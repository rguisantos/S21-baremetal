# S21-baremetal — AArch64 no QEMU e investigação do Exynos 2100

Kit de bring-up AArch64 com MMU, níveis de exceção, GICv3, timer e microkernel didático. A frente R10 investiga um payload para o Galaxy S21 Ultra **SM-G998B / p3s**, com evidências das imagens originais **G998BXXSJHZC2** fornecidas pelo usuário, que usa Android 15.

**Estado em 2026-10-22 (Campo Grande):** R8/R9 passam a regressão em QEMU; R10 compila e tem testes de componentes e integração em QEMU, mas ainda não foi executado no telefone. PRs #2 e #3 foram consolidadas na main. O DTS recebido, com três listas de CPUs corrigidas, reproduz o DTB base HZC2 byte a byte. Essa base confirma recursos do SoC, mas não descreve a RAM disponível após o bootloader.

O [roadmap atualizado](docs/roadmap.md) organiza o estado por frente e os critérios dos próximos marcos. A prioridade é fechar entrada/coerência e um canal de leitura para o diagnóstico mínimo; reconstrução de memória segue em paralelo. O primeiro registro no S21 e o boot R10 em uma CPU têm requisitos distintos e continuam pendentes.

A frente Darwin agora [inicia XNU no QEMU com um programa próprio](docs/xnu-qemu-lab.md): PID 1/UID 0, arquivo APFS, timer e retorno ao carregador, com controle negativo recusado. Kernel/loader são prebuilt identificados; não houve execução do userland iOS ou no S21. A [estratégia de escolha Android/XNU](docs/dual-boot-strategy.md) registra esse objetivo futuro e seus marcos. A [revisão HackiOS](docs/hackios-xnu-reference.md) conserva as diferenças de plataforma.

O [contrato binário XNU](docs/xnu-boot-contract.md) tem 28 testes de host, layout C conferido e captura QEMU de 736/14800 bytes reemitidos sem alteração. O [adaptador FDT → recursos Apple](docs/xnu-fdt-adapter.md) passou 29 testes e traduziu CPUs/GIC/PSCI/timer do HZC2 para um fragmento de 1944 bytes. X2 segue parcial no telefone: a base HZC2 continua sem bancos RAM e com reservas incompletas.

A [integração EFI no laboratório](docs/xnu-efi-adapter-lab.md) já foi executada: carregador recompilado consumindo o fragmento QEMU, **20 critérios positivos**, **cinco recusas antes da cópia/salto** e **16 testes de host**. O kernel continua prebuilt; memória e carregamento físicos do S21 permanecem pendentes.

As falhas de preparação HackiOS trazidas no relato GLM foram [reproduzidas no host](docs/hackios-userland-host.md): colisão dos jobs, permissões, drawable_test opcional e fallback de timezone. Há patch conferido e controles sintéticos; a interface iOS do relato ainda não foi reproduzida aqui.

## Módulos e validação

| Módulo | Conteúdo | Evidência atual |
|---|---|---|
| R8A | MMU, alias virtual e faults deliberados | QEMU PASS |
| R8B | EL3 → EL2 → EL1 e acesso privilegiado negado | QEMU PASS |
| R8C | GICv3 e timer físico, INTID 30 | QEMU PASS |
| R9 | EL0, SVC, tarefas, troca de contexto e preempção | QEMU PASS |
| R10 | Entrada EL2 → EL1, FDT, GIC herdado, timer e exceções fatais | Compilação; modelos host; integração com carregador sintético no QEMU |
| Carregador de teste EL2 | Contêiner → main R10 real, UART QEMU | Materialização conferida por GDB; timer IRQ; cinco recusas; uma CPU |
| Diagnóstico de entrada | Image independente, captura EL1/EL2 sem periféricos | [12 casos QEMU PASS](docs/entry-diagnostic.md), seis entradas aceitas e seis recusas; sem execução no telefone |
| Shim | Legado em quarentena; inspeção S21R10 v1 | Compilação; entrada padrão estaciona; handoff desativado |
| Laboratório XNU | UEFI/loader → XNU prebuilt → init Darwin próprio | QEMU em uma CPU; caso positivo e arquivo corrompido recusado; sem userland iOS |

Há dois testes R10: o estágio anterior substitui a função C principal; o novo carregador EL2 materializa o contêiner e inicia também a main de produção, trocando apenas o backend UART por PL011 QEMU. A memória é conferida antes do salto e as IRQs depois dele. Isso não emula o Exynos, Harx, USI nem o bootloader Samsung.

