# HZC2: método +56, comando 6 e espera de resposta

Análise estática de 2026-10-28 (Campo Grande), base remota `e00c9b1`.
O método chamado entre o backup e a restauração do
[buffer do slot38](newtime-slot38-buffers-hzc2.md) tem uma resolução
condicional concreta: **publica quatro palavras e espera uma resposta**.
Isso delimita uma aresta antes opaca; não demonstra consumo físico do
buffer alterado nem o significado do comando no destinatário.

Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs/células usam offsets de arquivo; delta BL2 nominal `0x020ea000`.
Sem execução Samsung ou ampliação do escopo QEMU.

## Binding e argumentos

| Aresta | Resolução sob preservação |
|---|---|
| `0x2256c` | slot20 da tabela A, célula `0x314a8`, W0=k/W21, W1=0 |
| Célula inicial `0x314a8` | `0x02119488`, alvo de arquivo `0x2f488` |
| `0x2f490/0x2f494/0x2f498` | lê binding `0x31998`, método +56, BLR |
| Provedor selecionado `0x307e0` | publicado pelo caminho de inicialização já delimitado |
| `0x307e0+56 = 0x30818` | `0x02101d84`, alvo nominal `0x17d84` |
| `0x17da0` | BL `0x17d1c`; este chama envio `0x17c04` e espera `0x17cb0` |

O [binding até a SMC](newtime-smc-binding-hzc2.md) trata do método **+72**
do mesmo provedor, uma aresta diferente. Neste caminho +56 os dois helpers
são folhas sem SMC/HVC/BL/BLR. Sua preservação de X7/X8 e X19..X29 foi
conferida no corpo selecionado, sem presumir ABI para esses registradores.

## O dado realmente selecionado

R é `M64[nominal(0x31a60)]`. `0x17d30` lê o u16 em R+20; `0x17d38`
forma `u64(R + offset16 + (u32(k)<<2))`. O shift estende W antes de somar
em X: para k=0xffffffff, o deslocamento é **0x3fffffffc**, não 0xfffffffc.
`0x17d40/0x17d4c` lê uma palavra e conserva seus 24 bits baixos.

O frame local contém, em +16/+20/+24/+28, `{0, valor24, 6, 0}`. O envio
recebe ponteiros para +16/+20/+24 e publica **`{0, valor24, 6, 6}`**: a
quarta store relê +24, não +28. Não há teste sintático de k nesse helper.

O buffer B não é um argumento direto do método, e o trecho não estabelece
uma dependência de seu byte alterado para valor24. R, seus metadados e
seus aliases continuam dinâmicos. A célula R é all-ones no arquivo;
esse valor inicial não foi atribuído à memória ativa. O produtor selecionado
de R em `0x19084`, descrito na
[análise do resultado secundário](newtime-secondary-result-hzc2.md), não
prova a preservação integral da tabela selecionada por k.

## Produtor selecionado: vetor MIF, offset u16 e máscara

O driver chama `0x1aab4` em `0x1911c` para cada domínio e recebe um vetor U
em X0 (`0x1b35c` retorna X25). Em `0x1912c`, grava
`low16(U-Rlate)` em `Rentry+52*domínio+20`. Assim, R+20 do consumidor
corresponde ao **primeiro domínio MIF**, e k escolhe uma palavra desse
vetor; o consumidor não multiplica k por 52 para escolher outro domínio.

Essa ligação exige Rentry=Rlate=Rconsume, publicação/preservação e
`u64(R+low16(U-R))==U`. Um vetor a mais de 65535 bytes da raiz, ou um
vetor anterior a ela, pode falhar nessa reconstrução. O truncamento u16
não é prova de que a condição sempre vale para o alocador em execução.

No final da continuação, `0x1b198` grava
`(anterior&0xff000000)|(u32(level[i]*1000)&0x00fffff8)` em U+4*i.
O payload ASV MIF preservado tem 13 níveis:
`3172,2730,2535,2288,2028,1716,1539,1352,1014,845,676,546,421`.
Sob conclusão desse laço, vetor/níveis estáveis, roundtrip válido e k<13,
o valor24 enviado é respectivamente `3172000,...,421000`.
São valores derivados dos bytes fornecidos, sem atribuição de unidade física.

A rejeição do slot38 não aborta o wrapper anterior: o método +56 ainda
recebe k mesmo quando a folha retorna -1. O filtro 0..7 daquela folha não
é uma guarda de k<13 para este acesso. Entradas u8 maiores permanecem
na fronteira dinâmica, sem afirmar que ocorram fisicamente.

