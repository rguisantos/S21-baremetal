# HZC2: canal direto 3 e gate do método +0 DVFS

Continuação estática de 2026-10-29 (Campo Grande), base `a3610ff`.
Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets do arquivo; endereços core e AP são indicados separadamente.

**O caminho direto selecionado chega ao método +0 do DVFS, cujo gate local
é uma leitura de 0xa590010c comparada com 0xabcd1234.** O callback não lê
seus argumentos. O clear AP de 0x15900104 não foi ligado a uma barreira
para o consumo DMC. A ausência de leitor permanece limitada a esse trecho;
não há censo completo dos leitores possíveis.

## Canal 3 e encaminhamento

Sob os dois mapeamentos ACPM já delimitados e preservação do dataset:

| Campo | Evidência do arquivo | Uso selecionado |
|---|---|---|
| Registro do canal 3 | arquivo 0x3b498, core 0x7498; stride 72 | base core 0x73c0 + 3×72 |
| Tipo, +12 | 2 | caminho direto, distinto da fila do canal 1 |
| Pedido, +24 | 0xa5900100 | 0x393a0 captura o ponteiro em frame+16 |
| Resposta, +48 | 0xa5900108 | alocador 0x386e0 retorna diretamente esse ponteiro |
| Count / stride, +52/+56 | 1 / 16 | dados iniciais, sem atribuição a RAM viva |
| Mapa de plugins | core 0x799c[3] = 7 | DVFS |
| Interface DVFS, método +0 | core 0x2e828[0] = 0x29699 | Thumb nominal no arquivo 0x56e98 |

O alocador 0x398e8 pula esse registro por seus ponteiros não zero. Não
atribuir a ele os índices de fila gerados para os canais 0/1. No evento
128 com máscara exatamente 8, o decoder 0x39c34 percorre o fallback de
prioridade, seleciona canal 3 e retorna plugin 7. Máscaras simultâneas
podem selecionar outro canal; um teste com 8|2 exercita essa diferença.

O dispatcher direto 0x3933c captura +24/+28, lê a palavra 0 do pedido
para o header e consulta a interface do plugin. Em 0x39416 chama o método
+0 com R0=&frame[16] (endereço da célula que contém o ponteiro do pedido)
e R1=3. O tipo de evento, máscara, status, interface instalada, raízes,
retornos dos helpers e entrega física continuam condições. A entrada
selecionada dos testes é 0x39386, após os gates de status anteriores.

## Dois magics diferentes

O corpo 0x56e98..0x56eac faz uma única leitura de 0xa590010c em 0x56e9c.
Compara com o literal **0xabcd1234** em 0x56eb0. Se diferente, pula o BL;
se igual, chama **0x5a938** em 0x56ea4. Ao retornar desse helper, ou ao
pular a chamada, grava R0=0 e retorna. Não há repoll no callback.

O magic de init7 é **0x1234abcd**, publicado em 0x56e6e. Portanto a
publicação de init7, mesmo fresca e preservada, não satisfaz essa outra
igualdade. O produtor do valor inverso não foi demonstrado nesta rodada.
Retorno zero do callback não comprova que o helper foi chamado, que ele
teve sucesso ou que as máscaras ficaram prontas.

A cauda selecionada 0x5a994..0x5a99e zera 0xa590010c. O corpo anterior do
helper contém chamadas e outros caminhos; não se demonstrou aqui que toda
invocação alcance essa cauda, nem a ausência de leituras transitivas de
0x104. O hook dos testes substitui esse corpo, sem certificar seus efeitos.

## O que significa para o clear AP

Em 0x18018 o BL2 zera AP 0x15900104 depois do retorno de 0x18000→0x1dc90.
Sob o alias AP/local candidato, esse endereço é a **palavra 1** do buffer
direto em 0xa5900100. O prefixo selecionado do dispatcher e o corpo local
do callback não leem essa palavra. O teste funciona deixando seus bytes
sem mapeamento; memória ausente provoca falha se for lida.

Isso não prova que o endereço jamais seja lido. Tampouco prova que o clear
seja irrelevante, que gere um evento, ou que uma palavra de pacote possa
ser interpretada como sinal de prontidão. Os acessos diretos 0x397b0 e
0x39cb0 que também usam deslocamento 0x104 constroem **0xa5910104**; os
da região 0x545d2 usam **0xa5960104**. Não são leitores do endereço alvo.

A [ordem parcial anterior](newtime-dmc-init-order-hzc2.md) continua válida:
nenhuma nova aresta ordena init9 contra as stores tardias das máscaras.
Aliases, visibilidade, estado físico, chamadas intermediárias e slot47/X0
seguem abertos. Próximo: encontrar um produtor do magic 0xabcd1234 e
rastrear os efeitos transitivos de 0x5a938, incluindo seus consumidores DMC.

## Reprodução

```sh
python3 scripts/inspect_newtime_fast_channel_hzc2.py /caminho/sboot.bin --json /tmp/fast-channel.json
python3 -m unittest discover -s scripts -p 'test_newtime_fast_channel.py'
```

[Extrator](../scripts/inspect_newtime_fast_channel_hzc2.py),
[17 testes](../scripts/test_newtime_fast_channel.py) e
[JSON](references/newtime-fast-channel-hzc2.json).
GNU confere 392 instruções Thumb/52 alvos relativos, três literais,
sete palavras A64 e 25 operandos selecionados. O hash e tamanho são
conferidos antes do GNU. Sem execução Samsung, novo QEMU ou amostra física.
Os avaliadores usam palavras reais, memória explícita e hooks opacos;
registradores voláteis são alterados nos hooks de integração. Os testes
cobrem o decoder, skip da alocação, encaminhamento do ponteiro, magics,
argumento não desreferenciado, retorno e clear da cauda isolada.
