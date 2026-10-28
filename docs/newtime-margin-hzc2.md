# HZC2: MARGIN, tabela de nomes e filtro dos consumidores

Auditoria estática de 2026-10-28 (Campo Grande), complemento do PR #50.
O payload MARGIN, o callback e a publicação do handle foram confirmados.
Uma correção de endereço resolve parte importante do consumo: **a tabela
de nomes é `0x30930`, não `0x31930`**. Com os nomes/registros preservados,
os candidatos MARGIN são os casos 0/19, cujas tags 255 pulam a store em Q.

## Payload e objeto publicado

Mesmo sboot HZC2, 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets abaixo são de arquivo; delta BL2 nominal `0x020ea000`.
Não houve execução de firmware, acesso ao aparelho ou ampliação QEMU.

O diretório ECT tem nove blocos. MARGIN é o último, offset `0x10f54`
relativo a `0x69000`, no arquivo `[0x79f54,0x7a0c4)`: 368 bytes.
O cabeçalho é `<I4sI>`: versão 2, texto `b'0.0 '`, contagem 2.
O fim dos dados coincide com origem ECT + campo de header `0x110c4`.
Isso não torna o tamanho do payload igual à reserva do alocador.

| Registro | Offset no bloco | Colunas +12 | Linhas +16 | Matriz no bloco | Bytes |
|---|---:|---:|---:|---:|---|
| MIF | `0x28` | 12 | 13 | `0x30` | 12×6, depois 144×4 |
| INTSCI | `0xcc` | 12 | 13 | `0xd4` | 24×8, depois 132×0 |

São **13 linhas de 12 colunas**, 156 bytes por matriz. O consumidor usa
o stride de 12 em u32(12*i+W19); não se deduz daí um limite para n/W19.
Os valores da tabela acima só determinam a carga quando o índice está
dentro da matriz e os dados são preservados até a leitura.

O registro MARGIN em `0x30a30` contém nome Q64, comprimento lido W32 em
+8, callback Q64 em +16 e handle Q64 em +24. O callback inicial
`0x0210596c` corresponde a `0x1b96c`; a célula do handle `0x30a48` é zero
no arquivo, sem estabelecer seu valor durante o boot.

No despacho selecionado `0x1c9c4`, sob preservação e alcance da entrada:
X0=`0x02163f54`, X1=`0x0211aa30`, X2=`0x0210596c`. A comparação do
despachante tem limite pelo comprimento do registro; não é prova de
igualdade completa de nomes de diretório malformados. As strings reais
da entrada selecionada coincidem.

O callback tem objeto **H=alloc(24)** e registros
**R=alloc(u32(48*contagem))**. Não se fixa o endereço de H/R omitindo as
alocações dos callbacks anteriores. Os helpers selecionados não alteram
X6..X10, sustentando o transporte de H, entrada e bloco em registradores
voláteis dentro do corpo. A publicação de sucesso em `0x1baa4` escreve
H em `[entrada+24]`, isto é, `0x30a48` neste caso.

| Campo construído | Valor para este payload |
|---|---|
| H+0, +4, +8 | versão 2, quatro bytes de versão, contagem 2 |
| H+16 | R, endereço runtime não estabelecido |
| registro+0, +8 | ponteiro do nome no blob e offset u32 do corpo |
| registro+12, +16 | 12 colunas, 13 linhas |
| registro+24, +32, +40 | zero Q64, ponteiro da matriz no blob, 6250 W32 |

Campos não escritos não são presumidos zero. A versão é comparada com 1
com condição signed: em versões <=1, +24 recebe o ponteiro e +32 recebe
zero; +40 não é escrito nesse braço. O payload real desta análise é versão 2.

## Lookup e endereço corrigido

`0x190b4` procura MARGIN pelo nome estático em `0x2fdd0`; o handle segue
X27 → X3 em `0x19104` → X23 em `0x1ab0c`. A busca inicial E em
`0x1ab7c` e a eventual substituição em `0x1ad74/0x1ad78` usam o nome
**sem prefixo**, guardado no frame+144. O nome MMIF construído para GEN
é outro argumento/caminho.

