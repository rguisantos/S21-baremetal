# FDT Samsung → recursos da árvore Apple

Etapa X2 parcial, **2026-10-22**. O novo adaptador de host lê o FDT bruto
e projeta os recursos explícitos para a representação Apple conferida na
[etapa anterior](xnu-boot-contract.md). O DTB base HZC2 gerou **1944 bytes**
de árvore de recursos, com reemissão byte a byte. Os **29 testes novos
passaram** com o parser C de produção instrumentado por ASan/UBSan.

É um fragmento de recursos. Ele permite revisar a tradução e sua origem,
mas não contém boot_args, janela DRAM, ramdisk, estado das CPUs ou identidade
Apple. Não é uma árvore de boot completa ou um carregador Samsung.

## Implementação e origem dos dados

`lab/xnu/fdt_probe.c` expõe os resultados de `r8/r10_payload/fdt.c` sem
endereços de teste ou chamada de política R10. O código de produção e seu
header não mudaram. A saída inclui bancos RAM, reservas do header e de
reserved-memory, reservas não resolvidas, initrd, CPUs, GIC e timer.

`lab/xnu/fdt_adapter.py` usa também o leitor limitado já existente em
`scripts/inspect_proton.py` / `tools/mkpayload.py`. Os dois leitores devem
concordar nos intervalos GIC e na lista/ordem de MPIDRs. O segundo leitor
fornece os caminhos das propriedades, PSCI e a tupla do timer virtual.
O relatório vincula todos os resultados ao hash do FDT e dos leitores.

| Entrada FDT | Saída Apple / regra |
|---|---|
| PSCI compatible 0.2/1.0 e method explícito | `/chosen/psci-method`, somente smc/hvc; sem fallback |
| CPUs ativas, reg e enable-method=psci | MPIDR u32 little-endian, na ordem original; 1–8 CPUs, sem truncar Aff3 |
| Timer clock-frequency u32 big-endian | timebase-frequency u64 little-endian de cada CPU; valor **nominal**, sem medir CNTFRQ |
| GICv3 reg com duas tuplas | Dois pares u64 little-endian, relativos à janela I/O gerada |
| Tamanhos GICD/GICR | Preservados integralmente; sem inferir stride por número de CPUs |
| Terceira tupla de interrupts do timer | Exige PPI virtual INTID 27 e trigger level, conforme o perfil XNU fixado |
| RAM, reservas e initrd | Conservados como entradas de política; não viram janela DRAM ou RAMDisk automaticamente |

As células raiz de endereço/tamanho devem ser explícitas e ter um ou dois
elementos. Recursos GIC/timer/PSCI ficam na raiz; tradução de buses não é
presumida. O adaptador recusa bindings ausentes, ambíguos ou incompatíveis,
frequência zero/ausente, CPUs sem enable-method e GIC sobreposto à RAM
declarada. As capacidades do parser C, o limite FDT de 2 MiB e limites
adicionais de nós/propriedades continuam aplicáveis.

A janela I/O cobre somente os dois intervalos GIC e seu espaço intermediário.
Essa conta não programa MMU/MMIO ou demonstra acesso ao Distributor/ICC.
A descoberta física dos redistributors por afinidade ainda precisa ser
implementada/validada no consumidor XNU; o mapa HZC2 de 2 MiB não comprova
um stride específico.

## Resultado na base HZC2

Entrada: os mesmos **389876 bytes**, SHA-256
`d75cd25518112ec3a64235497b33f2caf84d60e8080b92c17ef98774c439aa2d`,
da base DTS já [reproduzida](dts-source-roundtrip.md).

