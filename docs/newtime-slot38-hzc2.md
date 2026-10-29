# HZC2: slot 38, máscara da coluna 13 e efeito no descritor

Análise estática de 2026-10-28 (Campo Grande), base `8b1dabd` do PR #50.
O alvo inicial do slot 38 foi seguido: é uma folha de 13 palavras, sem
stores ou chamadas, que consulta uma máscara e retorna o índice ou -1.
No chamador selecionado, o retorno decide uma alteração de um byte.
Esta cadeia não demonstrou chamador nem X0 do slot 47.

Mesmo sboot HZC2 de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; delta nominal BL2 `0x020ea000`.
Não houve execução de firmware, leitura do aparelho ou ampliação QEMU.

## Entrada e contrato da folha

O [segundo switch](newtime-jump-tables-hzc2.md) em `0x2f90c` seleciona
`0x2fa54` para W0=0. Nesse braço, bit 12 de AP`0x02073698` precisa estar
ligado. `0x2fa68` copia o **W4 recebido** para W0; `0x2fa74/78` carregam
e chamam a célula `0x31538`, slot 38 de `0x31408`. Seu ponteiro inicial
`0x021172e4` corresponde a `0x2d2e4`.

A folha `[0x2d2e4,0x2d318)` faz duas cargas nesta ordem:

| PC | Acesso nominal | Largura |
|---|---|---|
| `0x2d2ec` | célula `0x318f0`, produzindo P | 8 bytes |
| `0x2d2f0` | P+68, produzindo mask | 4 bytes |

Ambas antecedem qualquer retorno antecipado. A comparação anterior do
índice **não protege** a segunda leitura para índice inválido/P nulo.
A célula é zero no arquivo; seu conteúdo em execução não foi medido.

Com as cargas concluídas, index/mask como padrões W32:

```
se signed32(index) > 7 ou mask == 0: retorno W0 = 0xffffffff
senão: retorno index se bit(mask, index & 31) == 1, ou 0xffffffff
```

CCMP usa condição signed LE; ASRV W usa cinco bits do contador. Assim,
`0xffffffe0` pode ser devolvido com mask=1. O padrão -1 continua sentinela,
mesmo quando bit31 está ligado. Todos os caminhos escrevem W0 e deixam
X0 zero-estendido: a sentinela é `0x00000000ffffffff`, não -1 em X64.
Só X0/X1 e NZCV são alterados pelo corpo; SP e X2..X30 não são escritos.
Não há SMC/HVC, stores ou chamadas. P pode apontar a uma região com efeitos
de leitura; ausência de stores não prova ausência de efeitos físicos.

## Origem nominal de P: coluna 13

Dois produtores selecionados publicam o ponteiro em `0x318f0`:

| Store | Cadeia | Condição adicional |
|---|---|---|
| `0x2d734` | lê W em AP`0x02073864`, soma W `0x02073600`, SXTW, STR X em S+616 | caminho de `0x2d568` alcançado; S=`0x31688` |
| `0x2efc0` | mesma soma W e SXTW, STR X por ADRP+2288 | bit31 de AP`0x158609b0` desligado |

A soma sofre wrap em 32 bits **antes** da extensão de sinal. Não equivale
a somar o offset sem sinal à base em X64. Não se afirma que sejam todos
os escritores possíveis da célula, inclusive por alias/cópia.

Sob construção completa e alias fixo do registro NEWTIME em AP`0x02073600`,
o descritor R+`0x260`/AP`0x02073860` é a **coluna 13**, índice de laço 12.
A chave dessa coluna não participa da transformação dos índices 0..8.
As 22 linhas do seletor apontam para três subtabelas:

| Chave | Payload no arquivo | Forma | u32 em +68 |
|---|---|---|---|
| `0x81` | `0x77644` | 23×1 u32, 92 bytes | `0x1ff` |
| `0x82` | `0x776ac` | 23×1 u32, 92 bytes | `0x1ff` |
| `0x83` | `0x77714` | 23×1 u32, 92 bytes | `0x1ff` |

