# HZC2: auditoria do slot 47 e origem de X0 ainda aberta

Análise **estática, 2026-10-25 (Campo Grande)**, base `a60cd37` / PR #29.
**O despacho da célula 0x31580 e a origem de X0 não foram resolvidos.**
Esta rodada descarta quatro candidatos imediatos de outra tabela e delimita
os efeitos do argumento zero. Não houve execução QEMU, SMC ou no aparelho.

## Mesmo índice, tabelas diferentes

O índice 47 corresponde ao deslocamento decimal 376 (`0x178`) para
entradas de oito bytes. O deslocamento sozinho não identifica a célula:

| Base | Índice | Célula | Ponteiro inicial | Alvo nominal, delta 0x020ea000 |
|---|---:|---|---|---|
| 0x30fe8 | 47 | 0x31160 | 0x02116300 | 0x2c300 |
| 0x31408 | 47 | 0x31580 | 0x02117364 | 0x2d364 |

Os quatro LDR X com imediato 376 encontrados usam a primeira base nos
caminhos selecionados, não a segunda:

| Carga | BLR | Base construída/retida | X0 antes da chamada |
|---|---|---|---:|
| 0x24784 | 0x2478c | X0=0x30000+0xfe8 | 4 |
| 0x24adc | 0x24ae8 | X20+0xfe8, com X20=0x30000 antes do ADD | 4 |
| 0x24ba0 | 0x24ba8 | X0=0x30000+0xfe8 | 4 |
| 0x2501c | 0x25020 | X20+0xfe8, com X20=0x30000 antes do ADD | 4 |

Âncoras: ADRP `0x24760` e ADD `0x24780/0x24ab0`; ADRP `0x24b7c` e
ADD `0x24b9c/0x24fe8`. Há chamadas e caminhos intermediários; retenção de
X20 conforme ABI, células e ponteiros continua sendo condição da ligação.
O JSON inclui os contextos selecionados, não uma prova de fluxo completo
ou de execução. X0=4 nesses locais **não é origem demonstrada** do argumento
publicado por `0x2d394`: o alvo nominal dessas células é `0x2c300`.

## O que a busca cobre

Sboot HZC2 de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets abaixo são de arquivo, não valores observados no telefone.

O [extrator](../scripts/inspect_newtime_slot47_hzc2.py) percorre **26432
palavras alinhadas** em `[0x16000,0x2fd00)` e decodifica somente:

- LDR de 64 bits, imediato unsigned escalado por oito.
- LDP de 64 bits, imediato signed, sem writeback; testa ambos os elementos,
  inclusive o segundo elemento de um par em deslocamento 368.

Para o deslocamento 376, o inventário contém somente os quatro LDR acima
e nenhum LDP. GNU reconfere as instruções dos candidatos e os contextos
selecionados: **84 palavras, três alvos relativos e 22 operandos**.
O [JSON](references/newtime-slot47-hzc2.json) registra toda a evidência.

Também foram procuradas codificações alinhadas B/BL para cada instrução
em `[0x2d364,0x2d3bc)`, no mesmo intervalo BL2. Não houve candidato,
inclusive para entradas internas. Isso amplia a busca anterior que só
considerava a entrada. O ponteiro nominal u64 aparece em `0x31580`.

**Não é uma exclusão geral de chamador.** Cargas por índice em registrador,
por literal, com pre/post-indexação, cópias, aliases, funções recebidas de
outro contexto ou código em outra imagem não estão excluídos. Os formatos
não aceitos não são contados como ausentes: ficam fora da cobertura.
A exploração temporária de candidatos em outros trechos não foi promovida
a um inventário reprodutível nem usada para afirmar ausência de chamadas.

## Semântica do argumento no escritor verdadeiro

No corpo `0x2d364`, X0 não é reescrito antes de `0x2d390`:

| Entrada X0 | Efeito selecionado sobre 0x31998 |
|---|---|
| Zero | CBZ para 0x2d398, pula somente o STR do binding; conserva o valor anterior nessa célula |
| Não zero | `0x2d394` publica X0 em S+784, S=0x31688 |

Isso descreve o store selecionado. Não prova preservação da célula depois
das chamadas seguintes ou exclusão de outros escritores/aliases.
Além disso, antes do teste, `0x2d378` já lê u64 de AP`0x02073600`,
`0x2d37c` publica em `0x31978` e `0x2d388` grava o nibble em `0x31939`.
Após `0x2d398`, a função continua por callbacks. **X0 zero não transforma
a função toda em no-op** nem fornece valor ou permissão para essa leitura.

O [caminho concreto do inicializador anterior](newtime-smc-binding-hzc2.md)
continua válido sob suas condições: X3 fornecido na chamada `0x18000`, store por
`0x1dcbc`, tabela `0x307e0` e método +72 nominalmente SMC. Não é possível
usar os quatro candidatos descartados para afirmar que esse binding foi
substituído por 4, preservado no boot ou modificado numa ordem específica.

A [continuação sobre transportes](newtime-transports-hzc2.md) afasta
sete cópias fixas sob o mapeamento nominal e delimita a frente de cópias
parametrizadas. O transporte da célula e X0 seguem sem solução.

## Reprodução, validação e próxima frente

```bash
python3 scripts/inspect_newtime_slot47_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

O extrator exige o hash exato. A validação inclui reprodução byte a byte,
recusas por arquivo curto/longo/alterado e testes do decoder para largura,
escala, sinal, segundo elemento do par e writeback excluído. Os testes
não executam firmware.

Próximo: seguir exportações/cópias e bases recebidas que possam transportar
a célula `0x31580`, antes de atribuir um índice dinâmico ou valor a X0.
Binding/método, leitor de AP`0x0207365c`, semântica física e ordem real
continuam abertos. O resultado desta rodada é **parcial**, não fechamento
da origem de X0 ou autorização de execução fora do callback NEWTIME.

Continuação: a [revisão dos argumentos de cópia](newtime-copy-arguments-hzc2.md)
cobre as 47 referências diretas e seus wrappers, sem transporte comprovado.
O buffer opcional de 64 bytes leva a outra tabela: slot 20 de `0x30fe8`,
não slot 47 de `0x31408`. Ponteiros de canal e metadados são a frente seguinte.

A [continuação do slot 20](newtime-slot20-hzc2.md) resolve X5 em nove
chamadas selecionadas e acrescenta buscas de endereços diretos da célula.
Nenhum novo despacho do slot 47 foi estabelecido; os limites das formas
de carga, pares adjacentes e região BL2 continuam explícitos.

A [enumeração de dois switches](newtime-jump-tables-hzc2.md) acrescenta
conjuntos finitos para os BRs `0x1ada4` e `0x2f928`: 20/5 entradas nos
arrays `0x30108`/`0x30130`, com 12/4 destinos distintos. Os anchors de código
`0x1ada8`/`0x2f92c` são distintos dos arrays. Nenhuma entrada aponta à
rotina do slot 47; chamadas e continuações posteriores permanecem abertas.
