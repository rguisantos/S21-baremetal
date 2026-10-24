# BL2 HZC2: registro que alimenta a geometria anterior

Análise de **2026-10-24 (Campo Grande)**. Mesmo sboot de 4194304 bytes,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
A primeira palavra de geometria tem dois caminhos de recarga a partir de
**`0x02073600`**. O endereço de origem foi recuperado, mas seus bytes no
aparelho e sua correspondência a bytes do arquivo continuam desconhecidos.

Complementa o [produtor do total](bl2-ram-size-hzc2.md), a
[consulta](bl2-geometry-query-hzc2.md) e a
[reescrita das bases](bl2-query-base-rewrite-hzc2.md). O novo inspetor é
somente estático: não aceita geometria fictícia nem executa callbacks.

## Duas recargas da primeira palavra

Os destinos abaixo são relativos ao arquivo/estado nominal. Não são
endereços físicos medidos. O estado base é relativo `0x31688`.

| Caminho | Leitura de 64 bits | Escrita de 64 bits | Byte derivado dos bits 4–7 |
|---|---|---|---|
| Função registrada `0x2d364` | `0x2d378`, de `0x02073600` | `0x2d37c`, para `0x31978` | `0x2d388`, para `0x31939` |
| Trecho de `0x2d568` | `0x2d7e0`, mesma origem | `0x2d7e4`, mesmo destino | `0x2d7fc`, mesmo byte |

`0x31978` é o primeiro dos quatro u64 usados pela folha de tamanho. O byte
em `0x31939` recebe somente o nibble extraído, com os demais bits do byte
zerados. Isso não recupera os outros três slots nem atribui semântica de
canal/rank aos campos.

O primeiro caminho também pode atualizar o ponteiro de contexto em
`0x31998` quando X0 não é zero, e depois chama outros callbacks. Sua célula
`0x31580` contém `0x02117364`, alvo nominal `0x2d364` com delta
`0x020ea000`; nenhum chamador dessa função foi resolvido nesta entrega.
Um ponteiro registrado não comprova execução.

No segundo caminho, X19 deriva da página X6 em `0x2d5ac` e do ADD em
`0x2d6d0`. Essa ligação é uma hipótese de contexto do trecho selecionado,
sem executar a função inteira, seus ramos de erro ou chamadas externas.
As escritas de outros campos de estado nesse trecho não foram modeladas.

## Marcador e ligação com a fase anterior à consulta

`0x1e2c0` produz o literal **`0xcafe`** e `0x1e2c4` o grava como u64 em
`0x31978`. Em seguida, aparecem dois calls indiretos:

| Call | Célula nominal | Ponteiro / alvo nominal | Argumentos identificados |
|---|---|---|---|
| `0x1e2d0` | `0x31510` | `0x021196c0 → 0x2f6c0` | X0 recarregado do campo com o marcador |
| `0x1e2e0` | `0x314c8` | `0x02117568 → 0x2d568` | W0=12, W1=12 |

O segundo alvo contém a recarga de `0x02073600`. Não se conclui que ela
sempre ocorre: há configuração intermediária, ramos e efeitos externos.
A ligação nominal também depende da preservação de X19/X20/X25 no chamador.
O `0xcafe` é estado intermediário produzido pelo código; não pode ser usado
como geometria medida ou convertido em capacidade física do S21.

## Cópias que podem transportar o registro

As [cópias fixas já conferidas](descriptor-provenance-hzc2.md) incluem o
intervalo da primeira palavra. Com seus literais, os oito bytes seguiriam:

| Helper | Origem da palavra | Destino condicional |
|---|---|---|
| `0x161d8` | `0x02073600` | `0x021ab600` |
| `0x16200` | `0x021ab600` | `0x9004a600` |

É uma tradução de intervalos: não demonstra que os helpers rodaram nessa
ordem, quais bytes copiaram ou uma origem no sboot bruto. O inspetor não
lê o arquivo nesses valores como se fossem offsets. A relação continua
válida como hipótese condicional, sem virar um snapshot do aparelho.

## Limpeza e restauração parcial no registro

No corpo `0x2f724`, se o retorno anterior em W0 for zero, o ramo em
`0x2f744` chega à chamada `0x2f788 → 0x1f9e8`, com destino `0x02073600`,
byte zero e quantidade **44 bytes**. O helper de nove instruções confere
como preenchimento de bytes para essa quantidade. Retorno do gate,
execução da limpeza e estado depois da função inteira não foram observados.

Outro gate, em `0x2f7fc`, pula seis cópias de campos se o bit 0 do byte
de estado relativo `0x31966` estiver ligado. Caso siga pelas cópias, cada
transferência tem **32 bits**:

| Offset | Origem | Destino |
|---|---|---|
| `+0x28` | `0x021ab628` | `0x02073628` |
| `+0x4c` | `0x021ab64c` | `0x0207364c` |
| `+0x34` | `0x021ab634` | `0x02073634` |
| `+0x50` | `0x021ab650` | `0x02073650` |
| `+0x6c` | `0x021ab66c` | `0x0207366c` |
| `+0xa0` | `0x021ab6a0` | `0x020736a0` |

As origens concordam com o deslocamento da primeira cópia BL2. **Nenhum
desses seis destinos intersecta `[0x02073600,0x02073608)`**. Essa restauração
parcial não fornece a geometria da primeira palavra. Também não prova que
ela permaneça zerada ou inalterada, pois a função e a cadeia têm outras
operações e estados herdados.

## Reprodução e validação

```bash
python3 scripts/inspect_bl2_geometry_record.py /caminho/sboot.bin
python3 scripts/check_bl2_geometry_record_gnu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
```

O inspetor exige tamanho/SHA-256 exatos, confere os prefixos das recargas e
as larguras/registradores, deriva os endereços MOVZ/MOVK e preserva a origem
como `unknown_record_u64`. Não fornece conteúdo de registro, respostas
simuladas ou cálculo de RAM. Imagem incorreta retorna 2, sem JSON parcial.

**70 testes passaram**: 12 novos controles e 58 regressões BL2. Há recusas
para larguras, bases/registradores ou campos alterados, truncamento, spans
que cruzam o fim da cópia e sequência MOVK sem MOVZ. GNU objdump **2.44**
conferiu **148 palavras, dez destinos relativos, 18 operandos, quatro
produtores de endereço/marcador, seis cópias de campos e nove ponteiros/
literais**. Endereços e campos são reconstruídos pelo texto GNU e pelos
hexdumps, sem reutilizar o decodificador binário desses endereços.
Evidências [estática](references/bl2-geometry-record-hzc2.json) e
[GNU](references/bl2-geometry-record-gnu-hzc2.json).

Nenhum novo QEMU, firmware/MMIO/serviço executado ou blob adicionado.
O próximo passo é seguir os produtores da primeira palavra de
`0x02073600` e os gates que a preservam/substituem. Conteúdo real, demais
slots, bindings, respostas da consulta, eventual limite LK e FDT final
continuam pendentes. Endereço e recarga não estabelecem RAM livre.
