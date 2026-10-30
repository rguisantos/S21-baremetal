# Coleta no aparelho sem root

Registro do que já foi tentado em 2026-10-20. O usuário usa o firmware original HZC2/Android 15 e não tem root. Os arquivos e saídas fornecidos foram examinados; não é necessário repetir a mesma coleta bloqueada.

## Termux + Shizuku/rish

O rish foi exportado para Termux, o pacote configurado como `com.termux` e a sessão confirmou **uid=2000(shell)**, contexto `u:r:shell:s0`. Isso dá privilégios de shell ADB, não UID 0, e não ignora permissões DAC/SELinux.

`/sys/firmware/fdt` apareceu com 694.976 bytes, dono root e modo `0400`; a leitura retornou Permission denied. Essa existência/tamanho não entrega os bytes do DTB. O TAR da árvore live fornecido contém 3.818 diretórios e apenas uma propriedade de dois bytes de um dispositivo Wacom: as propriedades relevantes não foram copiadas por falta de permissão. Não é uma árvore reconstruível.

Os nomes observados incluem memória acima de 4 GiB e nós de reserva como `el2_code`, `el2_earlymem` e `kaslr`. Nomes isolados não demonstram endereços completos, tamanhos, origem dessas reservas, nem o nível de exceção de entrada do futuro payload.

## Outros resultados

| Tentativa/arquivo | Resultado e interpretação |
|---|---|
| `cat /proc/iomem` | Permission denied; sem mapa físico utilizável |
| `cat /proc/cmdline` | Permission denied; não inferir conteúdo de um arquivo vazio criado por redirecionamento |
| `at /proc/meminfo` | Erro de digitação: comando `at` inexistente; o correto é `cat` |
| `s21-meminfo.txt` recebido | MemTotal 10.829.472 KiB, aproximadamente 10,33 GiB de RAM gerenciada pelo Linux; consistente com variante de 12 GB, sem provar bancos ou reservas |
| `logcat -b kernel -d` | O retorno ao prompt sem erro exibido não comprova que o buffer foi disponibilizado ou que o arquivo contenha evidência útil |

O total gerenciado pelo Linux não é tamanho nem endereço de RAM livre para o payload. Os arquivos de diagnóstico brutos não são publicados aqui; este registro preserva os achados técnicos necessários.

## Como o trabalho continua

As imagens stock e fontes oficiais já permitiram conferir CPU, GIC, timer, UART e overlays, sem root. O código agora distingue essas evidências estáticas de um FDT/contrato de memória completo. O boot continua bloqueado quando RAM/reservas são insuficientes. Shizuku não foi tratado como meio de obter acesso root, e não houve tentativa de alterar permissões do firmware ou de fazer flash.

## Coleta UART/MUIC recebida — 2026-10-21

Arquivo `s21-uart-state.txt`, SHA-256
`dcb645c38e20cf9d075b7841b8edcede19594cd3c603bf06804cf25e250c1b1a`.
Timestamp declarado no relatório: 2026-10-21 14:13:08 UTC
(10:13:08 em America/Campo_Grande). O relógio não foi verificado externamente.
O arquivo bruto permanece fora do Git; os achados técnicos estão abaixo.

| Campo | Observado | Conclusão permitida |
|---|---|---|
| Identidade shell | uid=2000, contexto u:r:shell:s0 | rish/Shizuku operou como shell, sem root |
| Modelo | SM-G998B | Consistente com o alvo p3s |
| Build Android | AP3A.240905.015.A2.G998BXXSJHZC2 | Confirma a propriedade do build informado |
| Bootloader | G998BXXSJHZC2 | Propriedade compatível com o BL recebido; não é comparação dos bytes instalados |
| uart_sel | ABSENT (or hidden by permissions) | Não permite escolher entre ausência real e ocultação por permissões; AP/CP desconhecido |
| uart_en | modo 0660, system:radio; UNREADABLE | Nó presente, valor desconhecido; não comprova UART desligada |
| adc | ABSENT (or hidden by permissions) | Sem valor ADC disponível |
| attached_dev | No VPS | Estado sem correspondência na tabela consultada pelo callback de referência |
| usb_state | ABSENT (or hidden by permissions) | Sem estado USB consultável por esse caminho |

No `max77705-muic.c` recebido, `max77705_muic_show_attached_dev()` chama
`muic_lookup_vps_table()` e imprime `No VPS` se o índice for negativo.
Isso não identifica um jig reconhecido, mas também não comprova ausência
física de cabo/acessório. A comparação com a fonte explica a mensagem; não
identifica por si só a versão do driver carregado.

O modo de `uart_en` permite leitura ao proprietário system e grupo radio.
O shell mostrado não pertence a esse grupo, portanto as permissões DAC já
explicam a falta de acesso. SELinux pode impor limites adicionais, mas não
foi isolado como causa nessa coleta. Não inferir seu valor a partir do modo.

### Resultado para o projeto

A primeira coleta UART foi concluída no Android e o relatório chegou completo.
O coletor funcionou dentro dos limites do shell: registrou propriedades,
permissões e uma leitura efetiva de MUIC. Não foi possível observar seleção
AP/CP, habilitação UART ou ADC. Não houve mudança de configuração.

Continuam pendentes o roteamento físico de UART0, o estado do console no LK,
o contrato de carregamento e a recuperação do registro de entrada. Esse
relatório não mede EL/cache, não fornece FDT dinâmico e não libera teste físico
do payload. Não repetir a mesma coleta nem pedir novamente FDT/iomem/cmdline
negados. A análise estática pode continuar com os arquivos já recebidos.

## Logs de boot — coleta concluída sem conteúdo

Em 2026-10-21 foi recebido o relatório da coleta limitada pelo rish.
`/proc/last_kmsg`, `/proc/first_kmsg` e `/proc/sec_log` apareceram ausentes ou
ocultos ao uid=2000; nenhuma leitura/captura foi realizada. Não se distingue
permissão de ausência por esse resultado. [Hash, evidência e decisão](boot-log-collection.md#resultado-recebido--2026-10-21).
Não solicitar binários, repetir o procedimento ou concluir que não há log
preservado na RAM. O acesso por essas interfaces encerra-se como indisponível
nas condições atuais.

## Mint/ADB e consulta Download concluídos — 2026-10-30

O usuário autorizou ADB por USB no Mint 22.3/x86_64 e confirmou novamente
SM-G998B/p3s, HZC2, uid=2000(shell), `flash.locked=1`, estado vbmeta `locked`
e verified boot `green`. A opção OEM ativa nas configurações não foi tratada
como desbloqueio; a tela Download foi transcrita com `OEM LOCK: ON(U)`.

O USB enumerou `04e8:685d`. O [relatório Download/PIT](download-pit-observation-hzc2.md)
documenta inicialização e encerramento da sessão Heimdall, leitura de 48
entradas e extrato sem identificadores pessoais. O texto recebido foi
identificado por SHA-256; não foi recebido o arquivo PIT binário. A versão
do cliente e o código de saída não aparecem na transcrição.

Isso acrescenta um canal físico de consulta de armazenamento, sem conceder
novos privilégios ao shell. FDT, iomem, logs Harx e registro do diagnóstico
continuam indisponíveis pelos caminhos já negados. Não repetir essas leituras
como consequência da conexão do PC. A leitura da PIT está concluída e não
demonstra aceitação de um payload ou aquisição de RAM.
