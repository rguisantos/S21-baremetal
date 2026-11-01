# Catálogo de scripts

`check_capture_a0_modules.py` inventaria os módulos do vendor_boot original e compara seus requisitos de CRC com um Module.symvers opcional. `capture_a0_modules.py` lê gzip/CPIO/ELF sem extrair arquivos nem carregar módulos; 25 controles em `test_capture_a0_modules.py`. [Guia](../docs/capture-a0-modules-hzc2.md).

`check_capture_a0_repack.py` repete o repack fixado com três mtimes por imagem e separa diferenças dentro/fora do hash original. Recusa inputs sem os hashes fixados; retorno 2 mantém o gate reprovado. `test_capture_a0_repack.py` cobre os limites com 12 testes sintéticos. [Guia](../docs/capture-a0-repack-extent-hzc2.md).

`check_capture_a0_kmi.py` confere arquivo Samsung/IKCONFIG por hash, faz censo
literal de identificadores e compara listas KMI/whitelist; seis controles com
gerador/headers originais usam fixtures host próprias. `test_capture_a0_kmi.py`
tem 23 testes de limites/recusas na CI. O runner retorna 2 para lacunas de
insumos e não afirma compatibilidade de CRC/módulo. [Guia](../docs/capture-a0-kmi-hzc2.md).


O [A0 offline HZC2](../docs/capture-a0-hzc2.md) usa `check_capture_a0.py` e
`capture_a0_formats.py`: inputs fixados por hash, inventário Android v3/DT-table,
IKCONFIG e verificação de hash descriptors AVB, sem assinatura ou dispositivo.
`test_capture_a0.py` tem 32 controles sintéticos na CI. O runner gera relatório
mesmo quando o repack reprova, retornando 2 nesse caso; somente diretórios novos.
A reconstrução integral do inventário não aceita payload alterado.

O [caminho candidato IOCC do UFS](../docs/lk-ufs-iocc-hzc2.md) agora separa bypass PHY e coerência: a tabela alternativa com consulta1 usa endereço/máscara compatíveis com o FlopKernel. OR preserva bits antigos; consultas distintas podem combinar tabela e máscara. São32 casos originais em QEMU com alvos em RAM e26 testes novos, sem prova de DMA físico.

A [entrada LK e o granule herdado](../docs/lk-entry-granule-hzc2.md) foram ensaiados com código original: EL2h desce para EL1h, EL1t é preservado e o TCR fornecido permanece intacto. O getter retorna4/64/16KiB conforme TG0; o perfil4KiB continua condicionado. São24 entradas,48 chamadas do getter em QEMU e14 testes novos.

O [produtor local do magic DVFS](../docs/newtime-dmc-magic-hzc2.md) foi confirmado em `0x369a0`: publica `0xabcd1234`, toca a campainha do canal3 e espera limpeza externa. A reprodução corrige a identificação do trecho como EL3 e limita a alegação de escritor único. São22 testes novos, mais14 da referência ACPM/ECT com oito fontes FlopKernel.

A [construção da tradução do pool UFS](../docs/lk-pool-mmu-hzc2.md) foi conferida: no perfil EL1/4KiB, as 3043 páginas têm identidade de estágio1 e atributos normais cacheáveis, RW/PXN. O código original gerou as tabelas previstas em seis casos QEMU; 21 testes novos. Granule herdado, estado vivo e coerência DMA continuam separados.

O [pool que abastece o heap UFS](../docs/lk-heap-pool-hzc2.md) foi ligado ao provedor de páginas: faixa nominal `[0xe8c1d000,0xe9800000)`, com 3043 páginas. São 28 casos do código original em QEMU, incluindo falha que mantém o host publicado sem buffers; 17 testes novos. Estado físico e identidade DMA continuam pendentes.

A [origem do host e buffers UFS](../docs/lk-ufs-host-memory-hzc2.md) está ligada nominalmente ao alocador e às tabelas locais, com 19 testes novos. O cruzamento ampliado com FlopKernel esclarece PRDT em bytes, DMA e seleção de driver UART. Alinhamento e stores de endereços permanecem separados da coerência física.

