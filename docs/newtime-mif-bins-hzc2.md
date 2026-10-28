# HZC2: chamada MIF 0x1adcc → 0x1a668

Auditoria estática de 2026-10-28 (Campo Grande), após a continuação comum
do PR #50. O material GLM trouxe uma folha útil: dois argumentos u32 são
classificados por 13 limiares e publicados em três células globais.
**Não demonstra o chamador do slot 47 nem a origem de seu X0.**

## Parte confirmada independentemente

Mesmo sboot HZC2 de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets abaixo são de arquivo; delta BL2 **nominal** `0x020ea000`.
Não houve execução em aparelho, MMIO/SMC nem ampliação QEMU.

No [switch já enumerado](newtime-jump-tables-hzc2.md), somente a entrada 0
das 20 entradas iniciais seleciona `0x1ada8`. O LDP W de `0x1adc8` carrega
X0=zero_extend(M32[X22+16]) e X1=zero_extend(M32[X22+12]), seguido do BL
`0x1adcc → 0x1a668`. Essa é uma afirmação sobre o switch selecionado,
sob preservação; não exclui entradas alternativas ou chamadas indiretas.

X22 vem de linha/ponteiro dinâmico do descritor. A busca selecionada usa
stride em palavras; sem chave coincidente conserva a última linha examinada.
Quando a contagem signed não é positiva, pode conservar a base do caminho
de compactação ou um valor herdado. Não foi estabelecido endereço concreto,
validade dos campos ou conteúdo ECT em runtime.

A folha `[0x1a668,0x1a73c)` tem 53 palavras, nenhum BL/BLR e RET em
`0x1a738`. Reserva/restaura 64 bytes de pilha. Constrói a tabela:

`3172,2730,2535,2288,2028,1716,1539,1352,1014,845,676,546,421,0,0`.

O zero do índice 13 vem da metade alta de STR XZR sobreposto pelo 421
no índice 12; o índice 14 é explicitamente zero. O índice 15 não é lido
sob uma pilha privada, estável e válida. Cada laço encontra o primeiro
k com `entrada_u32 >= tabela[k]`; o zero garante k<=13. As comparações
são unsigned, inclusive para `0x80000000` e `0xffffffff`.

| Store | Célula nominal no arquivo | Valor |
|---|---|---|
| `0x1a6e0` | `0x31a70` | W1 recebido, bruto |
| `0x1a720` | `0x31a74` | bin(W1 recebido) |
| `0x1a6f8` | `0x31a78` | bin(W0 recebido) |

Os valores iniciais dessas palavras no arquivo são `0xffffffff`; isso
não estabelece seus valores no momento da chamada. Há também stores
na pilha: são três stores **globais nominais**, não somente três STR no corpo.
As três células são diferentes de `0x31580` e `0x31998`. Aliases de pilha
não foram globalmente excluídos.

## Contrato de saída corrigido

Sob o corpo, pilha e globais conservados:

| Registrador | Saída |
|---|---|
| X0 | bin(W1 recebido) |
| X1 | `0x0211b000` |
| X2 | tabela[bin(W1 recebido)] |
| X3 | tabela[bin(W0 recebido)] |
| X4..X30 | não alterados pelo corpo selecionado; RET lê X30 |
| SP | restaurado |

O anexo declara X2=13. Isso é incorreto: `0x1a710` recarrega W2 com o
limiar do segundo laço. No próprio interpretador de teste recebido,
W0=3172/W1=2730 produz X0=1 e **X2=2730**; W0=W1=0 produz X0=13 e X2=0.
São estados sintéticos de host, não valores medidos no aparelho.

O valor retornado em X0 é descartado na continuação selecionada. Uma
verificação por caminhos encontra dois primeiros overwrites possíveis:
LDR W0 em `0x1b00c` e MOV X0,0 em `0x1b038`. Não há uso de X0 antes
desses pontos nos oito PCs do prefixo. O teste linear do anexo só via o
primeiro overwrite; a conclusão correta foi conferida pelos dois caminhos.
A [continuação comum](newtime-common-continuation-hzc2.md) cobre os usos
posteriores do frame e do buffer.

## Outras correções da entrega externa

- A comparação em `0x1ad84` é **0x13 = 19**, não 0x19 = 25.
- ADR codifica deslocamento +12, não uma base absoluta. `derive_delta`
  fixa `0x2104da8` e só então subtrai o offset. O round-trip confirma o
  encoding sob a base escolhida; não deriva essa base independentemente.
- X2..X7 são voláteis e atravessam outras chamadas. Em particular,
  `0x1ad68` procura MARGIN via `0x1c55c`/strcmp. Se o nome coincide e seu
  handle runtime é zero, strcmp deixa W2=0 e o caminho até `0x1adcc`
  conserva X2=0. Não é uma cadeia de preservação do argumento GEN.
  O callee só consome W0/W1; os outros argumentos não precisam ser inventados.
- O scan B/BL em `[0x16000,0x2fd00)` encontra `0x1adcc` para a folha e
  `0x1911c` para `0x1aab4`. Não prova que sejam os únicos chamadores globais.
- O scan incompleto de escritores não prova exclusividade. Além de perder
  valores em desvios, conserva X2 depois de escrever W2. O exemplo sintético
  ADRP X2,0x211b000; EOR W2,W2,W2; STR W0,[X2,#2672] é reportado como
  escrita em `0x211ba70`, embora X2=0 torne o endereço `0xa70`.
- Flags negativas e o texto sobre ausência de leitores no JSON externo
  têm campos fixos, sem o correspondente teste derivado no extrator.
  As referências v5 aos dois escritores do binding são referências externas,
  não uma nova prova de cobertura ou preservação.

## Reprodução e limites

```sh
python3 scripts/inspect_newtime_mif_bins_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

O [extrator próprio](../scripts/inspect_newtime_mif_bins_hzc2.py) exige
tamanho/hash e confere GNU 203 palavras, 37 alvos relativos e 34 operandos.
Deriva a tabela, as células, o limite unsigned e os primeiros overwrites.
Os [testes](../scripts/test_newtime_mif_bins.py) cobrem limites, unsigned,
X2/X3 de saída, os dois caminhos do retorno e invariância de translação ADR.
[JSON](references/newtime-mif-bins-hzc2.json) e
[validação](references/newtime-mif-bins-validation-20261028.json).

Os anexos externos reproduziram **29/29 testes**, JSON byte a byte e
49/49 encodings GNU após adaptação apenas de caminhos/bibliotecas locais.
Isso não valida suas afirmações globais ou todos os campos textuais.
O motor externo não foi incorporado ao repositório.

Continuam abertos os efeitos de outros callees, dados ECT dinâmicos,
aliases e a chamada real do slot 47. O parser MARGIN é uma próxima frente;
`0x1aff0` já tem análise independente e não precisa ser refeito.
