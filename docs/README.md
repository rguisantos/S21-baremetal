# Guia da documentação

A entrada do projeto é o [README principal](../README.md). Este índice separa implementação, evidências e histórico. Os documentos descrevem testes de software; nenhum registra execução R10 no telefone.

## Implementação e testes atuais

- [Roadmap e estado atual](roadmap.md): evidências, prioridades e critérios separados para diagnóstico físico e R10 em uma CPU.
- [XNU no QEMU](xnu-qemu-lab.md): kernel/loader prebuilt, init próprio, execução positiva e controle negativo; [objetivo Android/XNU](dual-boot-strategy.md).
- [Contrato binário XNU](xnu-boot-contract.md): 28 testes de host, layout C independente, captura de boot_args/árvore Apple e recusa da base HZC2 incompleta.
- [Adaptador FDT → recursos Apple](xnu-fdt-adapter.md): 29 testes, projeção HZC2 com proveniência e política de memória sem alocação.
- [Integração EFI do adaptador](xnu-efi-adapter-lab.md): build do loader e primeira integração dos recursos.
- [Memória UEFI no QEMU](xnu-uefi-memory.md): payload/janela reservados, quatro mapas completos, 22 critérios positivos, oito recusas e 22 testes de memória/evidência; 16 testes de recursos reexecutados.
- [Vídeo entregue ao XNU](xnu-video-contract.md): contrato capturado em arm_init, framebuffer reservado, driver observado, controle headless e três recusas.
- [ramfb do HackiOS](xnu-ramfb-audit.md): defeito do prebuilt confirmado por memória/desmontagem, correção na fonte, seis controles e capturas EFI reais.
- [Userland pelo consumidor EFI validado](xnu-guarded-userland.md): perfil explícito em uma CPU, capturas UEFI/boot_args, interface e retorno nativo conferidos.
- [Disco residente](xnu-resident-contract.md): descritor versionado, reservas e papéis md0/md1.
- [Interface pelo loader de referência](hackios-userland-qemu.md): imagens preparadas, checkpoint e ensaio de quatro CPUs.
- [Preparação do userland HackiOS](hackios-userland-host.md): quatro falhas trazidas no relato GLM, seis fixtures de jobs, quatro controles Bash e patch conferido.
- [Trecho final LK HZC2](lk-final-edges.md): grafo estático limitado, callbacks conhecidos, leituras SCTLR_EL1 e fronteira do SMC; 29 testes de host.
- [Diagnóstico de entrada EL1/EL2](entry-diagnostic.md): Image independente, registro de estado e 12 casos QEMU no teste padrão.

- [R10 em uma CPU](r10-single-cpu.md): entrada, exceções, GIC e timer.
- [FDT e política de memória](fdt-resources.md).
- [Formato S21R10](payload-format.md): empacotador e validação.
- [Carregador EL2 no QEMU](qemu-el2-loader.md): materialização, main real e recusas.
- [Validação anterior](validation-2026-10-20.md) e [nova revisão e arquivos pendentes](repository-review-2026-10-21.md).

## Evidências do aparelho e fontes externas

- [Hardware](../EXYNOS2100_HARDWARE.md) e [firmware stock HZC2](stock-firmware-hzc2.md).
- [Fontes Samsung e READMEs recebidos](samsung-reference.md).
- [Kernel público xfwdrev/rebased-11](xfwdrev-kernel-reference.md): revisão fixada, comparação de fontes, três compilações DTS e dois overlays no host; sem build completo ou observação física.
- [Menções BL2 e consumidores no kernel](bl2-kernel-consumers-hzc2.md): registro DRAM em 0x02073600, constante comum ao BL2, bootstat e gate CHIPID; sem valores runtime.
- [NEWTIME e argumentos bootstat](boot-metadata-hzc2.md): callback nominal, ponteiro mutável/alias condicional do registro DRAM e literal 100 no campo BL1; GNU de 156 palavras, sem medições físicas.
- [Publicação ACPM e NEWTIME](acpm-handshake-hzc2.md): produtor Thumb de 0x38e00, confirmação zero e comparação DRAM no payload; DTS fixado, GNU AArch64/Thumb e aliases/preservação condicionais.
- [ECT/NEWTIME e primeira escrita](newtime-ect-hzc2.md): 57 descritores, 22 seletores incluindo 0xcafe, parser/prefixo originais em 56 casos QEMU; 80 testes e GNU de 353 palavras, sem estado físico.
- [Registro NEWTIME e erros posteriores](newtime-record-hzc2.md): layout de 0x2400 bytes, gate reamostrado, alocador e erro 4 sem rollback; 11264 combinações no modelo, 196 casos QEMU com ramos explícitos e seis da folha do alocador. Sem amostras MMIO ou registro físico.
- [Erro NEWTIME, dump e depuração](newtime-error-hzc2.md): flags em +0x24, dump de 104 palavras e console nominal; 26 casos do dump/14 do fragmento de flags no QEMU, 101 testes e GNU de 662 palavras. Efeitos completos e estado físico abertos.
- [DTS enviados e recompilação HZC2](dts-source-roundtrip.md): patch de três listas de CPUs, identidade binária da base stock e limites dos overlays genérico/P3S.
- [Proton: fonte](proton-reference.md), [binários](proton-binary.md) e [contrato do carregador Samsung](loader-contract.md).
- [Referência TWRP](twrp-reference.md) e [limites da coleta Shizuku](runtime-collection.md).
- [HackiOS/XNU](hackios-xnu-reference.md): possibilidades de laboratório Darwin, contratos distintos, exercício do gerador com HZC2 e dependências do port Exynos.

