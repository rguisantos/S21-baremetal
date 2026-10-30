# HZC2: efeitos locais do callback0 e rota nominal DMC17

Análise de 30/10/2026 (Campo Grande), base `3d3eeaa`, continuação da PR53.
Mesmo sboot de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets do arquivo; tradução core Thumb selecionada
`file=core+0x2d800`, sem alias físico observado.

**O modo2 de `0x5a2b8` seleciona uma chamada nominal ao DMC, subcomando17,
que encadeia o carregador de configuração e outro método.** Essa rota
estende o [callback0 alcançável por dependências](newtime-fast-apply-hzc2.md).
Também foi confirmado que o retorno-1 do lookup vira índice255 antes da
primeira leitura da linha, sem guard local desse erro.

## As duas primeiras chamadas são folhas com efeitos

`0x599ec` chama `0x59e34`, depois `0x5a004`, e por fim `0x5a2b8` com R0=2.
Os dois primeiros corpos não contêm chamadas nem polls locais:

| Corpo | Stores constantes | Leitura/modificação/escrita |
|---|---|---|
| `0x59e34` | `aa031800=2`, `aa331830=4`, `aa331034=2` | `aa030600 \|=0x10`, `aa030840 \|=1`, `aa030844 \|=1` |
| `0x5a004` | `aa3318d4=1`, `aa3310dc=1`, `a0021804=2`, `a0021000=0`, `a0021800=7` | `a0020600 \|=0x10`, `a0020850 \|=1`, `a0020800=(old&0x0effffff)\|0xf0000000` |

Os endereços da tabela são hexadecimais locais, sem atribuição de unidades
ou função física dos registradores. Valores anteriores são desconhecidos
fora das fixtures explícitas. A primeira folha preserva R0; a segunda
devolve em R0 a palavra antiga de `0xa0020600`, lida em `0x5a022`.
Não são retornos locais de sucesso/erro. O caller substitui R0 por2 antes
da terceira chamada. Stores anteriores não têm rollback se uma leitura
posterior falhar; o teste de memória ausente conserva os efeitos parciais.

## Lookup, truncamento e primeira linha consumida

O terceiro corpo captura o header H da entrada0 e a base B pela célula
core `0x2fbf4`. No modo não zero, lê o valor corrente high24 da entrada0
e chama `0x5acec`. Esse lookup usa count u8 do header+1 e níveis de low24:
seleciona o primeiro nível menor ou igual ao valor solicitado, ou o último
índice se nenhum satisfizer. **Somente count zero produz-1 nesse corpo.**

Em `0x5a30a`, UXTB transforma o resultado em k=low8. Não há teste de sinal
ou comparação com-1 antes de calcular a linha:

`linha = u32(B + M16[H+22] + M8[H+2] × k)`.

Assim, count0 dá k255. `0x5a328` lê linha+2 e grava core `0x2fdd4`;
`0x5a32e` lê linha+5 e grava core `0x2fdd8`. O teste com linha ausente
falha antes da chamada DMC17. Outro fornece explicitamente os bytes da
linha255 e confirma as duas stores. Isso prova o cálculo selecionado,
**sem estabelecer uma tabela vazia ou acesso fora da memória no aparelho**.
Os demais ponteiros/header/offsets vivos e a extensão das tabelas continuam
condições. O caminho modo0 usa header+8 como índice; não foi confundido
com o modo2 fornecido pelo callback.

A descrição anterior “lookup-miss retorna-1” foi corrigida no extrator/JSON
DMC8/9 e no documento do receptor: uma busca não vazia sem limiar satisfeito
usa o último índice. No caminho DMC8/9 há teste do retorno-1; o trecho
modo2 desta continuação faz o truncamento descrito acima.

## Modo2 → subcomando17 → dois métodos DMC

Depois das operações intermediárias selecionadas, `0x5a3a8` desvia para
`0x5a432` quando o modo é2. `0x5a43c` chama `0x5822c` com o byte header+8
e k. Essa ligação é condicional à chegada ao trecho; as operações entre a
primeira linha e esse branch não foram executadas por completo nos testes.

