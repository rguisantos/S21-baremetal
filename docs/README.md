# Guia da documentação

A [proposta única de carga, captura e recuperação](marco-a-carga-captura-recuperacao.md) passa a orientar o trabalho imediato: captura cooperativa em uma Image Linux de diagnóstico e exportação somente de leitura no mesmo boot. É uma proposta ainda não implementada; a sonda WFE, o Marco A standalone e a decisão OEM continuam separados. NEWTIME/DMC/ASV, expansão XNU e SMP ficam pausados.

O [caminho candidato IOCC do UFS](lk-ufs-iocc-hzc2.md) agora separa bypass PHY e coerência: a tabela alternativa com consulta1 usa endereço/máscara compatíveis com o FlopKernel. OR preserva bits antigos; consultas distintas podem combinar tabela e máscara. São32 casos originais em QEMU com alvos em RAM e26 testes novos, sem prova de DMA físico.

A [entrada LK e o granule herdado](lk-entry-granule-hzc2.md) foram ensaiados com código original: EL2h desce para EL1h, EL1t é preservado e o TCR fornecido permanece intacto. O getter retorna4/64/16KiB conforme TG0; o perfil4KiB continua condicionado. São24 entradas,48 chamadas do getter em QEMU e14 testes novos.

O [produtor local do magic DVFS](newtime-dmc-magic-hzc2.md) foi confirmado em `0x369a0`: publica `0xabcd1234`, toca a campainha do canal3 e espera limpeza externa. A reprodução corrige a identificação do trecho como EL3 e limita a alegação de escritor único. São22 testes novos, mais14 da referência ACPM/ECT com oito fontes FlopKernel.

A [construção da tradução do pool UFS](lk-pool-mmu-hzc2.md) foi conferida: no perfil EL1/4KiB, as 3043 páginas têm identidade de estágio1 e atributos normais cacheáveis, RW/PXN. O código original gerou as tabelas previstas em seis casos QEMU; 21 testes novos. Granule herdado, estado vivo e coerência DMA continuam separados.

O [pool que abastece o heap UFS](lk-heap-pool-hzc2.md) foi ligado ao provedor de páginas: faixa nominal `[0xe8c1d000,0xe9800000)`, com 3043 páginas. São 28 casos do código original em QEMU, incluindo falha que mantém o host publicado sem buffers; 17 testes novos. Estado físico e identidade DMA continuam pendentes.

A [origem do host e buffers UFS](lk-ufs-host-memory-hzc2.md) está ligada nominalmente ao alocador e às tabelas locais, com 19 testes novos. O cruzamento ampliado com FlopKernel esclarece PRDT em bytes, DMA e seleção de driver UART. Alinhamento e stores de endereços permanecem separados da coerência física.

A [preparação e conclusão UFS do LK](lk-ufs-completion-hzc2.md) agora liga LUN68→0xc4, descritores, polling e publicação do status SCSI. São635 palavras GNU e21 testes novos. Os retornos de espera, OCS, SCSI e autenticação RPMB foram separados; conclusão física e persistência seguem sem observação.

O [registro e transporte RPMB do LK](lk-rpmb-transport-hzc2.md) agora ligam nominalmente `scsirpmb` aos wrappers, callbacks SCSI IN/OUT e entrada UFS. São992 palavras GNU e16 testes novos. Instalação ativa, host, completion e persistência continuam sem observação física.

A [referência FlopKernel Exynos2100](flop-kernel-reference.md) confirma o layout RPMB com probe C do host e acrescenta um leitor offline de frames, com 26 testes novos. Revisão fixada em `4553117`; suporte de fonte para p3s confirmado. Interfaces Linux/monitor/LK e estado do aparelho permanecem separados.

O [backend RPMB dos contadores](lk-rpmb-hzc2.md) está ligado aos pacotes locais, callbacks `scsirpmb` e pedidos seguros de nonce/MAC. A análise confere 1.156 palavras GNU e 16 testes novos; distingue revisões de rollback, contador de escrita e efeitos anteriores aos testes de autenticação. Persistência e implementação segura continuam abertas.

