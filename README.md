# S21-baremetal — AArch64 no QEMU e investigação do Exynos 2100

Kit de bring-up AArch64 com MMU, níveis de exceção, GICv3, timer e microkernel didático. A frente R10 investiga um payload para o Galaxy S21 Ultra **SM-G998B / p3s**, com evidências das imagens originais **G998BXXSJHZC2** fornecidas pelo usuário, que usa Android 15.

**Estado em 2026-10-24 (Campo Grande):** R8/R9 passam a regressão em QEMU; R10 compila e tem testes de componentes e integração em QEMU, mas ainda não foi executado no telefone. PRs #2 e #3 foram consolidadas na main. O DTS recebido, com três listas de CPUs corrigidas, reproduz o DTB base HZC2 byte a byte. Essa base confirma recursos do SoC, mas não descreve a RAM disponível após o bootloader.

O [roadmap atualizado](docs/roadmap.md) organiza o estado por frente e os critérios dos próximos marcos. A prioridade é fechar entrada/coerência e um canal de leitura para o diagnóstico mínimo; reconstrução de memória segue em paralelo. O primeiro registro no S21 e o boot R10 em uma CPU têm requisitos distintos e continuam pendentes.

O [bugreport HZC2 do aparelho](docs/dram-observed-hzc2.md) trouxe a primeira evidência de log nesta investigação: **Samsung, D1Z, 12.000000GB e `0001000850500130`** no `LAST KMSG`. Esse valor difere da comparação `0001000860000110` do driver, mas ambos selecionam Samsung/D1Z pelos getters LK; o observado corresponde à linha 15 da NEWTIME. São 229 palavras GNU e seis casos dos helpers originais no QEMU. O extrato público omite cmdline e identificadores; a observação não é uma leitura direta da SRAM ou do FDT final.

A [auditoria dos binários grandes](docs/binary-provenance.md) adiciona manifesto de 17 arquivos já versionados, com hashes e matches de pacotes locais/asset oficial. O `AGENTS.md` agora exige revisão automática concluída para o head exato antes de cada merge, além da revisão própria.

O [rastreio das colunas 1 e 12 da NEWTIME](docs/newtime-columns-hzc2.md) mostra que elas são chaves de subtabelas. Quatro execuções contínuas do callback no QEMU copiam a linha e param antes do primeiro acesso MMIO, sem fornecer gate ou desviar o fluxo. A análise estática segue a coluna 1 até um cálculo de 0/28 para AP0x0207365c e a coluna 12 até o ponteiro de seu payload; o significado físico de timing permanece aberto.

A [continuação estática dos consumidores](docs/newtime-consumers-hzc2.md) localiza o leitor da coluna 12 em `0x2cdb8` e segue seus campos até escritas nominais em registradores. Corrige o sentido do fluxo entre registros de 108/162 bytes e delimita o mapeamento ainda incerto de `vddcal_fw`; sem ampliar a execução QEMU ou nomear parâmetros físicos.

A [branch pública rebased-11 do kernel Exynos 2100](docs/xfwdrev-kernel-reference.md) foi conferida na revisão `756951a`: Linux 5.4.304-openela e config p3s. Três DTS compilaram e dois overlays foram aplicados no host; continuam sem nós RAM. O driver UART coincide com a referência Samsung recebida. A árvore é candidata para futura instrumentação Linux, com build completo e execução física ainda pendentes.

A [busca específica por referências a BL2](docs/bl2-kernel-consumers-hzc2.md) encontrou um consumidor Linux de `0x02073600` que imprime a palavra DRAM, uma constante comum ao BL2 HZC2, parâmetros de tempo bootstat e o nome `main_rev` para o campo que condiciona a reescrita das bases. São ligações estáticas; o produtor e os valores reais do registro continuam abertos.