| Elo | Evidência |
|---|---|
| Wrapper `0x5822c` | Salva os dois argumentos u32 no frame; plugin9, R2=0, subcomando17 → relay `0x58170` |
| Método+12 DMC | Sob os [gates já auditados](newtime-dmc-method12-hzc2.md), tabela core `0x37cd0[17]=0x322ad` aponta para `0x5faac` |
| Handler `0x5faac` | Lê as duas palavras completas e chama `0x60198`; se o callee retorna, devolve0 sem agregar seu resultado |
| Wrapper `0x60198` | Chama método+96 de core `0x38038`; depois **relê** o método+192 e chama-o sem testar o primeiro retorno |
| Alvos iniciais | +96 → core `0x36fad`/arquivo `0x647ac`; +192 → core `0x37925`/arquivo `0x65124` |

O carregador `0x647ac` salva R0 no frame+20 e R1 em R4: recebe byte header+8
e k nesta rota. Seu [efeito conhecido no cache](newtime-dmc-config-hzc2.md),
em `0x648be`, instala uma base derivada do descritor14. Seu corpo completo
continua uma fronteira; a nova ligação não certifica as suas respostas,
retornos ou todas as stores. O teste integrado interpreta método+12,
handler17, wrapper e o segundo método, substituindo o carregador por um
hook explícito que também altera os registradores voláteis.

Mesmo se o primeiro método retornar erro, o wrapper selecionado chama o
segundo. Se o primeiro mudar o ponteiro+192, a chamada seguinte usa o novo
valor: não foi congelada a tabela inicial durante o hook. Bindings,
retorno dos callees e preservação continuam condições.

## Segundo método: raízes distintas e releituras

`0x65124` lê um byte em `M32[core0x383b0]+28`, lê uma palavra na base
`M32[core0x37e0c]+0xa94` e escreve em outra base:

`M32[M32[core0x37e1c]+0xa94] = (old & 0xfffffff0) | (byte & 15)`.

Depois relê a célula core `0x38268`, carrega a palavra do ponteiro+128 e
escreve em `M32[core0x37e08]+0x504`. Todos os endereços usam wrap u32.
Origem e destino não foram presumidos iguais. Uma fixture de alias faz
a primeira store alterar o ponteiro da segunda leitura; o resultado usa
o ponteiro relido. Isso demonstra dependência sequencial de memória, sem
afirmar que esse alias aconteça fisicamente.

R0 termina como core `0x38268`, sem código local de sucesso. O handler17
o sobrescreve com zero. A continuação externa em `0x5a440` também não testa
o retorno do wrapper17 antes de reler seu indicador. Há poll selecionado
em `0x5a488`, repetido enquanto bit16 está setado, sem timeout local.
O orçamento do host não é timeout de firmware.

## Validação e limites restantes

[Extrator](../scripts/inspect_newtime_domain0_callees_hzc2.py),
[20 testes](../scripts/test_newtime_domain0_callees.py),
[JSON](references/newtime-domain0-callees-hzc2.json) e
[validação](references/newtime-domain0-callees-validation-20261030.json).
GNU: 466 instruções/493 halfwords/41 alvos/47 literais/45 operandos.
Avaliador ganhou UXTB, BICS e LDMIA com base fora da lista; outras formas
continuam recusadas. Flags, zero-extension e wrap do writeback têm controles
com palavras reais. Três conjuntos de80 casos exercitam máscaras, lookup
e raízes distintas. Suíte NEWTIME: **643 testes aprovados**.

```sh
python3 scripts/inspect_newtime_domain0_callees_hzc2.py /caminho/sboot.bin --json /tmp/domain0.json
python3 -m unittest discover -s scripts -p 'test_newtime_domain0_callees.py'
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

Os relatórios desta continuação e DMC8/9 foram reproduzidos exatamente;
as imagens curta/longa/alterada são recusadas sem stdout/JSON pelo extrator
novo. Sem execução Samsung ou ampliação QEMU do firmware. O relatório
anterior de 623 testes permanece histórico da árvore `82d7fe0`; esta
validação cobre as extensões do avaliador e os artefatos atuais.

Próximo: restante do corpo `0x5a2b8` e do carregador `0x647ac`, incluindo
consumidores dos argumentos e gates. Produtor de `0xabcd1234`, ordem init9
versus máscaras, valores/aliases físicos e slot47/X0 continuam abertos.
Identificar DMC17 não prova a ausência global de DMC8/9 ou outros efeitos.
