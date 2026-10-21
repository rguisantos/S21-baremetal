# UART0 antes do LK: rotina compatível com o DTS no BL2 HZC2

Análise estática de 2026-10-21 do mesmo sboot de 4 MiB, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Os offsets abaixo são do arquivo, no intervalo candidato BL2 0x16000–0xec000
já documentado. Não são endereços runtime nem prova de execução física.

## O que a busca encontrou

A investigação anterior ficou concentrada no LK. Ampliando a busca dos
construtores MOVZ/MOVK de 0x1043 ao arquivo completo, apareceu uma segunda
rotina em **0x1d46c**, anterior ao intervalo LK:

```text
0x1d46c  mov  x2, #0x120
0x1d470  movk x2, #0x1043, lsl #16  ; x2 = 0x10430120
0x1d474  ldr  w0, [x2]
0x1d478  and  w1, w0, #0xffff00ff   ; limpa somente campos 2 e 3
0x1d47c  mov  w0, #0x3300
0x1d480  orr  w0, w1, w0
0x1d484  str  w0, [x2]
```

A transformação é `novo = (antigo & 0xffff00ff) | 0x3300`.
Ela seleciona função 3 nos dois campos de quatro bits dos pinos 2/3.
Isso coincide com **GPG0_CON 0x10430120, gpg0-2/gpg0-3**, derivados do
pinctrl/DTS Samsung. Não copia uma configuração do mapa Exynos 9820.

Há chamadas diretas BL para essa rotina em **0x17e4c** e **0x1d5ac**.
A primeira fica em uma sequência de inicialização que também lê registradores
SoC; a segunda fica no início da rotina 0x1d59c, associada à UART0 abaixo.
Os alvos foram decodificados por imm26 assinado. Não foram resolvidos todos
os ramos de entrada dessas funções; não afirmar que ambas sempre executam.

## Configuração e transmissão UART0 nesse intervalo

A rotina **0x1d380** acessa o bloco 0x10540000:

- limpa o bit 0 de USI_CON em +0xc4;
- escreve ULCON +0 com 3, UCON +4 com 0x3005, UFCON +8 com 1;
- zera UMCON +0xc, escreve 6 em +0x10;
- calcula e escreve os campos baixos de +0x28/+0x2c;
- escreve 0xf em UINTM +0x38.

É descrição das instruções, não uma receita de inicialização validada. A
rotina não estabelece por si só domínio de energia, clock de entrada efetivo
ou sequência completa USI_OPTION. Não foi executada ou portada para o R10.

Em **0x1d59c**, após chamar o pinmux, o código passa a 0x1d380:

| Argumento | Valor derivado de MOVZ/MOVK |
|---|---:|
| w0 | 0x018cba80 = 26.000.000 |
| w1 | 0x0001c200 = 115.200 |

A constante double em 0x1d428 é 0,0625 (1/16). O cálculo usa ponto flutuante
para divisão e conversão do divisor. Esses argumentos corroboram o nominal
26 MHz/115200 nesse caminho; não medem o clock ou baud em nenhum estágio.
A sequência da fração ainda deve ser revisada antes de qualquer port, e o
R10 usa configuração/contrato próprios.

A rotina **0x1d4dc** espera bit 1 de 0x10540010 e escreve um word em
0x10540020. Ela também pode adicionar o byte a um buffer anterior. O caminho
**0x1d560** percorre strings, emitindo CR antes de LF. Isso liga o bloco UART
a uma função de saída, além de meramente encontrar seus endereços em dados.

## Por que isso muda a interpretação do LK

O sboot contém, portanto, **uma sequência anterior compatível com o pinmux
2100**, e também a escrita LK em 0x10430080 que diverge da fonte.

| Evidência | Conclusão |
|---|---|
| 0x1d46c configura 0x10430120/0x3300 | Há código correspondente ao mapa UART0 da fonte no intervalo BL2 |
| Chamadas 0x17e4c/0x1d5ac | Há referências diretas à função; não é apenas dado sem consumidor |
| LK 0xef3e0 altera outro word/campos | A divergência local continua; não substituir silenciosamente um endereço pelo outro |
| Configuração anterior pode persistir | Hipótese plausível para UART herdada no LK; ainda não observada no aparelho |

Não é mais adequado tratar o sboot inteiro como se só contivesse o pinmux
aparentemente legado. Também não se conclui que a UART estará utilizável
pelo payload: gate do console, roteamento MUIC, revisões e estado de clock
continuam relevantes. O LK usa divisor diferente do nominal dessa rotina;
o estado pode mudar entre estágios.

## Relação com o word em 0x30565c

A busca original era pelo consumidor desse dado. Foram procuradas referências
ADR/ADRP e ponteiros diretos ao redor do word no LK; a análise exploratória
de bases/loads também não estabeleceu um consumidor de 0x10430120 nesse
local. Isso **não prova que o dado esteja morto**. O novo achado é independente:
a função BL2 constrói o endereço por instruções, sem carregar aquele word.
A semântica da estrutura em 0x305658 continua não identificada.

## Reproduzir e próxima prioridade

```bash
python3 scripts/inspect_sboot_hzc2.py /caminho/sboot.bin
```

O relatório agora inclui `early_uart`: palavras do pinmux, chamadas diretas,
argumentos e constante de escala. Exige o hash exato, lê sem modificar e não
requer Capstone. Para desassemblar, usar o snippet existente de
[bootloader-hzc2.md](bootloader-hzc2.md) em 0x1d380:0x1d428,
0x1d46c:0x1d4b4, 0x1d4c8:0x1d59c, 0x1d59c:0x1d624 e
0x17e34:0x17e5c.

Próxima prioridade: rastrear a configuração de clock entre estágios e o
handoff, preservando a distinção entre nominal de código e estado medido.
Não habilitar UART automaticamente a partir de uma suposta herança.
Não é necessário outro pacote nem repetir as coletas bloqueadas pelo Shizuku.