A [continuação de metadados HZC2](docs/boot-metadata-hzc2.md) resolve nominalmente o callback NEWTIME e seu ponteiro de escrita, dependente de `0x15900108`. O alias com o registro DRAM segue condicional. Os formatos bootstat foram ligados à tabela e aos argumentos no LK: BL1 recebe literal 100. Foram 70 regressões BL2, seis recusas CLI e GNU de 156 instruções; sem valores físicos observados.

O [rastreio ACPM](docs/acpm-handshake-hzc2.md) encontrou um produtor Thumb de `0x38e00` em endereço local `0xa5900108`, com espera pela confirmação zero. Esse valor satisfaz a conta do destino NEWTIME `0x02073600`; o alias de hardware e a preservação da cadeia seguem condicionais. DTS fixado, 100 palavras AArch64/141 instruções Thumb conferidas por GNU, 70 regressões e 12 recusas CLI; sem execução física.

A [tabela ECT/NEWTIME](docs/newtime-ect-hzc2.md) foi recuperada do sboot: 57 descritores, com 22 linhas na seleção especial, incluindo `0xcafe`. Parser original e prefixo até a primeira escrita passaram em 56 casos QEMU, com 80 testes de host e GNU de 353 palavras. O argumento original é preservado nesse prefixo sob os bindings de laboratório; corpo posterior e estado físico seguem abertos.

A [construção condicional do registro NEWTIME](docs/newtime-record-hzc2.md) agora tem layout de `0x2400` bytes, gate reamostrado e erro 4 sem rollback delimitados. Foram 11264 combinações de ramos no modelo, 196 casos QEMU com escolhas de ramo explícitas, seis casos da folha do alocador, 92 testes de host e GNU de 623 palavras. O primeiro u64 permaneceu intacto no retorno direto do callback nesses bindings; o wrapper encaminha erros ao tratamento descrito abaixo. O estado físico segue pendente.

O [tratamento de erro NEWTIME](docs/newtime-error-hzc2.md) marca flags em `0x02073624`, solicita um dump de 104 palavras do cabeçalho e pode entrar numa rotina de depuração com acessos de hardware. Dump e conversor originais passaram em 26 casos QEMU com saída em RAM, mais 14 casos do fragmento de flags; GNU de 662 palavras e 101 testes de host. UART, buffer de log e callbacks mutáveis impedem estender a preservação ao caminho completo sem novas evidências.

O [empacotamento posterior da geometria](docs/bl2-geometry-packing-hzc2.md) mostra onde os quatro slots de estado são zerados e reconstruídos a partir de consultas. Inclui a extensão por seletor `0x31` e a diferença entre o modo final do slot 3 e o modo do slot 0 usado pela folha de tamanho. Passaram 100 cenários QEMU com retornos de chamadas fornecidos, cada um seguido pela folha original, 111 testes de host e GNU de 386 palavras. A publicação condicional é descrita a seguir; respostas e bindings físicos continuam abertos.

A [segunda publicação NEWTIME](docs/bl2-geometry-publication-hzc2.md) liga o primeiro slot ao ponteiro ativo de `0x30520`. O wrapper salva o argumento em `0x02073638` e depois relê o slot, portanto os valores podem divergir se ele mudar. Foram 160 cenários QEMU com chamadas originais e MMU de laboratório: 74 chegam à primeira escrita e 86 param no erro do prefixo; 119 testes e GNU de 464 palavras. Alias físico, conclusão do callback e preservação posterior continuam pendentes.

A frente Darwin agora [inicia XNU no QEMU com um programa próprio](docs/xnu-qemu-lab.md): PID 1/UID 0, arquivo APFS, timer e retorno ao carregador, com controle negativo recusado. O ensaio inicial usou kernel/loader prebuilt identificados; a variante EFI abaixo recompila o loader. A [interface iOS 16.5 foi reproduzida localmente no QEMU](docs/hackios-userland-qemu.md), com SpringBoard, Ajustes/Geral/Sobre respondendo a toques, o workspace de referência identificado e imagens APFS verificadas. A execução no S21 continua pendente. A [estratégia de escolha Android/XNU](docs/dual-boot-strategy.md) registra esse objetivo futuro e seus marcos. A [revisão HackiOS](docs/hackios-xnu-reference.md) conserva as diferenças de plataforma.