A [preparação e conclusão UFS do LK](../docs/lk-ufs-completion-hzc2.md) agora liga LUN68→0xc4, descritores, polling e publicação do status SCSI. São635 palavras GNU e21 testes novos. Os retornos de espera, OCS, SCSI e autenticação RPMB foram separados; conclusão física e persistência seguem sem observação.

O [registro e transporte RPMB do LK](../docs/lk-rpmb-transport-hzc2.md) agora ligam nominalmente `scsirpmb` aos wrappers, callbacks SCSI IN/OUT e entrada UFS. São992 palavras GNU e16 testes novos. Instalação ativa, host, completion e persistência continuam sem observação física.

A [referência FlopKernel Exynos2100](../docs/flop-kernel-reference.md) confirma o layout RPMB com probe C do host e acrescenta um leitor offline de frames, com 26 testes novos. Revisão fixada em `4553117`; suporte de fonte para p3s confirmado. Interfaces Linux/monitor/LK e estado do aparelho permanecem separados.

O [backend RPMB dos contadores](../docs/lk-rpmb-hzc2.md) está ligado aos pacotes locais, callbacks `scsirpmb` e pedidos seguros de nonce/MAC. A análise confere 1.156 palavras GNU e 16 testes novos; distingue revisões de rollback, contador de escrita e efeitos anteriores aos testes de autenticação. Persistência e implementação segura continuam abertas.

Os [verificadores Samsung chamados pelas partições](../docs/lk-samsung-checks-hzc2.md) agora têm papéis separados: seleção/pedido de assinatura ao monitor, comparação de revisão para rollback e política de binário personalizado. São 801 palavras GNU e 16 testes novos. Retornos zero, fallbacks e efeitos de política foram distinguidos da aceitação física de uma Image.

A [conferência de Build-id e os helpers de partições](../docs/lk-build-id-partitions-hzc2.md) estão delimitados localmente. O checker compara um prefixo entre caches atribuídos a vbmeta/super; atualização, terminação e valor da política permanecem sem medição. São 1.497 palavras GNU e 14 testes novos, sem execução de firmware Samsung.

O [wrapper AVB e seu chamador](../docs/lk-avb-wrapper-hzc2.md) têm os retornos locais delimitados: red conserva um laço antes do epílogo; o retorno normal preserva o resultado do slot e é descartado imediatamente pelo chamador. Pedidos de metadados ao monitor foram identificados. São 847 palavras GNU e 17 testes novos; aceitação física e efeitos dos serviços seguros continuam abertos.

O [verificador vbmeta e caminho RSA](../docs/lk-avb-signature-hzc2.md) agora tem resultados separados de cabeçalho, hash e assinatura, com seis combinações SHA/RSA e padding PKCS#1 v1.5 conferidos. São 1.147 palavras GNU e 18 testes novos. A conversão desses resultados para o slot foi delimitada; confiança da chave e autorização final de boot continuam etapas distintas.

O [callback de confiança AVB](../docs/lk-avb-key-trust-hzc2.md) foi ligado nominalmente ao pedido de chave `vbmeta` no monitor. O consumidor separa status de I/O e confiança; consulta de desbloqueio e classificação local dos rótulos também foram delimitadas. São 342 palavras GNU e 13 testes novos; aceitação final e igualdade com a chave embutida continuam abertas.

- `inspect_newtime_dmc_table_services_hzc2.py` / `test_newtime_dmc_table_services.py`: tabela da cauda, acumulador ID18, consumidor selecionado e publicador por raízes distintas; 21 testes e [limites](../docs/newtime-dmc-table-services-hzc2.md).

- `inspect_newtime_dmc_loader_hzc2.py` / `test_newtime_dmc_loader.py`: corpos locais do carregador DMC17 e cauda, ASR/UXTH/STRH e publicações condicionais; 20 testes e [condições](../docs/newtime-dmc-loader-hzc2.md).