Os [verificadores Samsung chamados pelas partições](lk-samsung-checks-hzc2.md) agora têm papéis separados: seleção/pedido de assinatura ao monitor, comparação de revisão para rollback e política de binário personalizado. São 801 palavras GNU e 16 testes novos. Retornos zero, fallbacks e efeitos de política foram distinguidos da aceitação física de uma Image.

A [conferência de Build-id e os helpers de partições](lk-build-id-partitions-hzc2.md) estão delimitados localmente. O checker compara um prefixo entre caches atribuídos a vbmeta/super; atualização, terminação e valor da política permanecem sem medição. São 1.497 palavras GNU e 14 testes novos, sem execução de firmware Samsung.

O [wrapper AVB e seu chamador](lk-avb-wrapper-hzc2.md) têm os retornos locais delimitados: red conserva um laço antes do epílogo; o retorno normal preserva o resultado do slot e é descartado imediatamente pelo chamador. Pedidos de metadados ao monitor foram identificados. São 847 palavras GNU e 17 testes novos; aceitação física e efeitos dos serviços seguros continuam abertos.

O [verificador vbmeta e caminho RSA](lk-avb-signature-hzc2.md) agora tem resultados separados de cabeçalho, hash e assinatura, com seis combinações SHA/RSA e padding PKCS#1 v1.5 conferidos. São 1.147 palavras GNU e 18 testes novos. A conversão desses resultados para o slot foi delimitada; confiança da chave e autorização final de boot continuam etapas distintas.

O [callback de confiança AVB](lk-avb-key-trust-hzc2.md) foi ligado nominalmente ao pedido de chave `vbmeta` no monitor. O consumidor separa status de I/O e confiança; consulta de desbloqueio e classificação local dos rótulos também foram delimitadas. São 342 palavras GNU e 13 testes novos; aceitação final e igualdade com a chave embutida continuam abertas.

- [Serviços da tabela DMC17 e consumidor](newtime-dmc-table-services-hzc2.md): primeiro resultado/todas as escritas, acumulador ID18, aliases e publicador por entrada0→entrada4; 21 testes.

- [Carregador DMC17 e cauda](newtime-dmc-loader-hzc2.md): comparação sem aborto, linhas por argumentos distintos, publicações e releituras de controle; 20 testes.

- [Callback0, truncamento de índice e DMC17](newtime-domain0-callees-hzc2.md): duas folhas com stores, count0→255, carregador e segundo método por raízes distintas; 20 testes.

- [Helper DVFS e dependências do canal direto](newtime-fast-apply-hzc2.md): quinze entradas, retorno/clear sem agregação de erros e seleção transitiva de domínio0; 20 testes.

- [Canal direto3 e gate DVFS +0](newtime-fast-channel-hzc2.md): evento128/máscara8, dois magics distintos e17 testes; clear0x104 sem barreira demonstrada.
- [Ordem dos handshakes e publicação DMC](newtime-dmc-init-order-hzc2.md): ACK0x108, magic0x10c e entrada tardia BL2; ordem parcial e 13 testes.

- [Produtor BL2 das máscaras e base DMC](newtime-dmc-bl2-producer-hzc2.md): três stores concretas, fonte ECT e concordância condicional de cache/fallback; 13 testes.

- [Escrita DMC por descritor e cache h/g2](newtime-dmc-config-hzc2.md): comando20, store calculada, aliases condicionais e duas origens do cache; 16 testes.

- [DMC método +12 e subcomandos 8/9](newtime-dmc-method12-hzc2.md): cadeia nominal, retornos, polls e correções dos modelos/testes GLM; 78 testes.

- [Setters de política FVP](newtime-policy-writers-hzc2.md): limites, habilitação u32 e recomputação em nova invocação comando6.

- [Conclusão do dispatcher ACPM](newtime-dispatch-completion-hzc2.md): logging, avanço do índice e saída sem agregação de erros.

- [Retornos FVP e cache](newtime-return-planes-hzc2.md): resultado u32, low16 construído e header publicado; nova invocação após falha.

A entrada do projeto é o [README principal](../README.md). Este índice separa implementação, evidências e histórico. Os documentos descrevem testes de software; nenhum registra execução R10 no telefone.