## Compilar e reproduzir

Ambiente usado: Linux x86_64, Bash, make, Python 3 e compilador C nativo (`cc`) para os testes host. Toolchain AArch64 GCC 14.2 e QEMU 10.0.13 estão extraídos de pacotes Debian em `tools/root`; os pacotes em `tools/debs` permitem reconstrução com `scripts/bootstrap_tools.sh` e `dpkg-deb`, sem root. O repositório é grande por incluir essas ferramentas.

```bash
make -C r8 -j4 all
make -C r8 regress
python3 scripts/test_fdt.py
python3 scripts/test_payload.py
python3 scripts/test_payload_stage.py
python3 scripts/test_payload_loader.py
python3 scripts/test_entry_diag.py
python3 scripts/test_xnu_lab.py
python3 scripts/test_xnu_contract.py
python3 scripts/test_xnu_fdt_adapter.py
python3 scripts/test_xnu_efi_resources.py
bash scripts/test_pr_fixes.sh
bash scripts/test_r10_stage.sh
```

Os caminhos são relativos ao repositório: não há dependência de `/home/z`. É possível sobrescrever `TOOLS=/caminho/tools/root`; na ausência das ferramentas locais, o Makefile procura o cross-toolchain e QEMU no PATH. O wrapper `scripts/cross-run.sh` isola as bibliotecas do toolchain local; QEMU usa seu loader e dados locais.

`r8/build/` e `r8/logs/` são resultados gerados, não evidências binárias distribuídas. A regressão leva aproximadamente dois minutos porque os módulos estacionam intencionalmente. O harness confere assinaturas PASS; timeout 124 é esperado. Para execução individual:

```bash
timeout 25 make -C r8 run_r8a
timeout 25 make -C r8 run_r8b
timeout 40 make -C r8 run_r8c
timeout 35 make -C r8 run_r9
```

`make -C r8 run_r10` e `run_r10_hw` apenas informam o estado do ELF experimental. Não fazem flash nem demonstram um método de carregamento Samsung. O endereço padrão `0x80080000` continua sendo hipótese de linkedição, não RAM livre comprovada.

## R10 atual

**Evidência nova do BL HZC2:** a entrada de LK programa/preserva EL1; não há EL2 confirmado no salto para o kernel. O requisito EL2 atual do R10 foi testado no carregador sintético QEMU e ainda precisa de adaptação/validação para o Samsung. [Splits, instruções e correções do relatório externo](docs/sboot-layout-hzc2.md).

A entrada primária exige EL2 com MMU/D-cache de EL2 e EL1 desligados e preserva o FDT recebido em x0. A main permanece em uma CPU, sem ativar MMU, MCT, SMP ou PSCI. O parser verifica RAM, reservas, initrd, afinidade completa da CPU, GIC e timer antes de acessar o GIC. Descrições incompletas provocam parada, sem preencher lacunas com endereços presumidos. Pilhas agora integram o `p_memsz` do segmento ELF.

O Distributor pertence ao firmware e é somente lido. A interface de CPU usa registradores ICC; o redistributor é descoberto por afinidade em GICR_TYPER. Somente interrupções privadas são suportadas. Exceções inesperadas registram o contexto e estacionam; o R10 não usa a recuperação didática `ELR += 4` de R8.

A UART fica desativada por padrão. `R10_UART_FIRMWARE_CONFIGURED` só permite usar uma instância cuja configuração herdada tenha sido verificada; não inicializa clock, pinmux ou USI. MCT e SMP permanecem experimentais e fora da sequência inicial.

## Fontes e documentação

Comece pelo [índice organizado](docs/README.md) e pela [revisão atual com arquivos pendentes](docs/repository-review-2026-10-21.md). O catálogo de scripts distingue ferramentas atuais de experimentos históricos.