O [contrato binário XNU](docs/xnu-boot-contract.md) tem 28 testes de host, layout C conferido e captura QEMU de 736/14800 bytes reemitidos sem alteração. O [adaptador FDT → recursos Apple](docs/xnu-fdt-adapter.md) passou 29 testes e traduziu CPUs/GIC/PSCI/timer do HZC2 para um fragmento de 1944 bytes. X2 segue parcial no telefone: a base HZC2 continua sem bancos RAM e com reservas incompletas.

A [integração EFI no laboratório](docs/xnu-efi-adapter-lab.md) agora tem [reservas e quatro mapas UEFI capturados](docs/xnu-uefi-memory.md): payload reservado, janela inteira conferida antes da cópia/salto e buffers cruzados com o contrato observado. Foram **22 critérios positivos**, **oito recusas**, **22 testes de memória/evidência** e **16 testes de recursos**. O kernel continua prebuilt; memória e carregamento físicos do S21 permanecem pendentes.

As falhas de preparação HackiOS trazidas no relato GLM foram [reproduzidas no host](docs/hackios-userland-host.md): colisão dos jobs, permissões, drawable_test opcional e fallback de timezone. Há patch conferido e controles sintéticos. O relato GLM foi seguido pela reprodução local da interface, com o loader corrigido na fonte e capturas/ações preservadas.

O [defeito ramfb do prebuilt foi confirmado no QEMU](docs/xnu-ramfb-audit.md): o loader declara 800×600 após configurar 1125×2436. A correção na fonte passou seis controles, com captura real do padrão EFI, erro/timeout recusados e regressão XNU de 22 critérios. A fonte original recompilada com Clang 19 também funciona nesse teste; a falha não deve ser generalizada a toda compilação.

O [contrato de vídeo XNU foi validado com o kernel em execução](docs/xnu-video-contract.md): ramfb 1125×2436/32 bits, reserva conferida em quatro mapas UEFI, captura em arm_init e driver framebuffer observado. Foram **25 critérios com vídeo**, **22 sem display**, **três recusas** e **62 testes de host**. O ensaio original do consumidor restrito usou init próprio. Em uma execução separada do ABI de referência, o [SpringBoard apareceu localmente](docs/hackios-userland-qemu.md).

O [perfil iOS do consumidor EFI validado](docs/xnu-guarded-userland.md) já iniciou as imagens APFS identificadas: uma CPU, 7 GiB de RAM, reservas capturadas na entrada do kernel e navegação em SpringBoard/Ajustes/Geral/Sobre. O [ensaio anterior de disco residente](docs/xnu-resident-contract.md) usou init próprio e 4 MiB. O novo perfil concluiu o retorno nativo de 900 s e conferiu os quatro snapshots reemitidos; tem três recusas QEMU, 74 testes de host e quatro controles semânticos da captura.

A [auditoria do trecho final LK HZC2](docs/lk-final-edges.md) agora enumera as chamadas posteriores ao helper e os callbacks conhecidos: 1834 instruções conferidas com objdump e 29 testes de host. O recorte não escreve SCTLR, mas contém dependências de SCTLR_EL1 e polling sem timeout; o SMC anterior e o estado físico continuam abertos.

A [preparação do monitor HZC2 e os escritores da lista LK](docs/monitor-preparation-hzc2.md) agora têm inspeção reproduzível: pedido BL2 -0xe7, um segundo objeto de callback desativado por gate constante e consulta de metadados -0x12d. Foram 29 testes de host e 160 instruções conferidas com objdump. A semântica segura de -0x3ff e o estado físico seguem abertos.