## Implementação e testes atuais

- [Roadmap e estado atual](roadmap.md): evidências, prioridades e critérios separados para diagnóstico físico e R10 em uma CPU.
- [Baseline obrigatório e CI](baseline-validation.md): comando único, ELF novo, host/QEMU, logs, timeout e recusa de skips.
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
- [Diagnóstico de entrada EL1/EL2](entry-diagnostic.md): Image independente, registro de estado e 12 casos QEMU no teste padrão; leitor de símbolos corrigido para cabeçalhos traduzidos, com cinco regressões no CI.
- [Contrato do diagnóstico Samsung](samsung-diagnostic-contract.md): matriz de carga/recuperação, condições pendentes e leitor offline de registros/capturas QEMU.
- [Perfis de dump e encaminhamento RDX](lk-dump-export-hzc2.md): quatro regiões fixas, descritores dinâmicos e envio nominal; disponibilidade e retenção ainda pendentes.
- [Origem da memória RDX e conclusão para a sonda](lk-rdx-memory-origin-hzc2.md): produtor `0xee370`, bancos de 16 bytes agrupados em pares, cobertura nominal da janela candidata e binding DWC3; a sonda atual não retorna cooperativamente ao LK.
- [Continuação de retorno da Image no LK](lk-payload-return-hzc2.md): epílogos, wrapper `sbl_boot` e saída da thread; retorno nominal descarta o valor da Image e não transfere diretamente ao RDX nos blocos selecionados.
- [Panic e recuperação de contexto](lk-panic-recovery-hzc2.md): parada local ou ERET para contexto salvo; aquisição RDX não demonstrada.

- [R10 em uma CPU](r10-single-cpu.md): entrada, exceções, GIC e timer.
- [FDT e política de memória](fdt-resources.md).
- [Formato S21R10](payload-format.md): empacotador e validação.
- [Carregador EL2 no QEMU](qemu-el2-loader.md): materialização, main real e recusas.
- [Validação anterior](validation-2026-10-20.md) e [revisão histórica de 21/10](repository-review-2026-10-21.md).

- [Revisão atual do projeto e próximos passos](repository-review-2026-10-25.md): baseline rerodado, cobertura condicionada ao ELF, CI e prioridade do diagnóstico observável.

## Evidências do aparelho e fontes externas