`0x1825c` faz ADRP nominal para o arquivo `0x30000`, soma `0x520+0x410`
e indexa em passos de oito bytes. Logo o nome está em
**`0x30930+8*índice`**. O deslocamento de página extra do anexo é incorreto.
As 20 strings incluem MIF, INT, CPUCL0, CPUCL1, …, INTSCI. Não são a
área zerada de `0x31930`; o slot 13 contém CAM em `0x30998`, sem sobreposição
com o binding `0x31998`.

`0x1c700` usa count signed em +8, array em +16 e registros de 48 bytes.
strcmp requer o nome completo; INT não corresponde a INTSCI. Com contagem
positiva, só os primeiros count registros são consultados. Handle zero
preserva o E anterior no chamador; handle presente com entrada ausente
substitui E por zero. A identidade concreta dos objetos continua condicional.

## Consequência para Q=B e a store secundária

| Índice/nome solicitado | Registro MARGIN possível | Tag do caso |
|---|---|---|
| 0 / MIF | MIF | 255 |
| 19 / INTSCI | INTSCI | 255 |
| 2 / CPUCL0 | nenhum | 0 ou 1 |
| 3 / CPUCL1 | nenhum | 0 ou 1 |

O extrator deriva os destinos da jump table e lê os MOV W27 dos dois casos
correspondentes, em `0x1adac` e `0x1ae10`. A folha do caso 0 conserva X27.
Não foi preenchida uma flag negativa constante a partir dos nomes esperados.

Sob a premissa de handles zero ou objetos MARGIN construídos com estes
registros, nomes/switch/frame preservados e tags conservadas, E só pode
corresponder a MIF/INTSCI entre os 20 casos selecionados. Em ambos a tag
255 pula a store `0x1b134` em Q. Nos casos 2/3 que podem
[retornar Q=B](newtime-secondary-result-hzc2.md), E é zero e o laço de
correção nem entra.

Portanto, **o efeito de duas adições descrito pelo modelo de código não é
demonstrado por este conjunto de dados MARGIN preservado**. O caminho Q=B
continua existindo. A conclusão se restringe a esses dados/chamadores:
objetos modificados, outros argumentos de entrada, aliases e mutações
continuam fora da exclusão. O teste sintético que acrescenta CPUCL0 aos
registros invalida a exclusão, como esperado.

## Limites e correções dos modelos recebidos

Os 44 testes, os dois JSONs idênticos e as 200 conferências de encoding/texto
GNU foram reproduzidos após adaptar somente caminhos/runtime. Há erros
adicionais que os testes não cobriam:

- `lookup_1c700(1, [A,B], B)` retorna B no modelo externo, que percorre
  toda a lista; o código para após o primeiro registro.
- Para comprimento `0xfffffffe`, o helper de nomes alinha em W32 e pula
  zero bytes. O modelo externo avança 4 GiB. O wrap acontece antes do ADD X.
- Cursor `0xfffffffffffffffc` + pedido 4 vira zero em X64, não 2^64.
- Os endereços H=`0x021640d8`/R=`0x021640f0` emitidos no JSON vêm de uma
  arena parcial sem os oito callbacks anteriores. Não são endereços runtime
  demonstrados; esta entrega usa símbolos H/R.

O BL de init em `0x160a0` precede o BL em `0x160bc` em ordem de programa
se ambos forem alcançados e retornarem normalmente. Gates, falhas de callback,
preservação do handle e efeitos das chamadas intermediárias impedem tratar
essa ordem sintática como observação de inicialização bem-sucedida no aparelho.

## Reprodução

```sh
python3 scripts/inspect_newtime_margin_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_margin_hzc2.py),
[testes](../scripts/test_newtime_margin.py),
[JSON](references/newtime-margin-hzc2.json) e
[validação](references/newtime-margin-validation-20261028.json).
GNU: 595 palavras, 111 alvos relativos e 62 operandos selecionados.
Os bounds do parser de host protegem as fixtures; não são guards atribuídos
ao firmware. Permanecem abertos n/W19, limites ASV, gates e estado runtime,
além do chamador e X0 do slot 47.
