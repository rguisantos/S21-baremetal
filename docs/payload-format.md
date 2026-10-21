# S21R10 v1: empacotamento e inspeção

O empacotador `tools/mkpayload.py` produz o formato que estava descrito no loader, agora com limites explícitos. O novo consumidor `shim/payload.c` inspeciona os bytes sem copiar segmentos, acessar MMIO ou saltar para a imagem. **O handoff continua desativado**: a implementação antiga passava boot_args estilo XNU para um R10 que exige FDT bruto em x0.

## Uso reproduzível

Na raiz do repositório, com Python 3 e o toolchain habitual:

```bash
make -C r8 -j4 all
python3 scripts/test_fdt.py --write-qemu /tmp/r10-test.dtb
python3 tools/mkpayload.py r8/build/r10_payload.elf \
  --dtb /tmp/r10-test.dtb --cmdline 'inspection-only' -o /tmp/r10.payload
python3 scripts/test_payload.py
```

O DTB desse exemplo é uma fixture QEMU. Ele não descreve a posição padrão do R10 no telefone e não autoriza carregar a imagem. Para inspeção nativa do contêiner:

```bash
cc -std=c11 -O2 shim/tests/payload_probe.c shim/payload.c \
  r8/r10_payload/fdt.c -o /tmp/payload-inspect
/tmp/payload-inspect /tmp/r10.payload 0x47000000
```

O último argumento representa onde o contêiner residiria fisicamente; o validador recusa sobreposição com a janela de destino declarada. Ele não prova que essa janela é RAM livre. A saída JSON é um plano de inspeção, não uma execução.

## Layout binário

Todos os números são little-endian. Header de **680 bytes**, seguido por `nsegs` registros de **32 bytes**; conteúdo de segmentos e FDT seguem em offsets alinhados a oito bytes.

| Offset | Campo | Tamanho |
|---|---|---|
| 0 | magic `S21R10  `, incluindo dois espaços | 8 |
| 8 / 12 | version=1 / nsegs | 4 cada |
| 16 / 24 | virt_base / entry_va | 8 cada |
| 32 / 40 | dtb_off / dtb_size | 8 cada |
| 48 | kernel_end, arredondado a página após todos os PT_LOAD | 8 |
| 56 / 64 | phys_base / mem_size | 8 cada |
| 72 | cmdline UTF-8 terminada em NUL, até 607 bytes úteis | 608 |
| 680 + 32×i | vmaddr, vmsize, file_off, file_size | 8 cada |

`kernel_end` inclui BSS e pilhas NOLOAD quando o ELF as inclui em PT_LOAD; o ELF R10 atual faz isso. Os bytes BSS não são inventados no arquivo: vmsize descreve a extensão a zerar por um futuro loader correto. O DTB teria destino físico `kernel_end`. Não há criação de boot_args XNU, framebuffer presumido ou página extra desse ABI.

O formato v1 não codifica permissões de segmento: o produtor confere a entrada em bytes executáveis do ELF, mas o leitor do contêiner só pode verificar que a entrada está em bytes carregados. Ele não deve tratar a origem do arquivo como autenticada.

## Restrições implementadas

- ELF64 AArch64 little-endian, ET_EXEC, com até 32 PT_LOAD não vazios; PT_DYNAMIC/PT_INTERP, segmentos sobrepostos, W+X, entrada fora de bytes executáveis e alinhamentos inválidos são recusados.
- Somente identidade: p_paddr=p_vaddr e phys_base=virt_base. Alterar phys_base não reloca literais, tabelas ou código; não é suportado.
- Janela de destino e contêiner limitados a 64 MiB; DTB limitado a 2 MiB. Não existe default de “2 GB de RAM livre”. mem_size padrão é apenas a extensão mínima de imagem+DTB arredondada a página. Um valor explícito deve caber nos mesmos limites.
- O Python confere a estrutura do FDT e suas reservas; o consumidor C usa também o parser FDT de produção. Aceitar um FDT para inspeção não significa que ele descreve RAM/reservas suficientes para boot.
- O consumidor valida header, tabela completa, offsets, overflow, sobreposições de fonte/destino, arquivos/segmentos/FDT, limites de destino, cmdline e entrada antes de retornar um plano. Dados de entrada deliberadamente desalinhados são exercitados nos testes.
- O consumidor e o parser FDT devem ser chamados em uma thread antes de IRQs/SMP, pois usam workspace estático. Falhas invalidam a saída.
- O CLI não sobrescreve arquivos existentes e não executa instaladores, cria imagens Android ou grava partições. O campo cmdline é preservado como metadado; ele não altera `/chosen/bootargs`.

## Quarentena do shim antigo

A entrada padrão do shim agora estaciona antes de BSS, pilha, MMIO e C. `loader_boot()` retorna uma recusa explícita e não copia nem salta. Código legado só fica alcançável na entrada por uma compilação de auditoria explicitamente alterada para SHIM_LEGACY_EXPERIMENT; mesmo assim, loader_boot continua desativado.

Os problemas confirmados no código legado incluem boot_args incompatível, endereços fixos de framebuffer/GIC, topologia MPIDR 0..7, reprogramação global do Distributor e frame de exceção com escrita duplicada que sobrescreve x14/x15. O header ARM64 do shim também usa `_end` absoluto como image_size e não inclui adequadamente as pilhas; não é uma Image de hardware validada. Compilar o shim não demonstra que ele possa iniciar no QEMU ou Samsung.

Não há teste SMP do shim aprovado. Um comando QEMU com `-smp 8` sozinho não verifica CPU_ON, SGIs ou restauração de contexto. A integração R10 existente testa uma CPU com firmware sintético e continua separada deste contêiner.

## Validação desta entrega

`python3 scripts/test_payload.py`: **59 casos PASS**, incluindo fixtures ELF independentes, tamanho exato de BSS/pilhas do ELF real, casos inválidos, não sobrescrita pelo CLI, leitura C sob ASan/UBSan e fixtures Linux+EFI/vendor_boot. A inspeção read-only do ZIP publicado está em [proton-binary.md](proton-binary.md).

Próximo desbloqueio: um carregador de teste EL2 sem MMU que reserve memória antes de copiar, zere exatamente os intervalos apropriados, mantenha coerência de cache e passe o FDT bruto. Depois, executar o R10 em uma CPU através desse caminho no QEMU; somente então estudar SMP. O contrato Samsung continua pendente em [loader-contract.md](loader-contract.md).
