# Catálogo de scripts

- `inspect_lk_payload_return.py` e `test_lk_payload_return.py`: resumos estáticos
  do retorno nominal da Image, wrapper e saída da thread; hash exato,
  GNU294/57/58 e 14 testes novos. Chamadas opacas mantêm apenas continuação
  condicional, sem inventar valores de pilha ou executar firmware.
  [Conclusão e reprodução](../docs/lk-payload-return-hzc2.md).

- `inspect_lk_rdx_memory_hzc2.py` e `test_lk_rdx_memory.py`: origem estática dos
  bancos relativos `0xcd31d0`, pares exportados e binding nominal DWC3;
  hash exato, GNU839/202/85 e 16 testes de host. Exemplos de quantidade são
  fornecidos no host; não executam firmware ou demonstram retenção.
  [Conclusão e reprodução](../docs/lk-rdx-memory-origin-hzc2.md).

- `inspect_lk_dump_hzc2.py` e `test_lk_dump.py`: análise estática fixada por
  hash dos templates/descritores RDX, gates selecionados e encaminhamento
  nominal de bytes. GNU488/103alvos/61operandos, 14 testes de host;
  [limites de aquisição e retenção](../docs/lk-dump-export-hzc2.md).

- `inspect_entry_record.py` e `test_entry_record.py`: inspeção offline de
  128 bytes S21ENTRY, referência Image, endereços e snapshot opcional;
  17 testes de host e integração aos seis registros/seis recusas do QEMU.
  Origem e frescor não são autenticados. [Contrato e exemplo](../docs/samsung-diagnostic-contract.md).

- `validate_baseline.py` e `test_baseline_runner.py`: build R10 em diretório
  novo, cobertura obrigatória host/QEMU, logs/resumo JSON e sete controles
  de falha do runner. [Uso e CI](../docs/baseline-validation.md).

- `inspect_newtime_reloads_hzc2.py`: outro leitor da coluna 1, recargas e
  bindings; [relatório](../docs/newtime-reloads-hzc2.md).
- `inspect_newtime_smc_binding_hzc2.py` e `test_newtime_smc_binding.py`:
  inicializador até folha SMC nominal e convenção pública SFR_W;
  [limites](../docs/newtime-smc-binding-hzc2.md).
- `inspect_newtime_slot47_hzc2.py` e `test_newtime_slot47.py`: inventário
  limitado LDR/LDP e bases distintas; [auditoria](../docs/newtime-slot47-hzc2.md).
- `inspect_newtime_transports_hzc2.py` e `test_newtime_transports.py`:
  projeção dos sete laços fixos e referências parametrizadas;
  [origem de X0 ainda aberta](../docs/newtime-transports-hzc2.md).

- `inspect_newtime_consumers_hzc2.py` e `test_newtime_consumers.py`: leitor
  da coluna 12, direção do fluxo 108→162 bytes, slots de funções e diretório
  candidato de vddcal. Exigem ambos os hashes; GNU1171, modelos de palavras
  fornecidas e buscas limitadas. [Escopo](../docs/newtime-consumers-hzc2.md).

- `inspect_newtime_columns_hzc2.py`, `trace_newtime_columns_qemu.py` e
  `test_newtime_columns.py`: colunas 1/12 como chaves de subtabelas,
  consumidores estáticos, GNU188 e preflight de cada acesso de memória
  do callback contínuo, parando antes do gate. Quatro casos QEMU, sem
  fornecer MMIO ou reescolher PC. [Escopo](../docs/newtime-columns-hzc2.md).

- `inspect_bugreport_dram.py`, `inspect_dram_logging_hzc2.py`,
  `emulate_lk_dram_labels_qemu.py` e `test_bugreport_dram.py`: extrato técnico
  do ZIP exato por lista de permissão, cache/rótulos LK, comparação com o
  driver público e seis casos dos helpers originais em MMU sintética.
  [Escopo e reprodução](../docs/dram-observed-hzc2.md).
