# Catálogo de scripts

Execute a partir da raiz do repositório. Os comandos de validação estão no [README principal](../README.md).

| Grupo | Arquivos | Uso |
|---|---|---|
| Regressão | `regress.sh`, `test_pr_fixes.sh`, `test_r10_stage.sh` | R8/R9 e testes de componentes R10/UART/atômicos |
| FDT e contêiner | `test_fdt.py`, `test_payload.py`, `test_payload_stage.py`, `test_payload_loader.py` | Modelos sanitizados e handoff real no QEMU |
| Ambiente | `bootstrap_tools.sh`, `cross-run.sh`, `run_qemu.sh` | Ferramentas locais e execução dos módulos |
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

- `inspect_sec_pgtbl_hzc2.py` e `test_sec_pgtbl_hzc2.py`: verificam identidades sboot/LDFW, percorrem seis registros por tamanho, registram cifragem pelo formato relacionado e rastreiam a entrega ao monitor. Modelam opcionalmente duas respostas X0; 14 testes de host. Não recuperam o provedor DRM ou RAM livre. [Escopo e reprodução](../docs/sec-pgtbl-hzc2.md).
- `emulate_sec_pgtbl_hzc2.py`: dependência opcional Unicorn 2.1.4; executa somente o chamador LK original, com respostas SMC explícitas e printf omitido. `--self-check` confere 144 cenários contra o modelo, com páginas/PCs/tempo/instruções limitados. Não executa serviços ou decifra o DRM; relatórios distinguem simulação e observação.
