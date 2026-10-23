# Contrato binário XNU: argumentos, árvore e memória

Etapa X2 parcial, **2026-10-22**. Implementamos um codec de host para
`boot_args` e árvore Apple, com validação de intervalos. Conferimos o layout
contra o header Apple fixado e capturamos os buffers de uma execução XNU no
QEMU: **736 bytes de argumentos e 14800 bytes de árvore foram decodificados
e reemitidos sem mudar nenhum byte**. Após remover o breakpoint, a mesma
execução satisfez os 17 critérios do laboratório.

O componente está em `lab/xnu/boot_contract.py`. A entrega seguinte
acrescentou um [adaptador separado de recursos FDT](xnu-fdt-adapter.md).
Não há alocação, carregamento de imagens ou XNU no aparelho. Os dados
HZC2 disponíveis continuam insuficientes para gerar um plano físico.

## Layout conferido

A referência é o
[boot.h Apple](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/pexpert/pexpert/arm64/boot.h),
base XNU 8796.121.2, commit
`c54f35ca767986246321eb901baf8f5ff7923f6a`. SHA-256 do arquivo:
`efdfec46319cb147297682a8faebe02873f845261b57f7511ab8e15c13ef3439`.

| Campo | Offset em bytes | Representação neste perfil |
|---|---:|---|
| Revision | 0 | u16, valor 2 |
| Version | 2 | u16, valor 2 |
| virtBase | 8 | u64 |
| physBase | 16 | u64 |
| memSize | 24 | u64 |
| topOfKernelData | 32 | u64 |
| Video | 40 | seis u64; 48 bytes; todos zero |
| machineType | 88 | u32, zero |
| deviceTreeP | 96 | ponteiro virtual de 64 bits nesta captura |
| deviceTreeLength | 104 | u32 |
| CommandLine | 108 | 608 bytes; até 607 ASCII e NUL |
| bootFlags | 720 | u64, zero |
| memSizeActual | 728 | u64 |

Tamanho total: **736 bytes**, little-endian. O teste opcional compila o
header original sem alterações com `cc` no host LP64 e compara `sizeof`,
`sizeof(Boot_Video)` e os 13 offsets. Somente dois includes não relacionados
ao layout são substituídos por stubs vazios. Isso é uma comparação de ABI
LP64; não recompila XNU nem executa esse teste C em ARM.

O codec exige padding zero nos intervalos 4–7, 92–95 e 716–719, revisão e
versão 2, linha de comando ASCII e campos de vídeo/flags não utilizados
zerados. São restrições do nosso perfil, não uma afirmação de que todo
boot_args aceito por qualquer versão XNU tem essas características.

## Ponteiros e instante da captura

`capture_xnu_contract.py` verifica os hashes do kernel/loader, UEFI,
payload e fontes do ensaio positivo anterior. Constrói seus próprios
argumentos QEMU e usa FAT/NVRAM novos. A interface GDB fica em stdio, sem
porta de rede. Os comandos consultam registradores e memória e instalam
um breakpoint de execução; não escrevem registradores ou buffers.

O breakpoint é `_arm_init = 0xfffffff007453994`, **válido apenas para o
prebuilt conferido**. A captura acontece na entrada C do XNU, depois do
código de entrada assembly e antes da cópia dos argumentos em `arm_init`.
Portanto, x0 já é virtual. Não é uma medição do argumento inicial com MMU
desligada, de SCTLR ou da entrada Samsung.

| Valor observado/derivado | Resultado no QEMU |
|---|---|
| PC | `0xfffffff007453994` |
| PSTATE | `0x600003c4`, EL1 no instante observado |
| x0 virtual | `0xfffffff0086f4000` |
| Endereço físico derivado de x0 | `0xf86f4000` |
| virtBase / physBase | `0xfffffff004000000` / `0xf4000000` |
| memSize | `0xca000000` |
| deviceTreeP virtual | `0xfffffff0086e4000` |
| Endereço físico derivado da árvore | `0xf86e4000` |
| topOfKernelData | `0xf86f8000` |

A transformação conferida é `PA = physBase + (VA - virtBase)`, com limites
e overflow verificados. Os endereços desta tabela pertencem ao laboratório.
O hash e o conteúdo completo da captura constam no relatório local;
[o manifesto versionado](references/xnu-contract-20261022.json) conserva
hashes, offsets, intervalos, comandos substituíveis e resultados.
O [serial completo](references/xnu-contract-serial-20261022.txt) conserva
a execução retomada, com controles e espaços finais escapados; o manifesto
separa seu hash do hash bruto.

## Árvore Apple e perfil de recursos

A árvore Apple usa contagens little-endian de propriedades/filhos, nomes
de propriedade de 32 bytes, comprimento u32 e valores alinhados em quatro
bytes. **Não é FDT**: o magic e as células big-endian Samsung não podem ser
copiados para essa representação. As referências são
[device_tree.h](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/pexpert/pexpert/device_tree.h)
e [device_tree.c](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/pexpert/gen/device_tree.c).

O codec limita a árvore a 64 KiB, 256 nós, 2048 propriedades e 16 níveis.
Exige nomes terminados, nomes de filhos/propriedades únicos e padding zero;
recusa truncamento, contagens excessivas, sufixos e FDT bruto. Essas regras
canônicas são mais restritas que o formato Apple geral.

O validador confere o perfil do loader examinado:

- `/chosen`: DRAM igual aos argumentos e método PSCI `smc` ou `hvc`.
- `/chosen/memory-map`: RAMDisk obrigatório, RAMDisk1 opcional; ambos
  físicos, alinhados a 16 KiB; outros papéis são recusados.
- `/arm-io`: ranges com base de filho zero; GICv3 com dois intervalos
  distintos dentro dessa janela e fora dos bancos de RAM declarados.
- `/cpus`: uma a oito CPUs, MPIDR de 32 bits sem duplicidade e frequência
  de contador u64 não nula. Não verifica permissões ou frequência efetiva.

Uma fixture sintética preserva os oito MPIDRs `0x0`–`0x700`, GICD
`0x10200000/0x10000`, GICR **`0x10240000/0x200000`**, PSCI SMC e o valor
nominal de 26 MHz do Exynos. A RAM dessa fixture é inventada para teste,
explicitamente separada do S21. Não reduzimos GICR a 1 MiB nem inferimos
stride pelo número de CPUs. O XNU capturado usou o mapa QEMU e uma CPU.

## Política de memória

O chamador deve fornecer bancos de RAM, reservas, buffers protegidos e
uma declaração explícita de completude. Uma declaração ausente/incompleta
é recusada. O componente verifica consistência; **não autentica a origem
dessa declaração e sempre retorna `hardware_ready: false`**.

A janela linear tem bases alinhadas a 32 MiB e tamanho múltiplo de 16 KiB.
Precisa caber integralmente em um banco, sem atravessar buracos, reservas
ou entradas protegidas. Esta é uma política conservadora: até uma reserva
numa parte ainda não ocupada da janela provoca recusa. Não há alocador.

Argumentos, árvore, todos os segmentos Mach-O com memória e ramdisks devem
ficar nessa janela, abaixo de `topOfKernelData` e sem sobreposição entre
si. A leitura Mach-O limita tamanho/contagens, confere bounds de comandos,
segmentos e arquivos e converte seus endereços virtuais. Não é validação
integral de um executável, de seu entry point, assinatura ou relocations.
`memSizeActual` maior não autoriza uma janela fora dos bancos declarados.

Na captura, declaramos somente a fixture QEMU de 6 GiB e protegemos o
contêiner de entrada em `0xf0000000`. A lista de reservas é vazia e **não
capturamos o mapa completo UEFI**. O relatório registra
`trust_established: false`: o resultado PASS comprova consistência com
essa fixture, sem demonstrar propriedade de toda a memória do firmware.

## Validação e reprodução

Os **28 testes de host passaram**, cobrindo limites do codec, todos os
prefixos truncados da árvore de teste, padding/duplicidades, overflow,
buracos na RAM, reservas, sobreposições e metadados incompatíveis. A
comparação independente em C também passou. Execute da raiz:

```sh
python3 scripts/test_xnu_contract.py
python3 scripts/test_xnu_contract.py --apple-boot-header /caminho/boot.h
```

O segundo comando exige exatamente o header e SHA acima; não o baixa.
Para capturar uma nova execução, primeiro produza um ensaio positivo
conforme [XNU no QEMU](xnu-qemu-lab.md). Use a mesma UEFI conferida e uma
pasta de saída nova:

```sh
python3 scripts/capture_xnu_contract.py \
  --lab-run /caminho/ensaio-positivo \
  --efi-code /caminho/efi/usr/share/AAVMF/AAVMF_CODE.no-secboot.fd \
  --efi-vars /caminho/efi/usr/share/AAVMF/AAVMF_VARS.fd \
  --out /caminho/nova-captura \
  --samsung-fdt /caminho/base-HZC2.dtb
```

`--samsung-fdt` é opcional e somente inspeciona o arquivo com o parser C
R10 existente, compilado com ASan/UBSan. Não muda a árvore do guest.
`--tools` permite outro diretório de ferramentas; prazo padrão de 90 s.
São gerados argumentos/árvore brutos, serial, relatório JSON e cópias
descartáveis do ambiente. Nenhum binário novo foi versionado.

O ensaio registrado reemitiu os dois buffers byte a byte, removeu o
breakpoint e retomou até PID 1/UID 0, leitura APFS, timer, RB_HALT e retorno
normal: **17/17 critérios, QEMU saiu 0**. São critérios de uma execução;
não 17 boots. Os 13 testes do laboratório anterior são uma suíte diferente,
não reexecutada nesta entrega. R8/R9/R10 não sofreram alterações.

## HZC2 e próximo passo

O parser de produção aceitou a estrutura do DTB base de 389876 bytes
(SHA-256 `d75cd25518112ec3a64235497b33f2caf84d60e8080b92c17ef98774c439aa2d`),
leu CPUs/GIC/timer, mas a política de boot recusou o conteúdo: **zero
bancos RAM, 29 reservas e uma reserva não resolvida**. Não foi gerado
handoff candidato. Esse DTB base não é o FDT final ajustado pelo LK.

O [adaptador de recursos](xnu-fdt-adapter.md) já traduz CPU/GIC/PSCI/timer
com proveniência explícita, sem completar a RAM ausente. A integração já
foi [executada na EFI de laboratório](xnu-efi-adapter-lab.md). O plano físico depende de uma declaração
verificável de bancos/reservas e posse dos buffers. Entrada/cache, canal de observação e
permissões GIC/timer permanecem nos marcos físicos
[P1/P2 e A/B](roadmap.md). Não precisamos de outro anexo para continuar o
desenvolvimento no host.