- `inspect_newtime_domain0_callees_hzc2.py` / `test_newtime_domain0_callees.py`: folhas do callback0, índice low8, rota DMC17 e dois métodos; 20 testes e [escopo](../docs/newtime-domain0-callees-hzc2.md).

- `inspect_newtime_fast_apply_hzc2.py` / `test_newtime_fast_apply.py`: laço do helper direto, callbacks/dependências e retorno/clear condicionados; 20 testes e [limites](../docs/newtime-fast-apply-hzc2.md).

- `inspect_newtime_policy_writers_hzc2.py` / `test_newtime_policy_writers.py`: setters FVP comando4 e comando5/subseletor2, dez regressões de palavras Thumb e sequência com comando6.

- `inspect_newtime_dispatch_completion_hzc2.py` / `test_newtime_dispatch_completion.py`: consumidor do retorno FVP e avanço circular condicionado, nove testes.

- `inspect_newtime_return_planes_hzc2.py` e `test_newtime_return_planes.py`: separação estática dos retornos FVP/cache/header, nove regressões.

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
- `inspect_newtime_copy_arguments_hzc2.py` e `test_newtime_copy_arguments.py`:
  argumentos das 47 referências, wrappers, índices com sinal e aliases
  preservados como lacunas; [relatório](../docs/newtime-copy-arguments-hzc2.md).
- `inspect_newtime_channel_origins_hzc2.py` e `test_newtime_channel_origins.py`:
  escritor das quatro células e modelos condicionais dos descritores;
  [origens, verificações e limites](../docs/newtime-channel-origins-hzc2.md).
- `inspect_newtime_slot20_hzc2.py` e `test_newtime_slot20.py`: chamadores
  selecionados, X5 local/nulo, aritmética e buscas limitadas de endereço;
  [relatório](../docs/newtime-slot20-hzc2.md).
- `inspect_newtime_margin_hzc2.py` e `test_newtime_margin.py`: payload MARGIN, handles simbólicos, nomes/casos e regressões de largura/count; [auditoria](../docs/newtime-margin-hzc2.md).
- `inspect_newtime_asv_gen_hzc2.py` e `test_newtime_asv_gen.py`: n, GEN com cabeçalho de dois u32, subkeys, pedidos SMC e posições; GNU1027/169/69 e 24 testes ASV/GEN. [Auditoria](../docs/newtime-asv-gen-hzc2.md).
- `inspect_newtime_ect_gate_hzc2.py` e `test_newtime_ect_gate.py`: gate/finalize, SMC W/X, efeitos delimitados e reserva corrigida; GNU534/121/63 e 24 testes. [Auditoria](../docs/newtime-ect-gate-hzc2.md).
- `inspect_newtime_slot38_hzc2.py` e `test_newtime_slot38.py`: folha, coluna 13, cadeia selecionada dos slots 19/22/38 e store de byte; GNU363/35/73 e 28 testes novos, sem executar firmware. [Auditoria](../docs/newtime-slot38-hzc2.md).
- `inspect_newtime_slot38_buffers_hzc2.py` e `test_newtime_slot38_buffers.py`: destino das colunas 6/7, footprint de B, backups/restauração e fronteira +56; GNU193/15/94 e 32 testes novos. [Limites](../docs/newtime-slot38-buffers-hzc2.md).
- `inspect_newtime_method56_hzc2.py` e `test_newtime_method56.py`: método +56, pacote comando6, fila e resposta exata; GNU207/14/107 e 32 testes novos. [Condições](../docs/newtime-method56-hzc2.md).
- `inspect_newtime_command6_hzc2.py` e `test_newtime_command6.py`: ponte Thumb canal1/FVP/DVFS, filas candidatas e resposta projetada; GNU814/932/112/10/96 e 25 testes novos. [Limites](../docs/newtime-command6-hzc2.md).
- `inspect_newtime_fvp_effective_hzc2.py` e `test_newtime_fvp_effective.py`: máximo/limite FVP comando6/domínio0, releitura do valor e cache; GNU830/983/150/64,28 testes e4608 fixtures cruas. [Condições](../docs/newtime-fvp-effective-hzc2.md).
- `inspect_newtime_dvfs_receiver_hzc2.py` e `test_newtime_dvfs_receiver.py`: modo0, callback com recarga/retorno parcial, init vivo, limiares e broadcast de quatro registradores; 28 testes próprios. [Auditoria e limites dos47 testes externos](../docs/newtime-dvfs-receiver-hzc2.md).
- `inspect_newtime_secondary_result_hzc2.py` e `test_newtime_secondary_result.py`: retorno do buffer secundário, gates/tags, offsets u16 e stores com alias exato; [escopo](../docs/newtime-secondary-result-hzc2.md).
- `inspect_newtime_mif_bins_hzc2.py` e `test_newtime_mif_bins.py`: folha de 53 palavras, tabela/células, X2/X3 de saída e liveness do retorno; [auditoria](../docs/newtime-mif-bins-hzc2.md).
- `inspect_newtime_common_continuation_hzc2.py` e `test_newtime_common_continuation.py`: grafo de 0x1aff0, argumentos de sete chamadas e modelos W/byte, com aliases abertos; [reprodução](../docs/newtime-common-continuation-hzc2.md).
- `inspect_newtime_jump_tables_hzc2.py` e `test_newtime_jump_tables.py`:
  20 entradas halfword e cinco byte, anchors separados dos arrays,
  guard unsigned e grafos locais com callees opacos;
  [limites e reprodução](../docs/newtime-jump-tables-hzc2.md).

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