- [Download USB e PIT observados](download-pit-observation-hzc2.md): sessão Heimdall concluída no Mint, 48 entradas e destinos boot/vendor_boot/recovery identificados; sem carga própria ou aquisição de RAM.
- [Transição de estado LK e pedido de wipe](lk-device-state-switch-hzc2.md): 238 palavras GNU, literal completa e chamada de armazenamento antes do setter; [links Android e geometria negada](runtime-collection.md#links-de-armazenamento-e-sete-leituras-negadas--2026-10-30), sem executar transição.

- [ASV/GEN, n e W19](newtime-asv-gen-hzc2.md): GEN após dois u32, n=13, caminho habilitado candidato, subkeys e pedidos SMC corrigidos; posições e condições de preservação.
- [Gate ECT, retorno e reserva corrigida](newtime-ect-gate-hzc2.md): testes X64/W32, SMC opacos, assinatura atual, continuidade condicional e descritor16 antes do incremento total+4.

- [Slot 38 e máscara da coluna 13](newtime-slot38-hzc2.md): folha de 13 palavras, dois produtores nominais do ponteiro, máscara comum e cinco caminhos u8 condicionais; efeito de um byte e aliases abertos.
- [Buffer do slot38 e restauração](newtime-slot38-buffers-hzc2.md): colunas 6/7, 88 perfis completos, janelas delimitadas e seis cópias; restauração condicional, sem excluir efeitos do método +56.
- [Método +56, fila e resposta](newtime-method56-hzc2.md): binding nominal até comando6, palavra runtime low24, publicação/espera e limites da restauração; GNU207/14/107 e 32 testes.
- [Comando6: ACPM, FVP e DVFS](newtime-command6-hzc2.md): canal1 e pares de filas, receptor FVP, serviço plugin7 e projeção do header; 25 testes e GNU814/932/112/10/96.
- [Valor efetivo FVP](newtime-fvp-effective-hzc2.md): máximo unsigned, limite posterior, indicadores anteriores ao limite, releitura e retorno sem rollback local; 28 testes e4608 fixtures sobre palavras Thumb cruas.
- [Receptor DVFS e auditoria GLM](newtime-dvfs-receiver-hzc2.md): modo0/callback, primeira falha não agregada, dados vivos do init, limiar sem recusa e broadcast exclusivo; 28 regressões próprias e47 externas reproduzidas com limites.

- [Hardware](../EXYNOS2100_HARDWARE.md) e [firmware stock HZC2](stock-firmware-hzc2.md).
- [Fontes Samsung e READMEs recebidos](samsung-reference.md).
- [Kernel público xfwdrev/rebased-11](xfwdrev-kernel-reference.md): revisão fixada, comparação de fontes, três compilações DTS e dois overlays no host; sem build completo ou observação física.
- [Menções BL2 e consumidores no kernel](bl2-kernel-consumers-hzc2.md): registro DRAM em 0x02073600, constante comum ao BL2, bootstat e gate CHIPID; sem valores runtime.
- [NEWTIME e argumentos bootstat](boot-metadata-hzc2.md): callback nominal, ponteiro mutável/alias condicional do registro DRAM e literal 100 no campo BL1; GNU de 156 palavras, sem medições físicas.
- [Publicação ACPM e NEWTIME](acpm-handshake-hzc2.md): produtor Thumb de 0x38e00, confirmação zero e comparação DRAM no payload; DTS fixado, GNU AArch64/Thumb e aliases/preservação condicionais.
- [ECT/NEWTIME e primeira escrita](newtime-ect-hzc2.md): 57 descritores, 22 seletores incluindo 0xcafe, parser/prefixo originais em 56 casos QEMU; 80 testes e GNU de 353 palavras, sem estado físico.
- [Registro NEWTIME e erros posteriores](newtime-record-hzc2.md): layout de 0x2400 bytes, gate reamostrado, alocador e erro 4 sem rollback; 11264 combinações no modelo, 196 casos QEMU com ramos explícitos e seis da folha do alocador. Sem amostras MMIO ou registro físico.
- [Erro NEWTIME, dump e depuração](newtime-error-hzc2.md): flags em +0x24, dump de 104 palavras e console nominal; 26 casos do dump/14 do fragmento de flags no QEMU, 101 testes e GNU de 662 palavras. Efeitos completos e estado físico abertos.
- [Empacotamento da geometria após o marcador](bl2-geometry-packing-hzc2.md): quatro slots zerados/reconstruídos, extensão 0x31 e modos do slot 0/3; 100 cenários QEMU com retornos fornecidos mais 100 execuções da folha, 111 testes e GNU de 386 palavras. Sem respostas físicas.
- [Segunda publicação da geometria](bl2-geometry-publication-hzc2.md): slot → wrapper → ponteiro R, cópia fixa e duas amostras distintas; 160 cenários QEMU com MMU sintética e chamadas originais, 119 testes e GNU de 464 palavras. Sem alias ou registro físico observado.
- [DRAM observada no bugreport HZC2](dram-observed-hzc2.md): Samsung/D1Z, 12GB e assinatura B; campos distintos da igualdade usada no driver, extrator com lista de permissão e seis casos dos getters LK.
- [Colunas 1 e 12 da NEWTIME](newtime-columns-hzc2.md): chaves de subtabelas, leitores estáticos e quatro execuções contínuas com parada antes do gate, sem respostas MMIO; parâmetros físicos ainda abertos.
- [Transportes da célula NEWTIME](newtime-transports-hzc2.md): sete cópias fixas sem interseção, 47 referências parametrizadas e três origens examinadas; despacho/X0 abertos.
- [Argumentos das cópias NEWTIME](newtime-copy-arguments-hzc2.md): 47 referências revisadas, wrappers e índices assinados; ponteiros de canal/metadados ainda abertos, sem transporte comprovado da célula.
- [Origem dos canais NEWTIME](newtime-channel-origins-hzc2.md): escritor concreto das quatro bases, chamada nominal via slot 18 e descritores de registro/recuperação; preservação e metadados reais continuam abertos.
- [Slot 20 e origem de X5](newtime-slot20-hzc2.md): nove chamadas nominais, sete X5 zero e duas com buffer calculado de 64 bytes; novas buscas limitadas não resolvem o slot 47.
- [MARGIN e filtro dos consumidores](newtime-margin-hzc2.md): duas matrizes de 13×12, publicação do handle e tabela de nomes corrigida; tags 255 pulam a store em Q no caminho preservado.
- [Resultado secundário de 0x1a804](newtime-secondary-result-hzc2.md): identidade Q=B nos caminhos rápidos, metadados u16 e interação das stores de correção.
- [Chamada MIF e bins NEWTIME](newtime-mif-bins-hzc2.md): tabela de 13 limiares, X0/X1 na chamada e contrato de saída corrigido após auditoria dos anexos.
- [Continuação comum NEWTIME](newtime-common-continuation-hzc2.md): 227 PCs, sete chamadas e layout de palavras/bytes; bases e efeitos numéricos ainda condicionais.
- [Dois switches e entradas relativas](newtime-jump-tables-hzc2.md): arrays em 0x30108/0x30130, 25 entradas e 16 destinos distintos; continuação comum e callbacks preservados como fronteiras.
- [Auditoria do slot 47](newtime-slot47-hzc2.md): candidatos de outra base descartados, cobertura LDR/LDP e semântica de X0 zero; origem verdadeira ainda aberta.
- [Binding NEWTIME até a SMC](newtime-smc-binding-hzc2.md): inicializador concreto, método +72 e endereços candidatos pela convenção pública SFR_W; sem chamada ao monitor.
- [Recargas e bindings NEWTIME](newtime-reloads-hzc2.md): outro leitor da coluna 1, 15 envios indiretos, escritores de 0x31998 e bases MMIO mutáveis; GNU324, sem nova execução.
- [Plano NEWTIME consolidado](newtime-plan-consolidated-hzc2.md): referência atual após substituição das seções 2.8–2.13 do plano recebido, PCs de despacho precisos, pendências e limite de execução preservado.
- [Consumidores NEWTIME e vddcal](newtime-consumers-hzc2.md): leitor da coluna 12, escritor de 0x31c30, fluxo 108→162 bytes, slots nominais e limites do diretório vddcal; análise estática, GNU1171 e 53 testes.
- [Proveniência dos binários grandes](binary-provenance.md): 17 arquivos de pelo menos 5 MiB, hashes/blobs, matches de .deb locais e digest de asset oficial; limites de autenticação explícitos.
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

- [Configuração LK após a cópia](lk-postcopy-policy-hzc2.md): CP debug, informações ao monitor e proteção nominal de fingerprint; aceitação da Image permanece aberta.

- [Origem do bitmap de política LK](lk-policy-bitmap-hzc2.md): transporte nominal de 32 bytes do contexto de token às consultas CP/fingerprint; valores reais desconhecidos.

- [Escritor dos bits de modo do token](lk-token-modes-hzc2.md): comando 21, lista limitada e acumulação OR; erros locais não demonstram publicação global.

- [Boot HZC2 observado no bugreport](bugreport-boot-hzc2.md): intervalos SEC_DRAM/SEC_PGTBL/Harx, ramo de prefixo do token e cenário condicional de bancos; extrato por lista de permissão.

- [Banco zero no editor FDT HZC2](lk-zero-bank-editor-hzc2.md): código original aceita reg de tamanho zero em fixture; edições parciais e retorno final que pode ocultar falha de reg, com 16 casos QEMU.

- [Alteração PSCI no FDT pelo LK](lk-psci-final-edit-hzc2.md): edição condicional smc→hvc, mensagem observada no boot e 24 casos QEMU; método da base estática não é o método final certificado.

- [Observação NEWTIME no gate](newtime-gate-observation-scope-hzc2.md): snapshots no runner com preflight preservado; ponteiro e scratch ff inalterados, predição de scratch zero refutada, sem execução após o gate.