## Histórico e decisões

- [Integração dos PRs](../PR_INTEGRATION.md).
- [Revisão do branch kilo](branch-packer-review.md): por que seu packer e as alegações de SMP não devem substituir a main.
- [Worklog](../worklog.md): registro cronológico, não guia de execução atual.
- [Notas arquivadas](archive/exynos2100-notes-legacy.md): hipóteses antigas preservadas.

## Organização dos diretórios

| Diretório | Finalidade |
|---|---|
| `r8/` | Código R8/R9/R10, Makefile e fixtures/testes C/assembly |
| `lab/xnu/` | Init Darwin, codecs/validação, adaptador de recursos FDT e patch externo auditado; kernel/loader e UEFI externos |
| `shim/` | Shim legado em quarentena e componentes atuais do contêiner; consultar os documentos antes de executar |
| `scripts/` | Testes, bootstrap, inspeção e ferramentas históricas; [catálogo](../scripts/README.md) |
| `tools/` | Empacotador e toolchain/QEMU local; binários grandes preexistentes |
| `samsung_kernel/` | Recorte de referência, **não** árvore compilável completa; [escopo](../samsung_kernel/README.md) |
| `docs/archive/` | Documentação superada conservada para rastreabilidade |

`build/`, logs e caches Python são gerados e ignorados. Não adicionar dumps privados, pacotes firmware ou novos toolchains para documentar uma análise: registrar origem, tamanho e hash. A remoção dos binários já versionados exigiria planejar a distribuição offline; não foi feita nesta organização.

## BL HZC2 recebido

[Inventário, integridade e primeira análise do salto para o kernel](bootloader-hzc2.md). O pacote BL solicitado já foi recebido e analisado; não há novo arquivo necessário para continuar a análise estática. Atualização: PR #4 posteriormente criado, revisado e encerrado como substituído pela main. A análise do BL agora rastreia a origem do deslocamento do kernel e a construção dinâmica de nós RAM.

- [Splits do sboot HZC2 e entrada LK em EL1](sboot-layout-hzc2.md): validação do detector, inspeção reproduzível e revisão do relatório externo atualizado.

- [Fronteira do prefixo EPBL](epbl-frontier-hzc2.md): grafo de 1182 instruções, 13 saídas pendentes, segundo produtor de VBAR e referência SSS delimitada; 36 testes de host, sem ligação runtime dos vetores.

- [Buffers e protocolo MMIO EPBL](epbl-protocol-hzc2.md): 48 bytes → material 32/IV 16, resultado comparado de 32 bytes, entrada DMA candidata e status/polling; 69 testes e conferência GNU de 177 acessos. Sem plaintext ou ligação dos handlers.

- [Proveniência HASH e diferenças entre referências](epbl-hash-provenance-hzc2.md): dez offsets ACE/Fireplace corroborados, contador baixo/alto corrigido e modo 0x19 não implementado no emulador Exynos9830; 83 testes, sem atribuir algoritmo HZC2.

- [Preparação EPBL e dispatcher parcial](epbl-preparation-hzc2.md): pedido in-place/MMIO, normalização dos IDs, guarda e duas tabelas; entrada vetorial/handlers ainda abertos; 34 testes de host.

- [Estado anterior do descritor BL2](descriptor-provenance-hzc2.md): sete cópias fixas sem interseção, duplicata com campos ainda desconhecidos e distinção do limite LK; 40 testes, sem inicialização demonstrada.

- [Origem do modo e descritor BL2](bl2-service-chain-hzc2.md): retorno X2, seletor W, campos herdados do pedido -0xe6 e referências iniciais das tabelas; 38 testes de host, sem serviço seguro executado.

- [Preparação do monitor e mutações da lista LK](monitor-preparation-hzc2.md): argumentos BL2 -0xe7, segundo objeto condicionado, saltos B/BL e consulta de metadados; serviços seguros e lista viva continuam abertos.

- [Console LK e handoff final HZC2](lk-console-handoff.md): caminho de saída e pista de base 0x10540000.

- [Cache/MMU e trecho final do LK](lk-cache-handoff.md): helper restrito ao EL atual, operandos set/way e argumentos finais condicionais; 352 cenários com acessos de sistema substituídos, sem coerência física comprovada.