- `audit_large_binaries.py`: inventário verificável dos arquivos rastreados
  de pelo menos 5 MiB e correspondência com pacotes/asset fixados.
  [Limites da proveniência](../docs/binary-provenance.md).

- `inspect_bl2_geometry_publication.py`, `check_bl2_geometry_publication_gnu.py`,
  `emulate_bl2_geometry_publication_qemu.py` e `test_bl2_geometry_publication.py`:
  segunda chamada NEWTIME, duas amostras, destinos fixo/R e contador.
  160 casos QEMU com MMU sintética, chamadas originais até primeira escrita
  ou erro do prefixo; sem reatribuir registradores de endereço.
  119 testes e GNU de 464 palavras.
  [Escopo e reprodução](../docs/bl2-geometry-publication-hzc2.md).

- `inspect_bl2_geometry_packing.py`, `check_bl2_geometry_packing_gnu.py`,
  `emulate_bl2_geometry_packing_qemu.py` e `test_bl2_geometry_packing.py`:
  zero/empacotamento dos quatro slots, extensão seletiva e modo final.
  QEMU executa blocos originais com retornos de chamadas fornecidos,
  sem executar BLR/BL nessas arestas, depois a folha original de tamanho.
  100 cenários, 111 testes e GNU de 386 palavras.
  [Escopo e reprodução](../docs/bl2-geometry-packing-hzc2.md).

- `inspect_newtime_error_hzc2.py`, `check_newtime_error_gnu.py`,
  `emulate_newtime_error_qemu.py` e `test_newtime_error_hzc2.py`: helper de
  erro, flags +0x24, dump e depuração HZC2. GNU de 662 palavras; 26 dumps no QEMU
  com conversor original/saída em RAM e 14 fragmentos de flags com X3
  fornecido pelo harness. Sem UART/MMIO ou helper completo executados.
  [Escopo e reprodução](../docs/newtime-error-hzc2.md).

- `inspect_newtime_record_hzc2.py`, `check_newtime_record_gnu.py`,
  `emulate_newtime_record_qemu.py` e `test_newtime_record_hzc2.py`: layout,
  alocador, sequência de gates, erros parciais e wrapper NEWTIME HZC2.
  Modelo de 11264 combinações; QEMU executa blocos originais com despacho
  explícito dos ramos, sem executar o gate MMIO. GNU de 623 palavras.
  [Escopo e reprodução](../docs/newtime-record-hzc2.md).

- `inspect_newtime_hzc2.py`, `check_newtime_gnu.py`,
  `emulate_newtime_qemu.py` e `test_newtime_hzc2.py`: sboot HZC2 exato,
  leitor ECT/NEWTIME com limites, 353 palavras GNU, parser original e
  prefixo até a primeira escrita em 56 casos QEMU. Bindings de laboratório;
  sem executar a inicialização Samsung ou o restante do callback.
  [Escopo e reprodução](../docs/newtime-ect-hzc2.md).

- `inspect_acpm_handshake_hzc2.py` e `check_acpm_handshake_gnu.py`: exigem
  sboot HZC2 e DTS público fixados por tamanho/SHA. Produtor Thumb de
  0x38e00, consumidor BL2 e critério NEWTIME; GNU de 100 palavras AArch64
  e 141 instruções Thumb. Sem executar firmware ou confirmar aliases.
  [Escopo e reprodução](../docs/acpm-handshake-hzc2.md).

- `inspect_boot_metadata_hzc2.py` e `check_boot_metadata_gnu.py`: somente
  sboot HZC2 exato; callback NEWTIME, ponteiro mutável/alias condicional do
  registro DRAM e argumentos bootstat. GNU: 156 palavras/26 alvos/39
  operandos. Sem valores de registrador opcionais ou firmware executado.
  [Escopo e reprodução](../docs/boot-metadata-hzc2.md).

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

- `test_entry_diag.py`: 12 casos do diagnóstico Image em QEMU (seis entradas EL1/EL2 em três endereços e seis recusas M/C); [contrato e limites](../docs/entry-diagnostic.md).

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

