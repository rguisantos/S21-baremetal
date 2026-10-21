# UART0: clocks nominais entre BL2 e LK

Análise estática de 2026-10-21, mesmo sboot HZC2 de 4 MiB, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets são do arquivo. Complementa [pinmux anterior ao LK](bl2-uart-hzc2.md)
e [mapa de clocks da fonte](exynos-2100-reference.md).

## Refinamento: há dois caminhos nominais, não um clock fixo de 26 MHz

A rotina 0x1d59c, documentada anteriormente, passa 26 MHz/115200 a 0x1d380.
A busca seguinte encontrou um wrapper **0x1d4b4** que passa **133.250.000 /
115.200** à mesma rotina. A entrada BL2 chama esse wrapper diretamente:

```text
0x160bc  bl   0x17e14       ; inclui chamada de pinmux em 0x17e4c
0x160c0  bl   0x1d4b4
...
0x1d4b4  mov  w1, #0xc200
0x1d4b8  mov  w0, #0x3bd0
0x1d4bc  movk w1, #1, lsl #16      ; 0x1c200 = 115200
0x1d4c0  movk w0, #0x7f1, lsl #16  ; 0x07f13bd0 = 133250000
0x1d4c4  b    0x1d380
```

Esse é um caminho estático mais diretamente ligado à entrada que a rotina
26 MHz. Não se afirma que o hardware tenha passado temporalmente por ambos:
o consumidor e todas as condições de chamada de 0x1d59c não foram fechados.
Clock nominal em argumento não é leitura da frequência real.

## Inicialização PERIC0 baseada em tabelas

A rotina 0x1765c chama dois helpers com base 0x10400000 e count 11:

| Helper | Tabela no arquivo | Operação |
|---|---|---|
| 0x16a60 | bytes em 0x30670 | escreve em base+0x1000+4*i; ignora valor 0xff |
| 0x16a90 | u16 em 0x30680 | escreve em base+0x1800+4*i; ignora valor 0xffff |

A primeira tabela contém onze bytes 1. A segunda contém
`[2,0,0,0,0,0,0,0,0,0,1]`.

A entrada i=0 é relevante à UART_DBG conforme o CAL Samsung:

- 0x10401000 recebe **1**: mux UART_DBG seleciona MUX_CLKCMU_PERIC0_IP0_USER
  na lista de pais da fonte;
- 0x10401800 recebe **2**: encoding do divisor. O helper CAL `ra.c` programa
  ratio-1, portanto corresponde a divisão por 3 nesse modelo;
- em 0x17688–0x17698, faz read/modify/write de bit 4 em **0x10400620**;
  o CAL identifica esse campo como seleção de IP0_USER, cujo pai 1 é
  CLKCMU_PERIC0_IP0;
- também altera 0x10400610 (IP1_USER) e outros registradores. Não reproduzir
  esses writes como uma sequência mínima sem compreender suas dependências.

O valor nominal 133,25 MHz é compatível aritmeticamente com uma entrada de
399,75 MHz dividida por 3. **Não se mediu essa entrada nem foi fechada a
configuração de PLL/CMU_TOP inteira**. A conta é uma inferência, não uma
frequência confirmada do aparelho.

## Ligação das chamadas e segunda cópia das tabelas

No caminho de inicialização de 0x17e14, há chamada em **0x18020** para
0x17864. Esta varre diversas rotinas de clock e chama **0x1765c em 0x178f8**.
Isso liga a programação PERIC0 à inicialização anterior ao wrapper de UART.
Há ramos dependentes de estado dentro da inicialização; não se resolveu o
caminho efetivamente tomado no aparelho.

Outra sequência em **0x3671c**, ainda no intervalo candidato BL2, usa os
helpers 0x365fc/0x3662c e tabelas em **0x369c8/0x369d8**. Os onze valores de
mux e divisor são idênticos aos da primeira sequência. Há chamadas diretas
0x36944→0x3671c e 0x369bc→0x36934. O propósito de todos os chamadores
não foi determinado; não atribuir por isso uma fase de resume ou reset.

## Comparação do divisor UART com o LK

A configuração 0x1d380 usa a constante double 1/16, divisão pelo baud e
subtração de 1. Para os argumentos positivos encontrados:

| Caminho | Clock nominal | Baud pedido | UBRDIV inteiro calculado |
|---|---:|---:|---:|
| Wrapper ligado à entrada BL2 | 133.250.000 | 115.200 | 71 / 0x47 |
| Rotina separada 0x1d59c | 26.000.000 | 115.200 | 13 / 0x0d |
| LK 0xef474–0xef488 | não lido nesse trecho | não expresso nesse trecho | escreve 0x47 |

O resultado 71 do wrapper é igual ao valor fixo do LK. Isso corrobora um
nominal compartilhado, sem comprovar que nenhum agente altere o clock antes
do kernel. O LK zera o campo baixo de +0x2c. Na sequência BL2 decodificada,
o cálculo de fração inclui `fsub d0,d0,d0`, produzindo zero para entrada finita.
Não se deve apresentar o baud nominal pedido como taxa exata medida.