A [origem do modo e o descritor BL2](docs/bl2-service-chain-hzc2.md) foram refinados: a resposta vem de X2 no SMC -0xe9, o seletor usa aritmética W e o pedido -0xe6 deixa campos herdados em dois modos. O modelo preserva esses desconhecidos. A [busca do estado anterior](docs/descriptor-provenance-hzc2.md) conferiu sete cópias que não alcançam a janela e distinguiu o limite LK `0xe7fffe00`; 40 testes de host passaram, com 165 palavras/23 alvos e 21 literais conferidos com objdump. O inicializador e o provedor seguro permanecem abertos.

O [prefixo EPBL e dispatcher SMC parcial](docs/epbl-preparation-hzc2.md) têm agora um [grafo de fronteiras](docs/epbl-frontier-hzc2.md): 1182 instruções, 13 arestas para a região pendente e dois produtores de VBAR coerentes com o mesmo delta nominal. Foram 36 testes de host e 138 destinos relativos conferidos com objdump. A referência SSS pública foi fixada por commit e não fornece o protocolo EPBL completo. Entrada vetorial, transformação e conteúdo runtime das tabelas continuam sem comprovação.

O [rastreio de buffers e MMIO EPBL](docs/epbl-protocol-hzc2.md) liga a primeira saída de 48 bytes ao material de 32 bytes e IV de 16 bytes da operação seguinte, seguida de comparação de 32 bytes. Foram 69 testes de host e conferência GNU de 1095 instruções/114 destinos/177 acessos MMIO. O padrão alto/baixo/tamanho indica uma entrada DMA candidata em `[0x1fc00,0x1fffc)`, sem binding ou conteúdo medidos. AES-256-CBC é uma inferência corroborada pela fonte SSS; algoritmo HASH, plaintext e ligação dos handlers continuam abertos.

A [proveniência do layout HASH](docs/epbl-hash-provenance-hzc2.md) agora cruza dez offsets com o perfil ACE Samsung v6 e com o emulador experimental Fireplace/Exynos9830. Corrige a nomenclatura alto/baixo dos contadores e demonstra que o modo `0x19` não é implementado nessa referência de emulação. Foram 83 testes; o algoritmo HZC2 e os dados da entrada candidata seguem desconhecidos. PR #5 revisado e integrado à main.

O [arquivo TZAR e as bibliotecas HZC2](docs/tzar-crypto-hzc2.md) agora têm inventário reproduzível de 44 registros, hashes e tradução dos três seletores de digest para pedidos de `/dev/crypto`. Foram 15 testes e conferência GNU de 15 símbolos/127 instruções/34 destinos. A fronteira EVP/dispositivo foi localizada; a implementação do driver e sua relação com o modo EPBL `0x19` continuam abertas. PR #6 revisado e integrado em `65040a6`.

A [ligação ioctl do TEEGRIS](docs/teegris-ioctl-boundary-hzc2.md) agora confere calls, PLT/GOT, relocação e versão requerida até `libtzsl.so`: o wrapper prepara X7=15 e executa SVC #0. Foram 30 testes e conferência GNU de 24 instruções/quatro destinos, além dos metadados de ligação. A conversão de erros foi delimitada; handler SVC, consumidor do dispositivo e modo EPBL `0x19` seguem abertos.

O [envelope BiEn do TZSW HZC2](docs/tzsw-bien-hzc2.md) agora tem leitura e validação de candidatos contra o original. O ensaio com a referência Exynos9830 foi reproduzido por OpenSSL/cryptography e recusado por divergência de digest; nenhum plaintext foi aceito. Quinze testes passaram. Esta ramificação do SVC depende de código correspondente em claro, mantendo diagnóstico físico e memória como frentes paralelas.

