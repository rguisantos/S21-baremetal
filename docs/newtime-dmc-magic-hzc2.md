# HZC2: produtor local do magic DVFS e handshake do canal3

O produtor local de `0xabcd1234` foi encontrado em **`0x369a0`**, no corpo
AArch64 iniciado em `0x36974`. Ele grava AP`0x1590010c`, toca a campainha
em AP`0x15900008` e espera a palavra do magic ficar zero. Isso fecha uma
origem nominal antes aberta na [rota do canal3](newtime-fast-channel-hzc2.md).
A unicidade global do escritor e a entrega física do handshake continuam
sem prova.

Reprodução independente de 31/10/2026, Campo Grande, base main `20c472c`
após PR #70. Sboot HZC2:4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets do arquivo; endereços AP e locais ACPM são separados.
Nenhum SMC, MMIO físico ou operação no telefone foi executado.

## Correções do resumo externo

O resumo recebido descrevia uma rodada em base `e4d6ba0`, com dois
extratores e testes. Esses arquivos não estavam disponíveis nesta árvore,
na main ou nas branches publicadas consultadas. A busca pelos títulos
mencionados também não recuperou a entrega. Esta rodada reconstrói e testa
a evidência; não herda as contagens28/34,712/46 ou as16 fontes citadas.

Duas alegações foram limitadas:

- **`0x36000` não foi identificado como a entrada efetiva de um monitor
  EL3.** Fica no intervalo candidato BL2 e consulta CurrentEL, com caminhos
  para EL1/EL2/EL3. O contêiner candidato EL3 separado começa em
  `0x36c000`; veja [estágios do sboot](sboot-layout-hzc2.md).
- **Um censo de literais/imediatos não prova “único escritor”.** Não
  exclui valores calculados, cópias, aliases, acessos indiretos ou agentes
  externos. A conclusão adotada é um produtor local demonstrado.

A correção proposta para o poll é válida: um hook de BL não pode liberar
o laço que precede esse BL. Os testes usam uma substituição `timed_word`,
como a [suíte DMC método12](../scripts/test_newtime_dmc_method12.py), para
fornecer a limpeza externa durante a terceira leitura.

## Entrada e publicação

A entrada selecionada usa AP`0x15860804` para escolher a pilha:
`0xbad` seleciona `0x02039000`; outro valor seleciona `0x0225a000`.
Aplica alinhamento de16 bytes, chama o helper em `0x360f8` e chega ao BL
`0x36084 → 0x36974`. Os quatro literais e os destinos foram conferidos;
valores PMU e EL efetivos não foram adquiridos.

| Ordem local | Instrução/efeito |
|---|---|
| `0x36990/0x36994` | Lê u32 de AP`0x15863b50` e guarda no frame+28 |
| `0x369a0` | STR W1: AP`0x1590010c ← 0xabcd1234` |
| `0x369ac` | STR W2: AP`0x15900008 ← 0x80000` |
| `0x369b0/0x369b4` | LDR W1 / CBNZ: repete enquanto a palavra não zero |
| `0x369b8/0x369bc` | Recarrega a amostra PMU salva e chama `0x36934` |
| `0x369c0/0x369c4` | Restaura FP/LR/SP e retorna |

`0x80000 = (1 << 3) << 16`. O cruzamento com a
[referência ACPM](flop-acpm-reference.md) liga o offset8 ao INTGR0 e à
convenção de campainha por canal. O laço selecionado não contém timeout;
o orçamento do avaliador é uma proteção do host.

O helper `0x36934` inclui chamadas da segunda sequência de clocks já
[documentada](uart-clock-stages.md). Seus efeitos físicos e o resultado
completo dos callees não são inferidos deste handshake. O argumento vem
da amostra anterior ao poll, mesmo se um agente mudar o registrador depois.

## Relação com ACPM e continuação segura

A rota anterior, preservada nesta verificação, fornece evento128/máscara8
→ canal3/plugin7 → método+0 em `0x56e98`. Seu gate faz comparação exata
com `0xabcd1234`; o magic de init7, `0x1234abcd`, não satisfaz esse gate.
O corpo pode chamar `0x5a938`. Após os callees selecionados retornarem,
a cauda `0x5a998` grava zero em local`0xa590010c`.

A interpretação entre AP`0x1590010c` e local`0xa590010c` continua
condicionada ao alias e à visibilidade. A integração de host transfere
explicitamente o valor entre os dois espaços; não simula uma interconexão
física, a entrega do evento ou o corpo completo do agente ACPM.

Depois do retorno local, `0x36088` salta a `0x3624c`, que prepara:
X0=`0xffffffffffffff18` (−232), X1=X2=0, X3=`0xbffff000` e segue ao
veneer `0x36138`, `SMC0; RET`. Os testes param **antes** do SMC.
A implementação e o resultado desse serviço permanecem desconhecidos;
não são confundidos com os pedidos−231,−301 ou−1023 do LK.

## Busca negativa com alcance declarado

O extrator varre os bytes recebidos e registra:

| Busca | Resultado nesta imagem | Limite |
|---|---|---|
| Quatro bytes LE de `0xabcd1234`, toda a imagem | Um match em `0x56eb0` | É o literal de comparação Thumb |
| Candidatos A64 MOVK com imm16=`0xabcd`, alinhamento4 | Um em `0x36988` | Não recupera fluxo ou fronteiras globais de instruções |
| Candidatos Thumb MOVW imm16=`0x1234`, `[0x38000,0x67000)` | Nenhum | Não exclui construção por outras operações ou cópias |

A busca confirma a origem local sem promover ausência de outros padrões
a exclusão universal de produtores.

## Validação e próxima fronteira

São112 palavras A64,27 destinos,54 operandos e quatro literais, além das
392 instruções Thumb/52 destinos herdados da rota do canal3. Há22 testes
novos de publicação, atraso externo, bloqueio sem limpeza, PMU salvo,
pilhas, argumentos SMC, gate/cauda, mutações e recusas.

```sh
python3 scripts/inspect_newtime_dmc_magic_hzc2.py /private/path/sboot.bin > /tmp/dmc-magic.json
cmp /tmp/dmc-magic.json docs/references/newtime-dmc-magic-hzc2.json
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
python3 -m unittest discover -s scripts -p 'test_flop*.py'
python3 scripts/validate_baseline.py --output-dir build/baseline-newtime-magic
```

[Relatório](references/newtime-dmc-magic-hzc2.json) e
[validação](references/newtime-dmc-magic-validation-20261031.json) conservam
a reprodução. Próximo: condições reais do trampolim, implementação do
SMC−232, aliases/visibilidade e ordem do agente ACPM. Slot47/X0 permanece
aberto; encontrar este escritor não resolve esse despacho.