A sequência UART investigada não basta para afirmar o estado de todos os
QCH/gates, power domains, pinmux e permissões no handoff. O driver R10
continua sem assumir clock fixo de 26 MHz ou 133,25 MHz automaticamente.

## Reprodução e verificação

```bash
python3 scripts/inspect_sboot_hzc2.py /caminho/sboot.bin
```

O relatório inclui `uart_clock_stages`: bytes/halfwords das duas tabelas,
chamadas diretas, palavras dos argumentos do wrapper e divisor LK. Tudo está
vinculado ao hash exato. Valores foram conferidos por desassemblagem Capstone
e extração independente de imediatos e tabelas. Não houve emulação dessas
rotinas ou medição do Exynos. Para repetir a desassemblagem, intervalos:
0x160b8:0x160c8, 0x16a60:0x16ac8, 0x1765c:0x176c8,
0x178e8:0x17904, 0x18018:0x18024, 0x1d380:0x1d428,
0x1d4b4:0x1d4c8, 0x3671c:0x36788 e 0xef46c:0xef498.

A prioridade seguinte é verificar alterações e dependências até o handoff,
e definir como observar o estado real. Não solicitar nova coleta dos nós
que o shell já mostrou indisponíveis nem reenviar pacotes recebidos.

## Origem nominal fechada na fonte — continuação 2026-10-21

O passo seguinte ligou os dois registradores CMU_TOP à seleção da PLL:

| Elemento | Evidência do firmware | Ligação na fonte CAL |
|---|---|---|
| Mux TOP PERIC0_IP0 | 0x169a8 escreve 2 em 0x1a3310d0 | índice 2 de `cmucal_mux_clkcmu_peric0_ip0_parents` = PLL_SHARED2_D2 |
| Divisor TOP PERIC0_IP0 | 0x1699c escreve WZR em 0x1a3318c8 | encoding 0 = dividir por 1 |
| User mux | 0x17698 liga bit 4 em 0x10400620 | seleciona CLKCMU_PERIC0_IP0 |
| Mux UART local | tabela 0x30670, índice 0 = 1 | MUX_CLKCMU_PERIC0_IP0_USER |
| Divisor UART local | tabela 0x30680, índice 0 = 2 | dividir por 3 |

Os writes CMU_TOP também aparecem em 0x36538/0x36544, na segunda sequência
analisada, com os mesmos valores. O significado dos encodings vem da fonte;
as instruções mostram os valores escritos, sem observar o hardware.

`cmucal-node.c` declara `pll_shared2_rate_table` com
`PLL_RATE_MPS(799500000, 123, 2, 1)` e o fator `PLL_SHARED2_D2` como ratio
codificado 1, isto é, divisão por 2 no modelo CAL. A conta nominal fecha:

`26.000.000 × 123 / (2 × 2^1) = 799.500.000 Hz`

`799.500.000 / 2 / 1 / 3 = 133.250.000 Hz`

Assim, os 133,25 MHz passados ao wrapper BL2 têm suporte na árvore de clocks
da fonte, não só na coincidência com UBRDIV do LK. **Os valores M/P/S da PLL
são os nominais da tabela de fonte**, não valores lidos ou confirmados como
escritos no aparelho. A programação completa de PLL_SHARED2 permanece pendente.

### Gates e o que ainda não foi demonstrado

O CAL identifica QCH em **0x10403014** e o gate do sincronizador de reset
UART em **0x104020b8**. Os gates IPCLK e PCLK são distintos: ver o
[inventário de gates](uart-gates.md), que refina a descrição anterior.
A busca de palavras literais completas e de construções
imediatas diretas nos trechos examinados não encontrou um acesso inequívoco
que fixe seus estados no handoff. Isso é um resultado limitado de busca,
não prova de ausência de writes: tabelas, aliases, outro firmware e acessos
indiretos podem configurá-los. Não declarar a UART pronta por essa conta.

Cuidado com nomes semelhantes: o registro CMU_TOP **0x1a33014c** é PLL_MMC
na fonte consultada; PLL_SHARED2 é **0x1a33020c**. Uma escrita na primeira
não deve ser usada como evidência do estado da segunda.

### Auditoria offline reproduzível

```bash
python3 scripts/check_uart_clock_evidence.py /caminho/sboot.bin /caminho/fontes-kernel
```

A raiz de fontes precisa fornecer `drivers/clk/samsung/clk-exynos2100.c` e
`drivers/soc/samsung/cal-if/exynos2100/{cmucal-node,cmucal-sfr,cmucal-qch}.c`
com os hashes já registrados no manifesto Exynos-2100. Os quatro foram
comparados anteriormente com o pacote recebido e são byte-idênticos.
A ferramenta confere o hash do sboot, os quatro arquivos, os seletores,
tabela M/P/S, divisores, inventário de gates/QCH e consistência
com os argumentos BL2 e UBRDIV LK. Faz somente leituras e imprime JSON.

Executada com as fontes fixadas: **133250000 Hz nominais, baud pedido 115200,
UBRDIV BL2=LK=71**. Entradas com fonte modificada e firmware incorreto foram
recusadas. O resultado marca `runtime_observed=false` e mantém gates e estado
final como pendências. É auditoria de evidência estática, sem emulação do SoC,
leitura física, cálculo automático de um plano de writes ou teste UART.