- `test_elf_symbols.py`: cinco regressões do leitor compartilhado por `test_entry_diag.py` e `test_payload_loader.py`: cabeçalhos em inglês/traduzido, locale do subprocesso, valor inválido e ELF recém-compilado. Executado pelo CI antes do baseline; não requer QEMU ou firmware Samsung.

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

- `inspect_lk_embedded_key.py` / `test_lk_embedded_key.py`: endereço do consumidor decodificado, comprimento u32 e chave pública serializada AVB com parâmetros Montgomery conferidos; 17 testes sem firmware, referência de formato fixada e recusa de imagem não identificada. Não executa SHA no monitor nem verifica confiança/assinatura. [Identificação e limites](../docs/lk-embedded-avb-key-hzc2.md).

- `inspect_lk_avb_trust.py` / `test_lk_avb_trust.py`: tabela AvbOps, slots +48/+72, consulta nominal da chave `vbmeta`, separação status/confiança e rótulos locais do wrapper. Treze testes de binding e recusa, sem executar firmware ou SMC. [Evidência e limites](../docs/lk-avb-key-trust-hzc2.md).

- `inspect_lk_avb_signature.py` / `test_lk_avb_signature.py`: caminho vbmeta/RSA, tabelas de algoritmos/padding, dois dispatches signed byte e conversão de resultados para o slot. Dezoito testes sintéticos de decodificação/recusa, sem executar firmware. [Evidência e limites](../docs/lk-avb-signature-hzc2.md).

- `inspect_lk_avb_boot.py` / `test_lk_avb_boot.py`: wrapper AVB completo localmente, laço red, códigos/retornos, referência B/BL e descarte no chamador, além de sete fragmentos de pedidos seguros. Dezessete testes sintéticos, sem executar firmware. [Escopo e evidências](../docs/lk-avb-wrapper-hzc2.md).

- `inspect_lk_build_id.py` / `test_lk_build_id.py`: checker Build-id, ligação do produtor/leitor de cache, getter de super e corpos locais de processamento/relatório de partições. Quatorze testes de operandos/binding/recusa; sem firmware executado. [Escopo e reprodução](../docs/lk-build-id-partitions-hzc2.md).

- `inspect_lk_samsung_checks.py` / `test_lk_samsung_checks.py`: tabela exata de nomes, pedido de assinatura ao monitor, rollback e política custom, com 16 testes sintéticos de ponteiros/descritor/recusa. Sem execução de firmware ou SMC. [Escopo e reprodução](../docs/lk-samsung-checks-hzc2.md).

