# UART0: gates e QCH da fonte Samsung

Análise estática de 2026-10-21. Complementa os [clocks nominais](uart-clock-stages.md).
Os nomes, endereços, pais e campos abaixo vêm dos arquivos CAL fixados no
[manifesto Exynos-2100](references/exynos-2100-37c14d8.json), comparados com o
Kernel.tar.gz recebido. Não são valores de registradores lidos do telefone.

## Três gates, dois caminhos de clock e um QCH

| Elemento CAL | Endereço | Pai na árvore da fonte |
|---|---|---|
| RSTNSYNC_CLK_PERIC0_UART_DBG / CLK | 0x104020b8 | DIV_CLK_PERIC0_UART_DBG |
| PERIC0_TOP0 / IPCLK_4 | 0x10402030 | DIV_CLK_PERIC0_UART_DBG |
| PERIC0_TOP0 / PCLK_4 | 0x10402060 | MUX_CLKCMU_PERIC0_BUS_USER |
| PERIC0_TOP0_QCH_UART_DBG | 0x10403014 | controle QCH; não é um quarto divisor |

Correção de precisão: **0x104020b8 é o gate do sincronizador de reset**;
a descrição anterior como gate UART IPCLK não distinguia os dois. O gate
IPCLK_4 é 0x10402030. PCLK_4 usa o caminho BUS_USER, separado do divisor
UART_DBG cuja frequência nominal de 133,25 MHz foi rastreada. Logo, fechar
a conta desse divisor não fecha todas as dependências do console.

Nos três gates, `cmucal-sfr.c` declara os mesmos campos:

| Campo | Bit inicial | Largura |
|---|---:|---:|
| CG_VAL | 21 | 1 |
| MANUAL | 20 | 1 |
| ENABLE_AUTOMATIC_CLKGATING | 28 | 1 |

No QCH, os campos são distintos:

| Campo | Bit inicial | Largura |
|---|---:|---:|
| ENABLE | 0 | 1 |
| CLOCK_REQ | 1 | 1 |
| EXPIRE_VAL | 16 | 10 |
| IGNORE_FORCE_PM_EN | 2 | 1 |

São descrições de campos, sem um valor recomendado para escrever. A lógica
CAL distingue controle manual e automático dos gates; um bit isolado não
basta para declarar que a UART está operacional. Também não se deduz estado
de reset, power domain, acesso ou roteamento físico desses nomes.

## Resultado da busca no sboot HZC2

No arquivo de 4 MiB identificado pelo SHA-256 já registrado, a busca dos
quatro endereços completos, como palavras little-endian, encontrou zero
ocorrências. Uma varredura heurística de instruções entre 0x16000 e 0x20c630
também não identificou construção direta inequívoca de um acesso a eles.
Isso **não prova ausência de configuração**: bases recebidas como argumentos,
laços, tabelas, código fora do intervalo e outros agentes não ficam cobertos.

Um falso candidato ilustra o limite da busca por offsets: em 0x14ce7c há
`str w1,[x19,#0x20b8]`, mas x19 é derivado de SP e alinhado em 0x14cdc0–
0x14cdd0. Essa escrita é em um buffer da pilha, sem evidência de acesso à CMU.
Não somar automaticamente um offset encontrado à base 0x10400000.

As rotinas PERIC0 0x1765c e 0x3671c continuam mostrando mux/divisor e
user muxes. Nenhum estado final de gates/QCH foi recuperado nesta análise.

## Reprodução sem acesso ao aparelho

```bash
python3 scripts/check_uart_clock_evidence.py /caminho/sboot.bin /caminho/fontes-kernel
```

A auditoria verifica hashes de quatro arquivos: `cmucal-node.c`,
`clk-exynos2100.c`, `cmucal-sfr.c` e `cmucal-qch.c`. O JSON inclui
`gate_source_inventory`, extraído das declarações SFR/SFR_ACCESS e ligado
aos nós CLK_GATE/CLK_QCH. Não aceita os nomes apenas por coincidência textual:
confere a associação entre registrador, campos, bloco e nó.

A execução com o firmware e as fontes fixadas passou. A alteração individual
de cada uma das quatro fontes foi recusada por hash. O relatório continua
com `runtime_observed=false`. Não houve acesso MMIO, execução do firmware,
mudança do driver R10 ou teste físico.

Próximo trabalho: rastrear acessos indiretos e a origem do caminho BUS_USER,
além das alterações posteriores até o salto ao kernel. A observação real
continua dependente de um canal acessível no aparelho; repetir as coletas
rish já bloqueadas não resolve essa lacuna. Nenhum arquivo extra é necessário
para continuar a análise estática com o material disponível.

Fontes primárias fixadas:
[SFR e campos](https://github.com/Exynos-2100/android_kernel_samsung_universal2100/blob/37c14d86996a49edbea8953f2523b202546b8958/drivers/soc/samsung/cal-if/exynos2100/cmucal-sfr.c),
[nós e pais](https://github.com/Exynos-2100/android_kernel_samsung_universal2100/blob/37c14d86996a49edbea8953f2523b202546b8958/drivers/soc/samsung/cal-if/exynos2100/cmucal-node.c),
[nó QCH](https://github.com/Exynos-2100/android_kernel_samsung_universal2100/blob/37c14d86996a49edbea8953f2523b202546b8958/drivers/soc/samsung/cal-if/exynos2100/cmucal-qch.c).