O [produtor BL2 do tamanho de RAM](docs/bl2-ram-size-hzc2.md) agora liga a escrita em `0x02038848` a uma folha candidata de geometria. As 44 instruções originais passaram **66 execuções QEMU** com entradas sintéticas em duas posições; **34 testes de host** e GNU de **300 palavras/23 destinos** também passaram. Geometria real, callbacks, eventual limite LK e bancos/reservas finais permanecem pendentes.

A [consulta que alimenta a geometria](docs/bl2-geometry-query-hzc2.md) foi seguida nominalmente até MMIO: campos de dois/sete bits, disparo e leitura de resposta de 32 bits, com cinco bases literais. Foram **48 testes** e GNU de **82 palavras/12 ponteiros**, sem executar hardware ou fornecer respostas simuladas. A preparação dos controladores e os bindings reais permanecem abertos.

Um [escritor condicional dessas bases](docs/bl2-query-base-rewrite-hzc2.md) agora demonstra que o BL2 pode trocar as cinco entradas terminadas em `0x6000` por `0xf000`, conforme um nibble de `0x10000010`. O outro ramo preserva o estado anterior. Foram **58 testes** e reconstrução independente GNU de cinco stores; a configuração ativa e as respostas físicas continuam desconhecidas.

O [registro anterior da geometria](docs/bl2-geometry-record-hzc2.md) agora liga duas recargas da primeira palavra a `0x02073600`. O marcador `0xcafe` e seis restaurações parciais foram delimitados; estas não incluem o primeiro u64. Foram **70 testes** e GNU de **148 palavras**, sem recuperar bytes do aparelho ou deduzir sua capacidade.

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
| Laboratório XNU | XNU prebuilt + init próprio; referência HackiOS com userland iOS | Consumidor validado com interface iOS em uma CPU e referência em quatro CPUs; sem teste Samsung |

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
python3 scripts/test_xnu_efi_memory.py
python3 scripts/test_xnu_video.py
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
- [Kernel público xfwdrev/rebased-11: comparação, DTS e limites do diagnóstico](docs/xfwdrev-kernel-reference.md)
- [Parser FDT, política de memória e contrato do carregador](docs/fdt-resources.md)
- [Entrada/GIC/timer/exceções e cobertura em uma CPU](docs/r10-single-cpu.md)
- [Carregamento Samsung e instalador Proton: contrato e lacunas](docs/loader-contract.md)
- [Revisão do empacotador do branch kilo e alegações de SMP](docs/branch-packer-review.md)
- [Carregador EL2 QEMU: main R10 real e recusas antes da cópia](docs/qemu-el2-loader.md)
- [Contêiner S21R10 v1: empacotador, validação e limites](docs/payload-format.md)
- [ZIP Proton publicado: hashes, Linux/EFI e DTB real](docs/proton-binary.md)
- [Proton+ v6.1.0: kernel, Mali r38p1 e recursos GPU](docs/proton-reference.md)
- [Referência TWRP indicada: DTB e configuração de recovery](docs/twrp-reference.md)
- [iOS pelo consumidor EFI validado: perfil, auditoria e interface](docs/xnu-guarded-userland.md)
- [Imagem APFS residente: descritor, reservas e raiz md0](docs/xnu-resident-contract.md)
- [Userland iOS 16.5 no QEMU: entradas, checkpoint e capturas](docs/hackios-userland-qemu.md)
- [HackiOS/XNU: código aproveitável, exercício HZC2 e etapas de um port](docs/hackios-xnu-reference.md)
- [XNU no QEMU com programa próprio: execução e contraprova](docs/xnu-qemu-lab.md)
- [Contrato XNU: layout, captura de argumentos/árvore e política de memória](docs/xnu-boot-contract.md)
- [FDT Samsung → recursos Apple: tradução, origem e recusas](docs/xnu-fdt-adapter.md)
- [Consumidor EFI: integração inicial e reprodução](docs/xnu-efi-adapter-lab.md)
- [Memória UEFI: reservas, quatro mapas completos e oito recusas no QEMU](docs/xnu-uefi-memory.md)
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
