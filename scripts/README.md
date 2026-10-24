# Catálogo de scripts

Execute a partir da raiz do repositório. Os comandos de validação estão no [README principal](../README.md).

| Grupo | Arquivos | Uso |
|---|---|---|
| Regressão | `regress.sh`, `test_pr_fixes.sh`, `test_r10_stage.sh` | R8/R9 e testes de componentes R10/UART/atômicos |
| FDT e contêiner | `test_fdt.py`, `test_payload.py`, `test_payload_stage.py`, `test_payload_loader.py` | Modelos sanitizados e handoff real no QEMU |
| Ambiente | `bootstrap_tools.sh`, `cross-run.sh`, `run_qemu.sh` | Ferramentas locais e execução dos módulos |
| Laboratório XNU | `run_xnu_lab.py`, `test_xnu_lab.py` | Init próprio no QEMU com prebuilt fixado; caso positivo, controle negativo e verificações de host; [reprodução](../docs/xnu-qemu-lab.md) |
| Contrato XNU | `capture_xnu_contract.py`, `test_xnu_contract.py` | Layout C/28 testes de host; captura de argumentos e árvore por GDB no QEMU, seguida de retomada até PASS; [escopo e reprodução](../docs/xnu-boot-contract.md) |
| Recursos XNU | `inspect_xnu_fdt.py`, `test_xnu_fdt_adapter.py` | FDT → fragmento Apple, parser C sanitizado e 29 testes; sem gerar boot_args ou plano físico; [contrato](../docs/xnu-fdt-adapter.md) |
| Contrato de vídeo XNU | `run_xnu_video_lab.py`, `test_xnu_video.py` | Captura no kernel, reserva do framebuffer, 25 critérios gráficos, 22 sem vídeo e três recusas; [guia](../docs/xnu-video-contract.md) |
| Display ramfb QEMU | `check_xnu_ramfb.py` | Seis controles prebuilt/rebuild/correção DMA; capturas PNG nativas e recusas de erro/timeout; [guia](../docs/xnu-ramfb-audit.md) |
| Consumidor EFI XNU | `run_xnu_adapter_lab.py`, `test_xnu_efi_resources.py`, `test_xnu_efi_memory.py` | Build do loader, recursos e reservas UEFI; 22 critérios positivos, oito recusas, 22 testes de memória/evidência e 16 de recursos; [reprodução e mapas](../docs/xnu-uefi-memory.md) |
| Userland no consumidor EFI | `run_guarded_userland.py`, `verify_guarded_userland.py`, `check_guarded_userland_capture.py`, `test_xnu_userland_profile.py` | Perfil fixo, auditoria física somente de leitura, replay independente, três recusas e retorno nativo; [guia](../docs/xnu-guarded-userland.md) |
| Preparação HackiOS | `check_hackios_userland.py` | Reproduz colisão/modos dos jobs e falhas Bash com entradas sintéticas; gera patch sem alterar o checkout; [evidências](../docs/hackios-userland-host.md) |
| Inspeção atual | `inspect_proton.py`, `inspect_sboot_hzc2.py` | ZIP Proton e relatório somente leitura do sboot HZC2 identificado por SHA-256 |
| Forense legada | `parse_fdt.py`, `abl_triage.py` | Leitores ainda não auditados; não usar como única evidência |
| Experimentos históricos | `build_kit*.sh`, `snapshot_project.sh`, `mk_append_r9.py`, `test_delta*`, `test_header_qemu.sh`, `kit-assets/`, `magiskboot/` | Kits DAY1/DAY2, repack e experiências anteriores; fora do fluxo atual validado |

Os scripts históricos foram mantidos no lugar para preservar referências e caminhos. Alguns usam `/home/z/my-project` ou dependem de downloads antigos; não são comandos de reprodução atuais. Em particular, o conteúdo descrito por `snapshot_project.sh` inclui `.env`: não usar esse snapshot como pacote público sem revisar sua seleção de arquivos. A organização não executou repacks, instaladores ou scripts de flash.

O empacotador atual está em `../tools/mkpayload.py`; não confundir com versões do branch kilo. O carregador de teste usa uma CPU e não verifica SMP.

