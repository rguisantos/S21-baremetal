# HZC2: cópias selecionadas e transporte da célula 0x31580

Análise **estática, 2026-10-25 (Campo Grande)**, base `dc5e745` / PR #30.
**Não foi encontrado transporte da célula nem resolvido seu despacho.**
As sete cópias fixas selecionadas não intersectam a tabela nominal; três
janelas de cópias parametrizadas têm origens distintas. Outras 44 referências
ao helper de cópia permanecem sem análise de argumentos nesta entrega.
Nenhuma rotina foi executada no QEMU, no monitor seguro ou no aparelho.

## Janela auditada e hipótese de endereço

Mesmo sboot HZC2 de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
A célula de arquivo `0x31580` corresponde a **`0x0211b580`** pelo delta
nominal `0x020ea000`. A janela dos 48 slots começando em `0x31408` é
`[0x0211b408,0x0211b588)`, com fim exclusivo. Não se afirma que esse
intervalo descreva os limites de um objeto da linguagem fonte.

A comparação abaixo usa esse mapeamento. Não converte os literais das
cópias em offsets de arquivo nem atribui ao aparelho uma imagem viva.

## Sete cópias fixas

Reutilizado o decoder de corpos exatos do
[estudo de proveniência do descritor](descriptor-provenance-hzc2.md).
Ele confere três LDR X literais, laço, passos, condição e barreiras, antes
de aceitar os parâmetros. Todos os intervalos são semiabertos:

| Helper | Origem | Destino |
|---|---|---|
| 0x161b0 | 0x02120000–0x02122000 | 0x02036000–0x02038000 |
| 0x161d8 | 0x0203d000–0x0207a000 | 0x02175000–0x021b2000 |
| 0x16200 | 0x02175000–0x021b2000 | 0x90014000–0x90051000 |
| 0x16228 | 0x02122000–0x02127000 | 0x0203d000–0x02042000 |
| 0x16250 | 0x02127000–0x02151000 | 0x02048800–0x02072800 |
| 0x16278 | 0x02153000–0x02167000 | 0x90000000–0x90014000 |
| 0x162b4 | 0x02167000–0x02175000 | 0x15b00000–0x15b0e000 |

Nenhuma origem ou destino intersecta a janela da tabela. Portanto esses
corpos, com esses literais e mapeamento, não copiam a célula `0x31580`
nem sobrescrevem seu endereço nominal. O extrator também testa projeção
de **oito bytes completos**, sem promover uma interseção parcial a cópia
de um ponteiro completo. Execução, aliases, outros laços e serviços
externos continuam fora dessa conclusão.

## Cópias parametrizadas: frente ainda aberta

A busca de codificações B/BL alinhadas em `[0x16000,0xec000)` encontrou
**46 BL e um B** para `0x1fcc4`. Os 47 PCs constam no JSON e foram
conferidos no GNU; não são uma prova de que todos sejam chamadas alcançáveis.
O corpo de nove instruções lê byte de `[X1+X3]`, grava em `[X0+X3]`,
incrementa X3 e testa o restante em W. Não foi substituído por uma cópia
irrestrita ou por uma execução de firmware.

Três janelas de argumento foram seguidas:

| Referência ao helper | Origem reconstruída | Extensão | Limite |
|---|---|---|---|
| 0x1db2c | Nominal 0x0211b630, de ADRP+ADD de 0x31630 | W19, não reconstruído aqui | Começa depois da célula; o helper avança, não recua |
| 0x1db58 | Nominal 0x0211b668, de ADRP+ADD de 0x31668 | 32 bytes | Origem não contém a célula |
| 0x2e8b8 | Literal 0x021ab6a4 | 52 bytes | Origem não contém a célula |

Para o primeiro caso, não se supôs W19=4: o valor e o fluxo anterior não
foram fechados. O índice parte de zero; o helper testa o restante como
signed W e avança por bytes. Com a base reconstruída, esse caminho não
alcança um endereço menor como `0x0211b580`. Isso não prova conclusão
normal da cópia nem acesso válido a toda a origem.

Origem distinta exclui transportar **esses bytes da célula**, não exclui
sobrescrever a célula por um destino recebido. Os destinos dos três casos
não foram usados para provar ausência de escrita. As outras **44 referências**
ainda precisam de argumentos/aliases e condições; chamadas indiretas ao
helper ou outros mecanismos tampouco foram excluídos.

## Buscas adicionais e limites

- O B/BL para `0x2d364` foi ampliado até `0xec000`, com alinhamento de
  quatro bytes: nenhum candidato nesse intervalo maior.
- O endereço nominal da tabela, o da célula e o ponteiro `0x02117364`
  foram buscados como literais u32/u64 em todo o sboot. Só o último aparece,
  em `0x31580`; isso não é uma referência à própria célula.
- O scan restrito MOVZ X/MOVK X existente, em todo o arquivo, não encontrou
  esses três valores. Ele aceita apenas suas formas declaradas; não cobre
  ADRP, aritmética geral, bases recebidas ou todos os encodings.

Nada disso demonstra ausência de exportação ou chamador. O [resultado do
slot47](newtime-slot47-hzc2.md) continua parcial: a origem de X0 permanece
aberta e os quatro candidatos de outra base continuam separados.

## Reprodução e continuação

```bash
python3 scripts/inspect_newtime_transports_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_transports_hzc2.py) e
[JSON com parâmetros, projeções, inventário e GNU](references/newtime-transports-hzc2.json).
Conferidos **141 palavras, 56 alvos relativos e 11 operandos**; o relatório
é reproduzível byte a byte. Testes da projeção cobrem limites exclusivos,
célula parcial e overflow; os testes anteriores dos laços foram preservados.

Próximo: priorizar os argumentos das cópias parametrizadas e seus wrappers,
sem inferir a origem de X0 só da existência de uma tabela. Uma investigação
do binding deve distinguir transporte do valor, escrita na célula e uso
posterior como ponteiro de função. A ordem real e os efeitos do monitor,
o leitor de AP0x0207365c e os nomes físicos continuam abertos. Nenhuma
ampliação do escopo de execução foi feita.