Isso não prova conclusão da construção para toda combinação de gates.
Quatro planos condicionais das linhas 10/15 e branch masks 0/0x1ff
registram os offsets diferentes do payload. Seleção real, alias, gates e
preservação entre cópia/publicação/leitura continuam condições.

## Argumentos anteriores e filtro unsigned do índice

A célula `0x314a0`, slot 19 da tabela A, aponta inicialmente a `0x2f90c`.
No BLR `0x22538` de `0x22370`, as definições locais fornecem W0=entrada W0
(salvo em W24), W4=entrada W1 (salvo em W21) e X2=buffer calculado em X20.
ADRP `0x22380` + ADD `0x224f0` + LDR `0x2251c` ligam a célula, sob
preservação de X23. Chamadas intermediárias e memória/frame exigem
preservação explícita; não se tomou a ABI como execução observada.

Inventário de B/BL alinhados em `[0x16000,0x2fd00)` encontra nove chamadas
diretas a `0x22370`. Seus seletores imediatos são:

| Seletores | PCs das chamadas |
|---|---|
| 0 | `0x249d4`, `0x24ad8`, `0x25010`, `0x260f8`, `0x269c4` |
| 1, 2, 3, 4 | `0x25e5c`, `0x247b4`, `0x24c28`, `0x26834` |

Nos cinco casos 0, LDRB W0 é seguido por chamada nominal do slot 22,
MOV W1,W0 e MOV W0,0. Slot 22, célula `0x314b8`, tem alvo inicial
`0x2f484`, uma única instrução RET: conserva o X0 do byte. Sob esse
binding e transporte preservado até `0x22538/0x2fa78`, index é u8.
As outras quatro chamadas selecionam braços que não chegam ao slot 38.
Os bases recebidos das cargas de slot 22 continuam condições nominais.

Com index u8 e mask=`0x1ff`, a folha aceita **0..7**; rejeita **8..255**,
mesmo tendo bit8 da máscara ligado. Os índices signed negativos do
contrato geral da folha não são demonstrados nesses cinco caminhos.
Outros chamadores indiretos ou bindings alterados permanecem abertos.

## Efeito depois do retorno e limite de aliases

X19 salva o X2 de entrada do dispatcher. CMN W0,1 em `0x2fa7c` testa
exatamente a sentinela `0xffffffff`. Retorno zero é sucesso. Se não for
sentinela, `0x2fa84/88/8c` lê o byte em X19+1 e o regrava com bit1 limpo;
com sentinela, pula a store. Gate desligado evita a chamada e essa store.
O X1 de entrada já foi substituído pelo ponteiro de função na chamada.

A folha não publica ponteiros nem escreve no binding `0x31998`. Porém o
destino do byte pertence a um buffer calculado: não se provou ausência de
alias com slots/globais. Também não se resolveu preservação física de P,
dos slots ou do gate. Não há exclusão global de uma ligação ao slot 47.

A [continuação dos buffers](newtime-slot38-buffers-hzc2.md) delimita agora
B pelas colunas 6/7 nos perfis completos e mostra o backup/restauração de
72 bytes. A exclusão do endereço calculado não cobre a pilha nem os
efeitos do método +56 chamado antes da restauração.

## Reprodução

```sh
python3 scripts/inspect_newtime_slot38_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_slot38_hzc2.py),
[testes](../scripts/test_newtime_slot38.py),
[evidência](references/newtime-slot38-hzc2.json) e
[validação](references/newtime-slot38-validation-20261028.json).
GNU confere 363 palavras, 35 alvos relativos e 73 operandos selecionados.
Os 28 testes novos incluem decodificador independente restrito às 13
palavras reais: 3922 combinações index/mask, flags CCMP, ASRV W, extensão
W/X e ordem das cargas. É interpretação de host, não firmware no QEMU.