- `test_entry_diag.py`: seis execuções do diagnóstico Image em QEMU (EL1/EL2 e três endereços); [contrato e limites](../docs/entry-diagnostic.md).

- `inspect_uart_reference.py`: leitura somente do Kernel.tar.gz identificado por hash; cruza UART0/UART1, pinctrl e syscon sem extrair o pacote.

- `collect_uart_state.sh`: coleta atributos UART/MUIC candidatos pelo shell Android/rish, sem writes no sysfs; cria relatório sem sobrescrever.

- `inspect_snapshot_log.py` e `test_snapshot_log.py`: leitor offline de header+log debug-snapshot e casos sintéticos; sem aquisição de memória do aparelho.

- `collect_boot_logs.sh`: consulta last_kmsg/first_kmsg/sec_log; captura limitada a 2 MiB/5 s por arquivo, cria pasta nova e gera report.txt.

O teste `test_entry_diag.py` inclui seis recusas (C, M e M|C em EL1/EL2), com tradução identidade read-only e AT/PAR nos casos MMU. O padrão executa 12 casos; `--all-offsets` combina 128 entradas aceitas e seis recusas.

- `check_uart_clock_evidence.py`: cruza sboot HZC2 com quatro fontes de clock identificadas por hash; verifica frequência nominal, seletores, UBRDIV e inventário de gates/QCH. Não lê hardware ou produz writes; [detalhes](../docs/uart-gates.md).

- `check_lk_v3_layout.py` e `test_lk_v3_layout.py`: modelo offline das cópias kernel/ramdisk e células de initrd do LK HZC2; requer imagens raw v3 e deslocamento explícito. `--fdt` compara chosen, com limite de 2 MiB e recusa de duplicidades. Não empacota nem verifica bootabilidade; [escopo](../docs/lk-v3-layout.md), [escritas dinâmicas](../docs/lk-dynamic-fdt.md).

- `check_lk_dtb_selection.py` e `test_lk_dtb_selection.py`: seleção por revisão explícita, validação das tabelas e resolução de símbolos DPM na base. Auditoria somente leitura, sem aplicar overlays ou produzir FDT final; [pipeline e teste separado com libfdt](../docs/lk-dtb-pipeline.md).

- `inspect_el2_hzc2.py` e `test_el2_hzc2.py`: relatório somente leitura de sboot/uH/Harx HZC2, com leitura limitada e identidade SHA-256 obrigatória. Liga os comandos uH aos handlers, registra soc_info e decodifica os retornos constantes do serviço de memória Harx. Não executa serviços nem fornece mapa de RAM. [Evidências](../docs/el2-earlymem-hzc2.md), [intervalo Harx e limites do decodificador](../docs/lk-harx-memory-gap.md).

- `check_lk_uh_ranges.py` e `test_lk_uh_ranges.py`: reproduzem os argumentos enviados pelo percurso LK dos nós com prefixo memory, com perfil explícito de células 2/1. Preservam a ordem e ignoram as tuplas de reg após a primeira, conforme o ramo rastreado. Não chamam HVC, simulam o alocador ou verificam memória livre; [escopo e limites](../docs/lk-uh-range-registration.md).

- `check_harx_log_evidence.py` e `test_harx_log.py`: cruzam seis fontes Samsung, IKCONFIG da Image stock e nó EL2 no DTB base, com hashes obrigatórios. Testam limites gzip/config e o coletor abaixo; [evidências](../docs/harx-log-observation.md).

- `collect_el2_log.sh`: uma captura do atributo sysfs exynos_el2_log, até 4096 bytes/5 s. A leitura pode avançar o cursor Harx; não escreve no atributo, não reseta e não repete páginas/aliases. Execução recebida: nó presente, UNREADABLE no shell, sem captura; não repetir nas mesmas condições.

- `inspect_sec_pgtbl_hzc2.py` e `test_sec_pgtbl_hzc2.py`: verificam identidades sboot/LDFW, percorrem seis registros e rastreiam a entrega ao monitor. `--drm-header` valida o header Samsung por hash e extrai 52 constantes; não as atribui à consulta. Modelo opcional de respostas X0; 20 testes de host. [Contratos distintos e reprodução](../docs/sec-pgtbl-hzc2.md).
- `emulate_sec_pgtbl_hzc2.py`: dependência opcional Unicorn 2.1.4; executa somente o chamador LK original com SMC substituído e printf omitido. `--self-check` confere 144 cenários básicos; com `--drm-header`, acrescenta 104 injeções hipotéticas das palavras do enum. Total 248, com páginas/PCs/tempo/instruções limitados. Não executa serviços ou decifra o DRM.

