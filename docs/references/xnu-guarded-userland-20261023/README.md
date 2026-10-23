# Evidências do perfil iOS no consumidor EFI

Ensaio QEMU de 2026-10-23. Guia e limites em
[Userland pelo consumidor EFI validado](../../xnu-guarded-userland.md).

- `report.json`: saída original do runner; `UI_visually_verified` automático
  permanece falso. Exige contrato, término nativo e snapshots coincidentes.
- `validation.json` e `visual-review.json`: verificações adicionais e inspeção
  individual dos quatro PNGs de interface, com hashes vinculados ao relatório.
- `loaded-inputs.json`: hashes dos itens do payload, EFI efetivo da ESP e
  todos os bytes do intervalo residente no backing file da RAM.
- `contract.json`, `boot-args.bin`, `apple-tree.bin`, `resident-header.bin`:
  captura ABI somente de leitura na entrada do kernel.
- `s21_*.bin`, `win_*.bin`, `efi-map-*.bin`, `loader.map`: buffers nativos,
  células/posições e snapshots UEFI completos; `replay.json` registra o replay.
- `serial.log.gz`: serial completo, incluindo o retorno e reemissão dos mapas.
- `semantic-controls.json`: quatro mutações rejeitadas com hashes atualizados.
- `headroom.*`, `profile.*`, `cmdline.*`: três recusas anteriores à cópia/salto.
- `compat-resident.*`, `compat-embedded.*`: regressões dos dois modos anteriores.
- `host-tests.txt`: 74 testes de host.

`optimized-field.*`, `short-observer.*` e `runtime-interrupted.*` pertencem a
**tentativas incompletas** e não contam como PASS final. Os dois arquivos
`observer-before-*.py.gz` e `optimized-field-loader.inc.gz` conservam as
versões relevantes anteriores às correções de observabilidade. O PNG
`runtime-interrupted-settings.png` mostra Ajustes na sessão sem relatório
final; as capturas principais pertencem à execução aceita.

São quatro snapshots da preparação, reemitidos após retorno: não é um novo
GetMemoryMap após o userland. A validação demonstra consistência das capturas,
sem autenticação criptográfica do guest. UEFI permanece residente; não houve
execução Samsung, compilação local do kernel ou teste de todos os apps.
Kernel e imagens APFS não são incluídos nestes registros.