| Recurso | Valor lido / resultado |
|---|---|
| CPUs | 0x0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700 |
| PSCI | `/psci/method = smc` |
| GICD | `0x10200000 / 0x10000` |
| GICR | `0x10240000 / 0x200000` |
| Timer | 26 MHz nominais; físico INTID 30, virtual INTID 27 |
| Escolha Linux no DTB | `use-physical-timer`; não concede acesso ao CNTV usado pelo XNU |
| RAM | Nenhum banco descrito |
| Reservas | 29 intervalos; indicador de layout não resolvido ativo |
| Initrd declarado | `[0x84000000, 0x841fffff)`, tamanho **0x1fffff** |
| Fragmento Apple | 1944 bytes; SHA-256 `fc8be29667d80d4954a33f678719a3277d0f7c9f29931b5db962c22bf05bd360` |

O initrd é interpretado com limite final exclusivo, como o parser de
produção. Preservamos a declaração, inclusive seu tamanho não alinhado;
não arredondamos para 2 MiB nem a reutilizamos como RAMDisk XNU. O FDT
efetivo ajustado pelo LK pode ser diferente dessa base estática.

O relatório registra `load_plan_generated: false`,
`memory_ownership_verified: false` e `hardware_ready: false`. A geração do
fragmento pode passar mesmo sem RAM: ela só traduz recursos existentes.
Uma tentativa de compor candidato de memória é recusada nessa situação.

## API de candidato, somente no host

`validate_candidate` recebe um template Apple, boot_args, endereço dos
argumentos, kernel e buffers protegidos fornecidos pelo chamador. Substitui
as descrições de CPU/I/O e PSCI pelo fragmento; a substituição de I/O também
retira a UART anterior do template. Os outros nós continuam sob
responsabilidade do chamador. Não fabrica clocks de CPU ou dados de vídeo.

Os bancos e reservas vêm do parser C. O initrd Linux original é protegido
adicionalmente; não pode ser sobrescrito pela janela do candidato. Exigem-se
RAM presente, reservas resolvidas e declaração explícita de completude.
Depois, aplicam-se os limites/recusas do contrato binário: buracos, reservas,
buffers vivos, segmentos Mach-O, árvore, argumentos e ramdisk.

O teste positivo usa **RAM sintética em 0x40000000**, com reservas e initrd
fora de sua janela. Não fornece endereço de carga para o S21. Mesmo nesse
teste, sucesso significa consistência com as declarações fornecidas, e
`hardware_ready` permanece false. A API não escreve arquivos ou memória
física e não prova a origem/completude de uma declaração do chamador.

## Reprodução

Da raiz do repositório, com Python 3 e cc nativo:

```sh
python3 scripts/test_xnu_fdt_adapter.py
python3 scripts/inspect_xnu_fdt.py /caminho/base-HZC2.dtb \
  --out /caminho/nova-inspecao
```

São gerados `apple-resources.adt`, `report.json` e o inspetor C na pasta
nova. Uma pasta existente é recusada sem sobrescrever seu relatório.
Saída zero significa projeção de recursos válida; não significa aprovação
de memória. O CLI não tem opção para gerar plano de carga ou boot_args.

Os 29 testes cobrem tradução de células 1/2, MPIDRs, bancos acima de 4 GiB,
reservas do header/nós, status, PSCI, timer virtual, frequência, corrupção,
GIC, composição sintética e recusas por RAM/reservas/buffers. A checagem
de leaks é desativada no host instrumentado, como na suíte FDT existente;
os checks de endereço ASan e de comportamento indefinido UBSan permanecem.

O [manifesto](references/xnu-fdt-adapter-20261022.json) conserva relatório,
hashes, comando, resultado dos testes e o fragmento inteiro em hexadecimal.
Não há binário novo no Git. Esta entrega não reexecutou XNU no QEMU,
as 28 verificações do codec anterior ou as suítes R8/R9/R10, cujos fontes
não mudaram.

## Continuação

Essa integração já foi [executada numa variante EFI de laboratório](xnu-efi-adapter-lab.md),
com um caso positivo e cinco recusas antes da cópia/salto. O caminho
físico continua condicionado a P1/P2 do [roadmap](roadmap.md): região sob
posse demonstrada, FDT efetivo/reservas, entrada/coerência, acesso GIC/timer
e resultado recuperável. Os arquivos já recebidos bastam para essa próxima
etapa de desenvolvimento no host.