- `check_lk_memory_banks.py` e `test_lk_memory_banks.py`: evidência do construtor RAM HZC2 e modelo das chamadas ao escritor com nove entradas explícitas; JSON limitado, aritmética X/W e limite de 128 chamadas no host. 17 testes novos, 44 na suíte LK. Não produz FDT ou autoriza memória livre; [contrato](../docs/lk-memory-bank-constructor.md).
- `emulate_lk_memory_banks.py`: Unicorn opcional; confere as instruções originais em 268 cenários fornecidos. Substitui SMC/getter/Harx, omite preparação FDT e captura as chamadas ao editor, com três páginas RX, pilha separada e orçamento por caso. Não executa o editor ou o provedor seguro.

- `check_lk_cache_handoff.py` e `test_lk_cache_handoff.py`: evidência HZC2 e modelo do gate de cache, seleção SCTLR por EL e operandos legados set/way; nove entradas explícitas, JSON limitado e 14 testes novos. [Escopo](../docs/lk-cache-handoff.md).
- `emulate_lk_cache_handoff.py`: Unicorn opcional; 352 cenários executam instruções originais até o BLR, parando num destino sintético. Acessos de sistema/DC/barreiras substituídos ou registrados, três chamadas externas omitidas. Não modela tradução/cache suja ou demonstra estado final no telefone.

- `inspect_lk_final_edges.py` e `test_lk_final_edges.py`: inventário limitado das chamadas finais HZC2, expansão declarada do formatador/tabela/lista e operações de sistema. 15 testes novos mais 14 do helper; não executa firmware ou resolve o SMC. [Guia e limites](../docs/lk-final-edges.md).

- `inspect_monitor_preparation.py` e `test_monitor_preparation.py`: argumentos dos wrappers BL2, censo B/BL dos helpers de lista e gates constantes no sboot HZC2 exato. 14 testes novos; não executa SMC ou demonstra lista/retornos reais. [Evidência e limites](../docs/monitor-preparation-hzc2.md).

- `inspect_bl2_service_chain.py` e `test_bl2_service_chain.py`: seletor BL2 a partir de X2 explícito, intérprete restrito dos stores do pedido -0xe6 e referências ADRP/pointer iniciais. Campos não escritos ficam desconhecidos; 24 testes novos, sem SMC/MMIO ou escrita física. [Contrato e limites](../docs/bl2-service-chain-hzc2.md).

- `inspect_descriptor_provenance.py` e `test_descriptor_provenance.py`: sete loops fixos de cópia, duplicatas do construtor e testemunhos MOVZ/MOVK; não provam inicialização ou censo geral de escritores. 16 testes novos e 24 regressões. [Escopo e fronteiras](../docs/descriptor-provenance-hzc2.md).

- `inspect_epbl_preparation.py` e `test_epbl_preparation.py`: prefixo EPBL, pedido in-place, hipótese nominal de ponteiros e aritmética do dispatcher comum com guarda separada. 18 testes novos; não decifra, executa MMIO ou resolve handlers. [Guia e limites](../docs/epbl-preparation-hzc2.md).

- `inspect_epbl_frontier.py` e `test_epbl_frontier.py`: grafo do prefixo EPBL com cortes antes dos bytes pendentes, expansão de uma tabela fixa e corroboração dos dois produtores de VBAR. 18 testes novos; retorno normal e viabilidade são hipóteses, sem arestas de exceção. [Escopo](../docs/epbl-frontier-hzc2.md).

- `inspect_epbl_protocol.py`, `check_epbl_protocol_gnu.py` e `test_epbl_protocol.py`: buffers/transferências, 177 acessos MMIO, seletores e polling do EPBL HZC2. 33 testes novos; conferência independente de endereços pelo texto GNU. Relatório exige firmware exato, preserva desconhecidos e não executa MMIO, decifra ou liga handlers. [Protocolo e hipóteses](../docs/epbl-protocol-hzc2.md).
