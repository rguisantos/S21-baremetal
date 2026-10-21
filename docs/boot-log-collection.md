# Coleta limitada de logs pelo rish

Procedimento preparado em 2026-10-21 a partir do driver debug-snapshot do
pacote Samsung recebido. Não repete FDT, iomem, cmdline ou os atributos UART
já bloqueados. A execução deste coletor no telefone ainda está pendente.

## Objetivo e limites

A [análise do log em memória](lk-memory-log.md) identificou três interfaces
somente de leitura na fonte: `/proc/last_kmsg`, `/proc/first_kmsg` e
`/proc/sec_log`. Elas podem estar ausentes, desabilitadas ou sem permissão.
Os resultados anteriores do Shizuku não determinaram o acesso a esses nós.

`last_kmsg` pode conter a cópia cronológica do buffer preservado na inicialização;
`first_kmsg` consulta outro item de snapshot; `sec_log` expõe o log corrente
sob a configuração correspondente. Não são sinônimos nem garantem conteúdo
LK: a origem e as mensagens precisam ser analisadas após a coleta.

O script não acessa `/proc/kmsg`, `/dev/kmsg`, `/dev/mem`, interface que exige
escrita de seletor ou arquivos de bloco. Não usa root, não muda permissões e
não reinicia o aparelho. Sua única escrita é nos arquivos de saída.

## Executar

Salve `scripts/collect_boot_logs.sh` em Download. Dentro do rish:

```sh
sh /sdcard/Download/collect_boot_logs.sh
```

Será criada a pasta **Download/s21-boot-logs**. O script recusa sobrescrever
uma pasta existente. Para outra tentativa deliberada, informe uma pasta nova
como argumento; não repetir automaticamente em caso de negação de acesso.

Comece enviando apenas **report.txt**. Ele lista disponibilidade, permissões,
resultado de leitura e quantidade de bytes. Se um nó for legível, o script
salva seu conteúdo em `last_kmsg.bin`, `first_kmsg.bin` ou `sec_log.bin`,
limitado a **2 MiB e 5 segundos por arquivo**. Até três capturas, no máximo
6 MiB de conteúdo, sem contar metadados e erros. `timeout` e `head` são
necessários para ler; na ausência deles o nó é marcado como ignorado.

Os binários podem conter dados privados de logs; examine antes de compartilhar.
Falha/timeout pode deixar captura parcial. Chegar a 2 MiB não comprova que o
arquivo inteiro foi lido. Arquivo vazio é registrado com zero bytes; não é
prova de log útil ou de falha do bootloader.

## Como interpretar

- Ausente/oculto ou ilegível: registra o limite atual; não justifica pedir
  novamente a mesma leitura nem tentar mudar permissões.
- Leitura com erro/timeout: bytes salvos não são evidência completa.
- Leitura concluída com bytes: analisar conteúdo e identificar build, origem,
  mensagens LK e condições de preservação. Não inferir EL ou acesso físico
  sem evidência correspondente.

Essas capturas **não incluem o header físico**. Não devem ser passadas ao
`inspect_snapshot_log.py`, que exige o dump contíguo header+buffer. `last_kmsg`
já é reconstruído pelo driver na fonte; rodar outra rotação sobre ele seria
incorreto. Um log legível poderá reduzir dúvidas sobre o carregador, mas não
estabelece posse de memória para o R10.

## Verificação local

Sintaxe conferida com `sh -n`. Fixture host verificou leitura exata, limite de
2 MiB, nó ausente e recusa de pasta existente sem sobrescrever. O teste usa
`S21_LOG_PROC_ROOT` para apontar a uma pasta temporária; no telefone, deixar
essa variável o valor padrão `/proc`. A fixture não emula permissões/SELinux
Android e não demonstra disponibilidade dos logs no aparelho.

## Resultado recebido — 2026-10-21

Relatório `report.txt`, SHA-256
`fed645347c8d05233bb5b6ec589094e03459d44f95d1dbd91b3f2960e95e524c`.
Timestamp informado: 2026-10-21 19:16:17 UTC (15:16:17 em Campo Grande),
sem verificação externa do relógio. Sessão uid=2000(shell), contexto
`u:r:shell:s0`.

| Interface | Resultado |
|---|---|
| /proc/last_kmsg | ABSENT (or hidden by permissions) |
| /proc/first_kmsg | ABSENT (or hidden by permissions) |
| /proc/sec_log | ABSENT (or hidden by permissions) |

O coletor terminou e registrou o rodapé. Nenhuma interface chegou ao ramo de
leitura; o relatório não registra captura binária, bytes de log ou timeout.
Não há binários dessa execução a solicitar ao usuário.

O teste de existência do shell não permite distinguir ausência real de
ocultação por permissões. Também não determina se o módulo está carregado,
se o log foi preservado ou se há conteúdo na RAM. Não atribuir a causa apenas
a SELinux nem concluir que o debug-snapshot não existe no firmware.

**Decisão:** o caminho de observação por estes três nós, nas condições atuais
do Shizuku, não está disponível. Não repetir a coleta, pedir root ou sugerir
mudança de permissões como continuação automática. O leitor offline permanece
validado apenas por fixtures; não existe dump real para ele nesta sessão.
A investigação segue pelo BL e pelas fontes já recebidos, enquanto contrato
de carregamento e canal físico de observação continuam pendentes. Este
resultado não autoriza teste de flash/chainload.
