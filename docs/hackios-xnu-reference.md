# HackiOS / XNU: possibilidades para o S21

Revisão direcionada de fontes em **2026-10-22**. Base do S21-baremetal:
`56406dc234be3e0c36a70106ac80a5aa7cf0a37d`. Os dois projetos indicados
foram clonados separadamente e conferidos nos commits abaixo; os fontes,
prebuilt e perfis gerados ficaram fora deste repositório.

| Projeto | Commit examinado | Papel |
|---|---|---|
| [hackios-xnu-kernel](https://github.com/oosexgang/hackios-xnu-kernel/tree/8e61187098f2c26c5daee8f9f72b6416aa64b9ab) | `8e61187098f2c26c5daee8f9f72b6416aa64b9ab` | Patches XNU, drivers, carregador EFI, port UEFI e laboratório QEMU |
| [hackios-xnu-userland](https://github.com/oosexgang/hackios-xnu-userland/tree/906425b75e02b4f99eb5d7bb1ef7c9583472d772) | `906425b75e02b4f99eb5d7bb1ef7c9583472d772` | Init, bibliotecas de adaptação, imagens APFS e experimentos gráficos |

**A oportunidade nova é investigar XNU/Darwin com uma base de plataforma e
compatibilidade já escrita.** O S21 continua precisando de sua própria
entrada Samsung, memória e observação. O hardware de referência do HackiOS
é o POCO X5 Pro/redwood, Snapdragon 778G; o segundo alvo é QEMU virt. Os
perfis e a seleção de plataformas examinados não incluem p3s/Exynos 2100.

## O que existe e qual evidência temos

O kernel usa XNU **xnu-8796.121.2**; `xnu/apply.sh` verifica o commit Apple
`c54f35ca767986246321eb901baf8f5ff7923f6a` antes de aplicar o patch e os
arquivos adicionais. Há implementações concretas de GICv3, PSCI, platform
expert IOKit, APFS/ramfs e substitutos de drivers Apple. O userland mira
**iOS 16.5 / 20F66, iPhone10,3/6**; não basta trocar a versão do IPSW,
pois bibliotecas de adaptação usam interfaces e endereços dessa versão.

O README upstream relata SpringBoard/apps no POCO e QEMU, e traz imagens.
Esses resultados são **relatos upstream** nesta revisão: não executamos
kernel, UEFI ou iOS. A consulta GitHub retornou zero execuções de Actions
nos dois repositórios naquele momento. Isso não demonstra falha nem
substitui reprodução independente.

Conferências realizadas aqui:

- HEAD dos dois clones corresponde aos SHAs fixados; leitura dos trechos
  relevantes, sem auditoria integral dos drivers ou do patch.
- **7/7 hashes** dos prebuilt do kernel correspondem ao `prebuilt/SHA256SUMS`
  publicado. O kernel é Mach-O arm64; o loader é uma aplicação EFI AArch64
  em PE32+. Integridade do arquivo não comprova correspondência ao build.
- Gerador `common/new-device.sh` executado somente no host, numa cópia
  externa, com o DTB base HZC2 e DTC 1.7.2: resultado detalhado abaixo.
- Nenhum download do IPSW, build XNU, boot QEMU HackiOS, acesso ao telefone
  ou importação de código upstream nesta entrega. As suítes R8/R9/R10 não
  foram reexecutadas por esta revisão documental.

O [manifesto](references/hackios-xnu-20261022.json) registra identidade,
hashes dos arquivos consultados, integridade dos prebuilt e o exercício
do gerador. Nenhum desses checks é teste de funcionamento no S21.

**Continuação na mesma data:** o [laboratório XNU](xnu-qemu-lab.md) depois
executou o kernel/loader prebuilt no QEMU com nosso init, APFS e timer.
Há caso positivo e contraprova com um byte alterado. Essa evidência é
separada da revisão estática acima; o userland iOS e o S21 permanecem
sem execução demonstrada.

## Aproveitamento por camada

| Camada e fontes upstream | Possibilidade concreta | Trabalho específico no S21 |
|---|---|---|
| `GenericARMPE.cpp`, `gic_v3_irq.c`, `psci_smp.c` | Base para XNU em ARM genérico; estudar início de CPUs, IRQs e encerramento | Rever timer, redistributors, permissões do firmware e topologia; primeiro uma CPU |
| `xnuloader/loader.c` | Referência de carga Mach-O, montagem de argumentos e árvore Apple | Adaptador Samsung com bancos/reservas verificados e contrato de entrada próprio |
| `loader_return.c`, canal USB do loader, `xl` | Projeto de log em RAM, heartbeat e retorno ao carregador para recuperar o resultado | Backend de observação e contexto preservado próprios; USB deles depende de protocolos Qualcomm |
| `MiniIOSurface`, `MiniIOMobileFramebuffer`, `inject.c` | Caminho de estudo para interface gráfica usando framebuffer e rasterização por CPU antes da GPU | Framebuffer realmente ativo/reservado, formato, stride, coerência e painel Samsung |
| APFS/ramfs, `init.c`, `libmini`, geradores de imagens | Montar primeiro um ambiente Darwin mínimo, depois estudar os serviços do iOS | XNU/ABI Darwin funcionando; esses programas não usam as syscalls do R9 |
| AIR → NIR, Mesa, ponte OpenGL ES | Pesquisar reaproveitamento do frontend de shaders e interfaces gráficas | Backend e driver para Mali-G78; o caminho Adreno/freedreno/ir3 não o fornece |

Os caminhos da tabela são relativos ao respectivo projeto upstream. A
base R8/R9 mantém seu papel didático; o R10 segue como diagnóstico/bring-up
do Exynos. Executar o userland Darwin requer o kernel e seus contratos,
não apenas compilar programas arm64.

## Fronteiras que impedem uma troca direta

### Entrada, formatos e memória

Nos [argumentos e plataformas do loader](https://github.com/oosexgang/hackios-xnu-kernel/blob/8e61187098f2c26c5daee8f9f72b6416aa64b9ab/xnuloader/loader.c),
o contêiner é **XNUP**, o executável é Mach-O e x0 recebe um endereço de
**boot_args XNU**, que referencia uma árvore em formato Apple. Isso difere
do S21R10 v1 e do FDT bruto recebido pelo R10. O shim legado do nosso
projeto já foi colocado em quarentena por misturar esses contratos;
essa referência não reabilita aquele código.

O loader escolhe uma janela contígua por `GetMemoryMap` e
`EfiConventionalMemory`. Isso pressupõe uma UEFI cujo mapa já seja confiável.
Não descobre as reservas Samsung/Harx a partir dos endereços do POCO.
`PAYLOAD_BASE=0xf0000000`, FD em `0x9fd00000`, ramdisks e framebuffer
redwood não são propostas de alocação para o S21.

O comentário inicial do loader diz que sai dos boot services, mas o
desenho implementado e documentado junto a `loader_save_ctx` mantém UEFI
residente para retorno. `loader_return.c` explicita essa dependência.
`jump_to_kernel` opera em SCTLR_EL1 e entrega boot_args; não normaliza
automaticamente toda entrada Samsung ou os níveis de exceção.

O [empacotador de boot](https://github.com/oosexgang/hackios-xnu-kernel/blob/8e61187098f2c26c5daee8f9f72b6416aa64b9ab/mkxnuimg.py)
solicita Android **header v1** para o percurso redwood. Nosso stock HZC2
usa v3, com vendor_boot/DTBO. O fluxo `fastboot boot` documentado para o
POCO não estabelece um percurso de carregamento para este Samsung.

### GIC, timer e CPUs

O [driver GIC upstream](https://github.com/oosexgang/hackios-xnu-kernel/blob/8e61187098f2c26c5daee8f9f72b6416aa64b9ab/xnu/files/osfmk/arm64/gic_v3_irq.c)
usa ICC e compara a afinidade de GICR_TYPER com MPIDR. Entretanto:

- O passo de busca é fixo em **0x20000**; não interpreta VLPIS nem um stride
  do DT. O R10 atual já trata ambos e não deve perder essa propriedade.
- O loader emite uma região GICR de **0x100000** na árvore Apple; o DTB
  HZC2 informa **0x200000**. Tamanho dividido por oito CPUs continua sem
  provar o stride físico.
- O driver permite alterar GICD_CTLR e configurar SPIs. Isso exige revisão
  contra o estado/posse do firmware; o R10 atual só lê o Distributor.
- O timer desse port é **virtual, INTID 27**. Nosso R10 usa o **físico NS,
  INTID 30**. HZC2 descreve ambos no DTB; acesso e traps ainda dependem
  da entrada. A restrição CNTP mencionada no loader é do ambiente Qualcomm,
  sem prova equivalente para Samsung.

O [PSCI SMP](https://github.com/oosexgang/hackios-xnu-kernel/blob/8e61187098f2c26c5daee8f9f72b6416aa64b9ab/xnu/files/osfmk/arm64/psci_smp.c)
tem seleção SMC/HVC, estados de entrada, timeout, limpeza PoC antes de
CPU_ON e parada dos demais núcleos antes do retorno. São boas referências
para uma etapa futura. No S21, o método do DTB é **smc**; os MPIDRs
`0x000..0x700` avançam na afinidade 1. O campo `core_shift=8` coincide com
essa lista, mas não valida PSCI ou o agendamento dos três grupos A55/A78/X1.

### Display, GPU e serviços

`MiniIOMobileFramebuffer.cpp` compõe pixels no framebuffer deixado pelo
carregador e usa timer para vsync. Isso abre uma possibilidade de interface
por software, depois de estabelecer memória de vídeo e painel ativos no
S21; não inicializa DECON/DSI nem confirma um endereço de display Samsung.

`tools/mk-mesa.sh` seleciona `softpipe,freedreno`. Há um frontend AIR → NIR
e uma interface entre Metal e Mesa, porém a execução acelerada examinada
termina em Adreno. Mali-G78 continua exigindo seu próprio percurso de
memória, submissão, sincronização e compilação. O relatório AIR upstream
separa **321/456 módulos traduzidos/compilados** de correção em execução;
essa contagem não significa compatibilidade Metal completa ou resultado
Mali. Não reproduzimos esse corpus.

Touch/SPI, EPSS/cpufreq, GPIO/PMIC, Wi-Fi WCN6750/ath11k e áudio ADSP são
implementações redwood/Qualcomm. Há fronteiras úteis para estudar, mas não
são drivers dos periféricos do p3s.

Os substitutos IOKit e as bibliotecas injetadas resolvem parte das
dependências de userland, sem equivaler a todos os serviços de um iPhone.
Por exemplo, `MiniAppleKeyStore.cpp` declara não possuir chaves secretas e
implementa um estado sem senha. O README upstream lista Apple ID/App Store,
celular e outros recursos entre os limites. Isso delimita o experimento.

### Observação e retorno

É promissora a ideia de manter log/heartbeat em RAM e recuperá-los por um
carregador residente. Mas `usb_start` procura **QCOM_USB_DEVICE_GUID** e
**QCOM_USB_INIT_EVENT_GUID**: não há um transporte USB Samsung pronto nessa
função. A restauração do contexto e o retorno exigem controlar também os
periféricos compartilhados e os demais núcleos.

O código `write_logs` pode gravar por Block I/O numa partição **logdump**
quando disponível. Portanto o slogan upstream de execução em RAM não deve
ser transformado em garantia de ausência de escritas para um port. Nenhum
desses comandos foi executado no telefone.

## Exercício reproduzido com nosso DTB

Entrada: DTB base HZC2, **389876 bytes**, SHA-256
`d75cd25518112ec3a64235497b33f2caf84d60e8080b92c17ef98774c439aa2d`.
Na cópia externa do HackiOS, com DTC 1.7.2 no PATH, executamos:

```sh
bash common/new-device.sh p3s /caminho/stock-base.dtb
```

Resultado: **8 CPUs, core_shift=8, small_cores=0x0f**, mas
**GIC_DIST=TODO e GIC_REDIST=TODO**. O pai do GIC usa
`#address-cells=2`, `#size-cells=1`; suas duas tuplas de `reg` são:

```dts
reg = <0x0 0x10200000 0x10000 0x0 0x10240000 0x200000>;
```

São **seis células**. O parser textual do gerador aceita quatro ou pelo
menos oito; não decodifica o caso 2+1. O perfil também conserva defaults
Qualcomm de SoC, UEFI e endereços. Assim, a saída não é um port compilável
ou um mapa de memória autorizado. Não foi adicionada aos perfis do nosso
projeto. Nosso parser FDT já lê essas células pelo contexto dos nós.

## Frente proposta no roadmap

| Etapa | Entrega e critério |
|---|---|
| X0 — referência | Esta revisão com commits, checks e diferenças; concluída no escopo estático |
| X1 — kernel no laboratório | Ambiente separado: reproduzir XNU no QEMU e um programa estático mínimo; guardar versão, argumentos, logs e limites de build |
| X2 — contrato de port | Especificar Mach-O/boot_args/árvore Apple e comparar os recursos p3s; testar conversão com fixtures, sem endereços herdados do POCO |
| X3 — base física | Após diagnóstico Samsung com resultado recuperado, adaptar entrada/memória/GIC/timer para XNU em uma CPU e obter seu log |
| X4 — userland e interface | APFS/serviços primeiro no laboratório; no aparelho, framebuffer e CPU antes de GPU; periféricos com validação própria |

X1 pode avançar em paralelo à investigação HZC2. X2 pode começar como
especificação, mas X3 depende dos marcos físicos do
[roadmap principal](roadmap.md). A prioridade imediata desse roadmap
continua sendo entrada/coerência e recuperação do diagnóstico. R10 não
passou a ser um kernel Darwin e nenhuma etapa física foi concluída por
esta descoberta.

Para esta análise **não é necessário enviar arquivo adicional**. Os
arquivos HZC2 já recebidos bastam para cruzar os contratos. Um ensaio
posterior do userland completo requer as dependências descritas pelo
upstream, incluindo SDK/toolchain e extração local do iOS; não foi pedido
ao usuário nem iniciado download de vários GB nesta revisão.

## Referências primárias e licença

- [Roteiro de port](https://github.com/oosexgang/hackios-xnu-kernel/blob/8e61187098f2c26c5daee8f9f72b6416aa64b9ab/docs/PORTING.md),
  [build XNU](https://github.com/oosexgang/hackios-xnu-kernel/blob/8e61187098f2c26c5daee8f9f72b6416aa64b9ab/xnu/README.md)
  e [cuidados com verificações](https://github.com/oosexgang/hackios-xnu-kernel/blob/8e61187098f2c26c5daee8f9f72b6416aa64b9ab/docs/checks.md).
- [Userland](https://github.com/oosexgang/hackios-xnu-userland/blob/906425b75e02b4f99eb5d7bb1ef7c9583472d772/README.md),
  [inicialização/ABI Darwin](https://github.com/oosexgang/hackios-xnu-userland/blob/906425b75e02b4f99eb5d7bb1ef7c9583472d772/userland/libmini/start.S),
  [frontend AIR](https://github.com/oosexgang/hackios-xnu-userland/blob/906425b75e02b4f99eb5d7bb1ef7c9583472d772/tools/mesa/air/air_to_nir.c)
  e [relatório AIR](https://github.com/oosexgang/hackios-xnu-userland/blob/906425b75e02b4f99eb5d7bb1ef7c9583472d772/docs/air-report.md).
- O projeto kernel declara **APSL 2.0**, inclusive loader/scripts próprios;
  o userland próprio declara **MIT**. Componentes de terceiros conservam
  suas licenças, relacionadas pelos projetos. Esta entrega contém análise,
  referências e metadados, sem copiar suas implementações ou prebuilt.