- [Mapa de hardware confirmado e pendências](EXYNOS2100_HARDWARE.md)
- [Imagens stock HZC2: cabeçalhos, DTB, overlays e hashes](docs/stock-firmware-hzc2.md)
- [DTS recebidos: patch de três listas e reprodução exata da base HZC2](docs/dts-source-roundtrip.md)
- [Construtor LK de bancos RAM: argumentos conferidos em 268 cenários](docs/lk-memory-bank-constructor.md)
- [Cache/MMU no LK: EL ativo, percurso set/way e limites do salto final](docs/lk-cache-handoff.md)
- [Pacote Samsung: base, delta e drivers consultados](docs/samsung-reference.md)
- [Parser FDT, política de memória e contrato do carregador](docs/fdt-resources.md)
- [Entrada/GIC/timer/exceções e cobertura em uma CPU](docs/r10-single-cpu.md)
- [Carregamento Samsung e instalador Proton: contrato e lacunas](docs/loader-contract.md)
- [Revisão do empacotador do branch kilo e alegações de SMP](docs/branch-packer-review.md)
- [Carregador EL2 QEMU: main R10 real e recusas antes da cópia](docs/qemu-el2-loader.md)
- [Contêiner S21R10 v1: empacotador, validação e limites](docs/payload-format.md)
- [ZIP Proton publicado: hashes, Linux/EFI e DTB real](docs/proton-binary.md)
- [Proton+ v6.1.0: kernel, Mali r38p1 e recursos GPU](docs/proton-reference.md)
- [Referência TWRP indicada: DTB e configuração de recovery](docs/twrp-reference.md)
- [HackiOS/XNU: código aproveitável, exercício HZC2 e etapas de um port](docs/hackios-xnu-reference.md)
- [XNU no QEMU com programa próprio: execução e contraprova](docs/xnu-qemu-lab.md)
- [Contrato XNU: layout, captura de argumentos/árvore e política de memória](docs/xnu-boot-contract.md)
- [FDT Samsung → recursos Apple: tradução, origem e recusas](docs/xnu-fdt-adapter.md)
- [Consumidor EFI: build, boot QEMU e cinco recusas antes do salto](docs/xnu-efi-adapter-lab.md)
- [Preparação HackiOS: quatro falhas reproduzidas e patch](docs/hackios-userland-host.md)
- [Objetivo Android/XNU: contratos e marcos da escolha de boot](docs/dual-boot-strategy.md)
- [Coleta sem root com Shizuku: resultado e limites](docs/runtime-collection.md)
- [Resultados reproduzidos nesta revisão](docs/validation-2026-10-20.md)
- [Integração dos PRs](PR_INTEGRATION.md) e [histórico de investigação](worklog.md)

`scripts/test_fdt.py --inspect arquivo.dtb` compila e executa o parser C real com ASan/UBSan, além das fixtures. Forneça um FDT bruto, separando antes eventuais tabelas Android. Ferramentas forenses antigas em `scripts/`, incluindo `parse_fdt.py` e `abl_triage.py`, não substituem essa validação: seus leitores de formatos ainda precisam de revisão antes de serem usados como evidência.

## Próximos passos para o telefone

Faltam um contrato de carregamento verificável, mapa de RAM e reservas após os ajustes do bootloader, estado de entrada/caches e acesso ICC/timer confirmado. Os DTBs stock e TWRP não resolvem essas lacunas. A coleta via Shizuku já foi tentada e documentada; ela não concede acesso root. Depois disso, fechar USI/clock/pinmux e só então ampliar para SPI, MCT e SMP com a topologia real.

As [notas antigas de hardware](docs/archive/exynos2100-notes-legacy.md) foram preservadas como histórico e contêm hipóteses superadas. A documentação atual distingue resultados observados de trabalho ainda não validado.

A Image do Proton publicada foi inspecionada: é Linux ARM64 com EFI stub, não um executável Windows que substitui Linux. O contêiner S21R10 agora pode ser gerado e validado offline, mas não habilita o shim ou testes de flash. Consulte as evidências binárias e o formato acima.

## BL HZC2 recebido

[Inventário, integridade e primeira análise do salto para o kernel](docs/bootloader-hzc2.md). O pacote BL solicitado já foi recebido e analisado; não há novo arquivo necessário para continuar a análise estática. Atualização: PR #4 posteriormente criado, revisado e encerrado como substituído pela main. A análise do BL agora rastreia a origem do deslocamento do kernel e a construção dinâmica de nós RAM.

A análise estática do [console LK HZC2](docs/lk-console-handoff.md) encontrou um caminho que seleciona `0x10540000`. O cruzamento com a fonte Samsung identifica UART0, canal debug configurado para 115200/8; ativação e conexão física seguem pendentes.

A [seleção do console por jig e MUIC](docs/uart-routing.md) foi rastreada no LK e cruzada com o driver MAX77705. Há um coletor somente de leitura para os atributos UART/MUIC no Android.