As correções MARGIN anteriores mudam o byte superior. Sob as mesmas
condições de palavra/vetor, a máscara low24 do pedido remove esse byte.
Isso não prova que as correções sejam irrelevantes para outros consumidores.
U é o vetor da continuação ASV; o **B temporário das colunas 6/7** é outro
rótulo, cuja disjunção física de U continua condicionada a aliases.

## Configuração e publicação

O estado nominal usa `0x307c0` (base de registradores, inicial 0x15900000),
`0x307c8` (canal, inicial 1), `0x307d0` (TX), `0x307d4` (RX),
`0x307d8` (contagem) e `0x307dc` (passo). Os quatro últimos u32 são zero
no arquivo. Não são amostras runtime ou prova de configuração válida.

O BL `0x17fb4` chama `0x17dbc`, que calcula
`T=u32(M32[AP0x02041008]+0x02039000)`. Se o resultado é zero, retorna
sem publicar os quatro campos. Senão, publica TX/RX somando 0x02039000
em W às palavras de T+96/T+120; contagem/passo vêm de T+124/T+128.
Um offset de entrada zero **não** faz T zero. O código não demonstra
limites do objeto T ou o preenchimento físico desses campos.

Em `0x17c04`, i vem de `M32[u32(TX-4)]`. As quatro stores usam
`u32(TX+{0,4,8,12}+i*passo)`, zero-estendido para o endereço. TX e passo
são **recarregados entre stores**; agrupá-las numa única linha pressupõe
configuração e fontes do pacote estáveis. Depois incrementa i em W,
aplica UDIV/MSUB com contagem relida e atualiza o índice. Contagem zero
produz quociente UDIV zero e conserva o incremento truncado no MSUB;
não equivale a uma exceção de módulo no host.

Finalmente grava 0xffff em base+32 e `1<<((u32(canal+16))&31)` em base+8.
O alias LSL W mascara o contador em cinco bits. O corpo não contém guard
de fila cheia/capacidade nem barreira explícita. Isso não estabelece
política do destinatário, ordenação de hardware ou vulnerabilidade.

## Espera e retorno

`0x17cb0` captura RX, passo e base de registradores antes do poll. Repete
`0x17cd0` enquanto os quatro bits baixos de `M32[base+40]` forem zero ou
a palavra `M32[u32(RX+M32[u32(RX-8)]*passo)]` diferir do esperado.
O esperado é `palavra0_do_pedido & 0xffff0000`, igual a zero para este
pacote preservado. A comparação usa **a palavra completa da resposta**;
uma resposta 1 é rejeitada mesmo tendo os 16 bits altos zero.

Não há timeout/limite de tentativas no corpo selecionado. Depois do match,
relê o índice RX e a contagem, avança e grava o índice, relê a base e
grava 2 em base+32. Não copia um corpo de resposta para os argumentos.
O retorno deste helper é a base de registradores, não um código de sucesso.

O wrapper `0x17d84` escreve byte 0x5a em P_before+25 quando W1=0, antes
do pedido. Depois da espera, **relê P** de `0x31a68`, zera P_after+25 e
a palavra P_after+20 e retorna P_after em X0. Se P mudou, a primeira marca
pode permanecer em outro objeto. A célula inicial também é all-ones.

O slot20 sobrescreve X0, carrega `0x31040` e faz BR em `0x2f4ac` com W0=4;
o alvo inicial é `0x2a24c`. Seus efeitos transitivos permanecem abertos.
Somente o retorno de toda essa cadeia permite alcançar a restauração B.
Restaurar os 72 bytes de B não inclui as stores da fila, índices ou
registradores e não prova desfazer um pedido já consumido.

## Reprodução e fronteira restante

```sh
python3 scripts/inspect_newtime_method56_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_method56_hzc2.py),
[32 testes](../scripts/test_newtime_method56.py),
[JSON](references/newtime-method56-hzc2.json) e
[validação](references/newtime-method56-validation-20261028.json).
GNU: 207 palavras, 14 alvos relativos e 107 operandos selecionados.
Os testes incluem palavras aritméticas reais decodificadas independentemente,
wrap W/X, divisão por zero, match exato, recarga P e contraexemplo de fila
que permanece alterada depois de restaurar outro buffer.

Próximas arestas: escritores dos metadados R+20/tabela de palavras,
produtor/consumidor da configuração de canal, destinatário do comando6
e BR `0x2f4ac → 0x2a24c`. Valores físicos, aliases, viabilidade conjunta,
consumo do buffer B e chamador/X0 do slot47 continuam abertos.