- `check_epbl_hash_sources.py` e `test_epbl_hash_sources.py`: comparação de cinco fontes fixadas por SHA-256/blob Git, pré-processamento ACE v6 e parser restrito de macros/switch. Doze testes novos, mais dois de ligação dos contadores no protocolo (35 atuais). Dez offsets e dialecto DMA corroborados, sem importar o algoritmo 0x19 ou executar o emulador. [Escopo](../docs/epbl-hash-provenance-hzc2.md).

- `inspect_tzar_hzc2.py`, `check_tzar_crypto_gnu.py` e `test_tzar_hzc2.py`: arquivo interno TZAR do HZC2 exato, LZ4 limitado em memória, 44 registros e recortes ELF64 da fronteira criptográfica. Quinze testes; GNU confere 15 símbolos, 127 palavras e 34 destinos relativos. Exige `liblz4` no host; sem executar firmware ou atribuir algoritmo ao EPBL. [Escopo e reprodução](../docs/tzar-crypto-hzc2.md).

- `inspect_teegris_ioctl.py`, `check_teegris_ioctl_gnu.py` e `test_teegris_ioctl.py`: contrato ELF versionado e chamada SVC do ioctl TEEGRIS HZC2. Leitura limitada de DYNAMIC/RELA/VERSYM/VERNEED/VERDEF, PLT e aritmética de retorno explícito. Quinze testes novos e 15 regressões TZAR; GNU confere metadados e 24 palavras/quatro destinos. Sem resolução de símbolos ou execução de syscall observada. [Escopo](../docs/teegris-ioctl-boundary-hzc2.md).

- `inspect_tzsw_bien.py` e `test_tzsw_bien.py`: envelope TZSW HZC2 exato e validação de candidato completo contra o original. Quinze testes; ensaio opcional com quatro fontes Exynos9830 fixadas por SHA-256/blob, AST sem executar fontes, cryptography/OpenSSL. A hipótese falhou no digest HZC2; nenhum plaintext emitido. `--candidate` inválido sai com código 1 e JSON de recusa; erros estruturais saem com 2. [Escopo](../docs/tzsw-bien-hzc2.md).

- `inspect_lk_panic_recovery.py`: [analisador estático de panic/contexto](../docs/lk-panic-recovery-hzc2.md): parada local ou ERET para contexto salvo; aquisição RDX não demonstrada.

- [Configuração LK após a cópia](../docs/lk-postcopy-policy-hzc2.md): CP debug, informações ao monitor e proteção nominal de fingerprint; aceitação da Image permanece aberta.

- [Origem do bitmap de política LK](../docs/lk-policy-bitmap-hzc2.md): transporte nominal de 32 bytes do contexto de token às consultas CP/fingerprint; valores reais desconhecidos.

- [Escritor dos bits de modo do token](../docs/lk-token-modes-hzc2.md): comando 21, lista limitada e acumulação OR; erros locais não demonstram publicação global.

- [Boot HZC2 observado no bugreport](../docs/bugreport-boot-hzc2.md): intervalos SEC_DRAM/SEC_PGTBL/Harx, ramo de prefixo do token e cenário condicional de bancos; extrato por lista de permissão.

- [Banco zero no editor FDT HZC2](../docs/lk-zero-bank-editor-hzc2.md): código original aceita reg de tamanho zero em fixture; edições parciais e retorno final que pode ocultar falha de reg, com 16 casos QEMU.

- [Alteração PSCI no FDT pelo LK](../docs/lk-psci-final-edit-hzc2.md): edição condicional smc→hvc, mensagem observada no boot e 24 casos QEMU; método da base estática não é o método final certificado.

- [Observação NEWTIME no gate](../docs/newtime-gate-observation-scope-hzc2.md): snapshots no runner com preflight preservado; ponteiro e scratch ff inalterados, predição de scratch zero refutada, sem execução após o gate.