- `inspect_lk_rpmb.py` / `test_lk_rpmb.py`: backend dos contadores, switch signed halfword, descritor MAC e gates, com 16 testes sintéticos. Análise estática sem pacotes ou SMC executados. [Escopo e reprodução](../docs/lk-rpmb-hzc2.md).

- `inspect_rpmb_frame.py` / `test_rpmb_frame.py`: leitor de um arquivo regular de512 bytes, com ordem explícita e hashes dos arrays transmitidos; 14 testes, sem autenticação ou I/O de dispositivo.
- `inspect_flop_reference.py` / `test_flop_reference.py`: valida19 fontes fixadas, constantes/config e o layout C de RPMB no host; 12 testes e nenhuma execução do kernel. [Referência e reprodução](../docs/flop-kernel-reference.md).

- `inspect_lk_rpmb_transport.py` / `test_lk_rpmb_transport.py`: construtor/registro scsirpmb, binding de métodos, CDBs SCSI e entrada UFS; 16 testes de operandos/recusa e992 palavras GNU. [Escopo](../docs/lk-rpmb-transport-hzc2.md).

- `inspect_lk_ufs_completion.py` / `test_lk_ufs_completion.py`: descritores UFS, polling por amostra, publicação de status e binding até o consumidor SCSI; 21 testes e635 palavras GNU, sem firmware executado. [Escopo](../docs/lk-ufs-completion-hzc2.md).

- `inspect_lk_ufs_host.py` / `test_lk_ufs_host.py`: publicação do host, alocações, tabelas MMIO e projeção low32 de bases; 19 testes e 432 palavras GNU, sem firmware executado. [Escopo](../docs/lk-ufs-host-memory-hzc2.md).

- `inspect_lk_heap.py` / `test_lk_heap.py` / `emulate_lk_heap_qemu.py`: pool nominal, heap e provedor de páginas que abastecem os buffers UFS; 562 palavras GNU, 17 testes e 28 casos originais em QEMU com pool fornecido. [Escopo](../docs/lk-heap-pool-hzc2.md).

- `inspect_lk_pool_mmu.py` / `test_lk_pool_mmu.py` / `emulate_lk_pool_mmu_qemu.py`: construção selecionada EL1/4KiB da tradução e atributos do pool; 292 palavras GNU, 21 testes e seis casos originais QEMU, sem instalar tabelas. [Escopo](../docs/lk-pool-mmu-hzc2.md).

- `inspect_newtime_dmc_magic_hzc2.py` / `test_newtime_dmc_magic.py`: produtor local de0xabcd1234, campainha, poll com limpeza externa e continuação−232; 22 testes e112 palavras A64, com rota Thumb herdada. [Escopo](../docs/newtime-dmc-magic-hzc2.md).
- `inspect_flop_acpm_reference.py` / `test_flop_acpm_reference.py`: oito fontes fixadas, probe C seguro de ABI SRAM, mailbox e namespace ECT; 14 testes. [Escopo](../docs/flop-acpm-reference.md).

- `inspect_lk_entry_granule.py` / `test_lk_entry_granule.py` / `emulate_lk_entry_granule_qemu.py`: entrada por EL, getter TG0 original e censo limitado de writers TCR_EL1; 131 palavras GNU,14 testes,24 entradas e48 chamadas do getter. [Escopo](../docs/lk-entry-granule-hzc2.md).

- `inspect_lk_ufs_iocc.py` / `emulate_lk_ufs_iocc_qemu.py` / `test_lk_ufs_iocc.py`: consultas distintas, tabelas, OR PHY/IOCC e32 casos de fragmentos originais com alvos em RAM. `inspect_flop_ufs_iocc.py` / `test_flop_ufs_iocc.py`: dois arquivos fixados, resolução numérica de phandles e nove testemunhas do driver;26 testes novos. [Escopo](../docs/lk-ufs-iocc-hzc2.md).
