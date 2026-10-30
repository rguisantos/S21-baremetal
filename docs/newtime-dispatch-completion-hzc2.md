# HZC2: consumo da fila após o retorno FVP

Análise estática em 2026-10-29, continuação de
[retorno completo/cache/header](newtime-return-planes-hzc2.md).
Base técnica `0bb0a7e`; sboot4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets abaixo são de arquivo, ACPM Thumb; não há execução física.

## O resultado completo chega ao logging

Na seleção já ligada ao FVP, o BLX `0x3929a` recebe o retorno u32 do
callback. `0x3929c` o salva no frame+4; `0x392d4` o recarrega como R2
para a chamada de logging `0x392dc ->0x38684`.

Entre esse retorno e a store do índice em `0x392fe`, não há teste local
do valor salvo para abortar o consumo ou selecionar retry. Há hooks e
logging intermediários; seus retornos, preservação e efeitos continuam
condições. Não se afirma que o índice avance quando uma dessas chamadas
não retorna ou altera as raízes relevantes.

O caso sem callback segue `0x39328..0x3933a ->0x3929e` sem substituir
frame+4. Esse campo é zerado antes do laço em `0x391ee/0x391f8`, não a
cada iteração. Sob preservação, o log desse caminho pode reutilizar o
resultado de uma iteração anterior. Isso não estabelece falha observada,
nem muda a análise selecionada do FVP com callback presente.

## Avanço condicionado à conclusão da iteração

R9 guarda o índice capturado antes do callback. Após os hooks, a continuação
recarrega o descritor do canal (stride72), sua contagem em+52 e o ponteiro
do índice em+16. A sequência SUBS/SBCS/NEGS/AND implementa:

`inc = u32(old + 1); next = (inc == count ? 0 : inc)`

A store é `0x392fe`, seguida do salto para `0x391fe`. Para configuração
válida count>0 e old<count, corresponde ao avanço circular. Para old=5 e
count=3 produz6, não0: **não é normalização módulo para índices arbitrários**.
Count é uma leitura viva posterior ao callback; o valor nominal3 do canal1
não é uma constante garantida por esse trecho.

Com índice válido2/count3, retornos0,10,65536 ou0xffffffff seguem o mesmo
avanço para0, sob as condições acima. A resposta pode já ter sido publicada
pelo FVP antes de retornar, mas publicação não garante que os hooks seguintes
terminem nem que o índice seja efetivamente atualizado no aparelho.

## Saída local não agrega os erros dos callbacks

O braço `0x39302..0x39310` remove o canal selecionado da máscara de
pendências quando o teste anterior o considera vazio. Quando a máscara
fica zero, `0x39312` coloca **R0=0** antes do epílogo. Essa saída local não
agrega os resultados dos callbacks previamente salvos no frame+4.

A cadeia delimitada é: erro u32 do relay → retorno FVP preservado →
logging do dispatcher; o avanço selecionado não depende desse erro, e a
saída normal após esvaziar a máscara devolve0. Isso reforça que zero no BL2,
zero do dispatcher e aceitação física do DMC são evidências diferentes.
Não se excluem políticas externas, outros caminhos, handlers ou interrupções.
Slot47/X0 continua aberto; nenhuma rotina DMC foi analisada nesta rodada.

## Reprodução

[Extrator](../scripts/inspect_newtime_dispatch_completion_hzc2.py),
[JSON](references/newtime-dispatch-completion-hzc2.json) e
[nove testes](../scripts/test_newtime_dispatch_completion.py).
O extrator confere tamanho/hash, cobertura GNU, bytes, alvos relativos e
19 operandos selecionados. O teste interpreta palavras Thumb cruas da
sequência do índice, com528 configurações válidas e256 pares aleatórios,
limites u32, resultado não zero e contagem alterada. Orçamento do host
não é timeout do firmware; acessos ausentes recusam a fixture.

```sh
python3 scripts/inspect_newtime_dispatch_completion_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime_dispatch_completion.py'
```
