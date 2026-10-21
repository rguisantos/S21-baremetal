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

- `check_lk_v3_layout.py` e `test_lk_v3_layout.py`: modelo offline das cópias kernel/ramdisk do LK HZC2 e testes de limites; requer imagens raw v3 e deslocamento explícito. Não empacota nem verifica bootabilidade; [escopo](../docs/lk-v3-layout.md).