- [Roteamento UART, jig e coleta somente de leitura](uart-routing.md).

- [Log em memória LK/debug-snapshot](lk-memory-log.md): cursor, preservação pelo kernel e leitor offline.

- [Coleta limitada de logs pelo rish](boot-log-collection.md): interfaces de snapshot, metadados e limites.

- [Cópia da Image e destino de salto no LK](lk-kernel-copy.md): contexto e caminhos Android v2/v3.

- [Modelo offline LK v3](lk-v3-layout.md): kernel, ramdisks concatenados, extensão Image e região DTB, com testes de host.

- [Pipeline DTB/DTBO/DPM](lk-dtb-pipeline.md): ponteiro vendor ligado ao buffer do kernel, seletor por revisão e oito candidatos de host.

- [Escritas dinâmicas no FDT](lk-dynamic-fdt.md): initrd ligado às cópias, checagem parcial de chosen, reservas condicionais e origem do tamanho de RAM.

- [Construtor de bancos RAM no LK](lk-memory-bank-constructor.md): nove entradas explícitas, chamadas ao escritor e blocos altos de 512 MiB; 268 cenários Unicorn e 44 testes de host, sem valores reais ou FDT final.

- [Produtor do tamanho de RAM no BL2](bl2-ram-size-hzc2.md): escrita em `0x02038848`, callbacks nominais e folha de geometria; 66 execuções isoladas QEMU, 34 testes e GNU de 300 palavras, sem capacidade real ou mapa final.

- [Consulta da geometria no BL2](bl2-geometry-query-hzc2.md): callbacks nominais até MMIO, campos de dois/sete bits e cinco bases; 48 testes e GNU de 82 palavras/12 ponteiros, com respostas e bindings físicos ainda desconhecidos.

- [Reescrita das bases da consulta BL2](bl2-query-base-rewrite-hzc2.md): cinco u64 condicionados a um nibble de registrador, com preservação do estado no ramo sem escrita; 58 testes e reconstrução GNU de cinco stores, sem configuração ativa presumida.

- [Registro anterior da geometria BL2](bl2-geometry-record-hzc2.md): duas recargas de `0x02073600`, marcador e cópias/restaurações condicionais; 70 testes e GNU de 148 palavras, mantendo desconhecidos os bytes e os demais slots.

- [uH earlymem e Harx soc_info](el2-earlymem-hzc2.md): handler do HVC ligado ao LK, efeitos de alocação e relatório offline vinculado aos três hashes HZC2.

- [Intervalos LK → uH](lk-uh-range-registration.md): percurso dos nós memory do FDT, primeira tupla de reg, comando 2 e checagem offline dos argumentos.

- [Intervalo Harx no construtor de RAM](lk-harx-memory-gap.md): retornos constantes do serviço OEM, condição do LK e dependências ainda abertas.

- [Log Harx e coleta bloqueada](harx-log-observation.md): fonte/configuração/DTB cruzados; atributo presente, UNREADABLE no shell e nenhuma página capturada.

- [SEC_PGTBL e LDFW](sec-pgtbl-hzc2.md): seis registros, cifragem DRM, entrega -0x500 e 52 status na fonte; contratos distintos de carga/consulta/proteção. Chamador conferido em 248 cenários Unicorn, provedor ainda sem código em claro.

- [Kernel Exynos-2100/universal2100](exynos-2100-reference.md): comparação fixada por commit, aproveitamento e limites.

- [UART0 no intervalo BL2 HZC2](bl2-uart-hzc2.md): pinmux compatível, chamadas diretas e configuração nominal.

- [Clocks UART0 entre BL2 e LK](uart-clock-stages.md): tabelas PERIC0, wrapper principal e divisor.

- [Gates e QCH UART0](uart-gates.md): sincronizador de reset, IPCLK/PCLK, campos CAL e limites da busca estática.

- [Arquivo TZAR e fronteira criptográfica HZC2](tzar-crypto-hzc2.md): 44 registros descomprimidos e identificados, tradução de seletores e percursos EVP/dispositivo separados. Quinze testes e conferência GNU de 15 símbolos/127 instruções/34 destinos; não identifica o modo EPBL `0x19`.

- [Ligação ioctl e fronteira SVC do TEEGRIS](teegris-ioctl-boundary-hzc2.md): calls/PLT/GOT/relocação e versão requerida conferidos até libtzsl; X7=15/SVC #0, limites de erro e retorno. Trinta testes, metadados GNU e 24 instruções/quatro destinos; handler e dispositivo ainda pendentes.

- [Envelope BiEn e candidatos TZSW HZC2](tzsw-bien-hzc2.md): região candidata de 641264 bytes, quatro fontes fixadas e um ensaio negativo reproduzido por duas implementações AES. Quinze testes; candidato inválido retorna exit 1, sem salvar firmware/plaintext ou aceitar digest substituído.