A [coleta UART/MUIC no aparelho](docs/runtime-collection.md#coleta-uartmuic-recebida--2026-10-21) confirmou SM-G998B/HZC2 e os limites do shell: `uart_en` existe, mas é ilegível; `attached_dev` retornou `No VPS`. A habilitação e a seleção AP/CP continuam desconhecidas.

O callback adicional do LK foi identificado como [log em memória debug-snapshot](docs/lk-memory-log.md), em região de 2 MiB. Há um leitor offline com testes sintéticos; ainda não foi obtido dump dessa região no telefone.

Para testar o acesso aos logs sem root, há um [procedimento limitado pelo rish](docs/boot-log-collection.md), com relatório de permissões e capturas de até 2 MiB por arquivo. A execução no aparelho foi concluída: os três nós apareceram ausentes ou ocultos pelo acesso do shell, sem conteúdo capturado.

A [cadeia de cópia da Image no LK](docs/lk-kernel-copy.md) foi ligada ao destino do salto. O diagnóstico independente passou em 128 casos QEMU cobrindo EL1/EL2 e todos os 64 deslocamentos decodificados; nenhum teste físico foi realizado.

O [modelo offline LK v3](docs/lk-v3-layout.md) confere as três cópias kernel/ramdisk nas imagens stock, a extensão declarada pela Image e o ponteiro DTB staging. Sete testes de host passaram, incluindo 64 cenários de deslocamento e recusas de entradas inválidas. Não é um empacotador ou validação de boot no aparelho.

A [seleção DTB e os merges DTBO/DPM](docs/lk-dtb-pipeline.md) foram ligados ao buffer 0x8b080000. O seletor offline passou em seis testes; oito candidatos de placa+DPM passaram na aplicação com libfdt, mantendo UART/GIC/timer/PSCI e sem nós RAM. Isso não reproduz a UFDT Samsung nem o FDT final do aparelho.

A [recompilação dos DTS enviados](docs/dts-source-roundtrip.md) identificou três escapes octais ambíguos em listas de CPUs. O patch em uma cópia, compilado com DTC 1.7.2 e `-a 4`, reproduz os 389.876 bytes da base stock. O overlay genérico UNIVERSAL2100 habilita UART0 e mantém UART1 desabilitada; o P3S-fonte r17 habilita ambas, mas seu binário difere do overlay stock. Os candidatos continuam sem RAM e foram corretamente recusados na checagem do initrd LK v3. Os originais foram preservados.

O [rastreio das escritas dinâmicas](docs/lk-dynamic-fdt.md) ligou chosen ao initrd concatenado: 0x84080000–0x84ca12df no ramo stock v3. O verificador aceita `--fdt` para comparar essas propriedades e recusa os valores antigos dos candidatos estáticos; a suíte conjunta passou em 19 testes. Reservas condicionais e o getter de tamanho de RAM foram localizados, sem reconstruir o mapa efetivo.

A [sequência do construtor de bancos RAM](docs/lk-memory-bank-constructor.md) agora tem modelo com nove entradas explícitas e conferência das instruções originais em **268 cenários Unicorn**, além de **44 testes de host LK**. Foram reproduzidos os recortes Harx/SEC_PGTBL, a aritmética X/W e os blocos altos de 512 MiB a partir de 0x880000000, inclusive o último bloco inteiro. A conferência captura argumentos ao escritor; respostas reais, sucesso das edições e mapa final continuam pendentes.

A [auditoria de cache/MMU e argumentos finais](docs/lk-cache-handoff.md) conferiu **352 cenários Unicorn e 14 testes novos de host**. O helper limpa M/C somente no EL atual quando M=1; M=0/C=1 conserva C, e I permanece inalterado. Registradores e operações de cache são fornecidos/registrados pelo harness. As chamadas posteriores e o SMC -0x3ff anterior continuam sem contrato fechado; isso não comprova coerência física ou estado final no S21.

O [handler uH de earlymem](docs/el2-earlymem-hzc2.md) foi ligado ao HVC 0x83000004 do LK no mesmo pacote BL. Ele pode alocar e inicializar memória; não é uma consulta pura. Um novo inspetor offline exige os hashes de sboot/uH/Harx e registra a cadeia. Os três testes novos e os 19 testes LK passaram; base/tamanho efetivos e mapa final continuam desconhecidos. Nenhum arquivo adicional é necessário para continuar esta análise.

Os [intervalos enviados ao uH](docs/lk-uh-range-registration.md) vêm do FDT corrente: o LK seleciona nomes com prefixo `memory` e envia somente a primeira tupla de `reg` pelo comando 0x83000002, antes de pedir earlymem. A nova checagem reproduz esses argumentos sem executar serviços; o conjunto offline passou em 30 testes. Falta determinar os valores usados na construção dinâmica dos bancos.

Uma [região Harx omitida na construção de RAM](docs/lk-harx-memory-gap.md) foi ligada ao serviço 0xc6000020: o handler tem retornos constantes para 0xc0000000–0xc1400000 (20 MiB). O inspetor agora decodifica esses retornos e a suíte offline passou em 33 testes. A execução desse ramo e os demais valores soc_info/SMC continuam sem observação no telefone.

O [log Harx](docs/harx-log-observation.md) foi cruzado com fonte, configuração embutida e DTB stock. A coleta no aparelho confirmou `exynos_el2_log` com modo 0644, mas retornou **UNREADABLE** para uid=2000(shell); nenhuma página foi aberta ou capturada. Não repetir nas mesmas condições. Os 40 testes de host anteriores validam as ferramentas; a chamada 0xc6000040 foi corrigida na documentação para registro de callback/buffer de crash.

O [tratamento de SEC_PGTBL no LK](docs/sec-pgtbl-hzc2.md) foi conferido executando as instruções originais em Unicorn: **248 cenários controlados** coincidiram com o modelo, sendo 144 básicos e 104 injeções hipotéticas das palavras do enum DRM. A suíte de host passou em **20 testes**. O header Samsung recebido confirma 52 constantes, incluindo E_DRMDRV_INVALID_SIZE_ALIGN=0x1003; isso não demonstra que a consulta devolva esse enum. As respostas foram fornecidas explicitamente e o provedor não foi executado.

O contêiner LDFW tem seis registros e sua entrega ao monitor por SMC -0x500 foi rastreada. O `drm_fw`, candidato pelo identificador 0x82002000, está marcado como cifrado; somente o tail tem código em claro conferido. Recuperar o handler e seus retornos reais exige código DRM HZC2 em claro com origem verificável ou fonte correspondente. O arquivo cifrado original já foi recebido e não precisa ser reenviado.

Os contratos foram separados nas evidências: a carga -0x500 trata contadores/casos especiais, a consulta 0x82002060 devolve base/tamanho e as operações de proteção na fonte comparam o status com DRMDRV_OK. Zero significa sucesso nessas operações de proteção e valor inválido na consulta. O harness atual não executa o monitor seguro ou produz um dump DRM pós-decriptação.

O diagnóstico também foi testado com `SCTLR.C` ligado por uma fixture QEMU: recusou a entrada em EL1/EL2 antes de gravar o registro. O teste padrão ampliado agora cobre seis entradas aceitas e seis recusas, incluindo MMU ligada e M|C em EL1/EL2.

O [roadmap atual](docs/roadmap.md) registra os marcos concluídos e o que ainda bloqueia o primeiro diagnóstico no telefone.

A [referência Exynos-2100/universal2100](docs/exynos-2100-reference.md) foi comparada ao pacote Samsung: 18 arquivos, 13 idênticos. O cruzamento detalhou clocks/pinctrl UART0 e registrou uma divergência de pinmux com o LK.

Uma [rotina anterior no intervalo BL2](docs/bl2-uart-hzc2.md) configura GPG0_CON `0x10430120` com os campos UART0 previstos pelo DTS. Isso contextualiza a divergência do LK; a configuração efetiva no handoff ainda não foi medida.

O [rastreio dos clocks entre BL2 e LK](docs/uart-clock-stages.md) encontrou um wrapper ligado à entrada BL2 com nominal 133,25 MHz/115200; seu divisor 71 coincide com o LK. Isso refina o caminho separado de 26 MHz, sem medir a frequência final.

A [auditoria nominal da árvore UART0](docs/uart-clock-stages.md#origem-nominal-fechada-na-fonte--continuação-2026-10-21) fechou a conta PLL_SHARED2 799,5 MHz ÷2 ÷1 ÷3 = 133,25 MHz, consistente com BL2/LK. A ferramenta offline verifica os hashes e seletores; gates e frequência real permanecem pendentes.

O [inventário dos gates UART0](docs/uart-gates.md) distingue sincronizador de reset, IPCLK, PCLK e QCH. O PCLK deriva de BUS_USER, separado do nominal UART_DBG. A auditoria extrai endereços/campos de quatro fontes verificadas por hash, sem atribuir estado ao hardware.
