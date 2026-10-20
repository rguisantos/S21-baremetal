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
