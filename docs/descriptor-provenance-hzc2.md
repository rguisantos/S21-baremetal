# HZC2: busca do estado anterior do descritor BL2

Auditoria estática de **2026-10-23 (Campo Grande)**, continuação da
[origem do modo e descritor -0xe6](bl2-service-chain-hzc2.md). sboot original:
4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets de código são no arquivo; intervalos de origem/destino abaixo são
valores nominais reconstruídos dos literais, sem execução física.

**Resultado:** as sete cópias fixas examinadas no BL2 não alcançam a janela
do descritor `[0xe7ffe000,0xe7ffe01c)`. A cópia do construtor tem os mesmos
campos desconhecidos. As referências adicionais do LK usam outro endereço,
`0xe7fffe00`, em comparações de limite. **O inicializador dos campos herdados
não foi identificado; nenhum valor anterior foi preenchido por hipótese.**

## Sete cópias: intervalos conferidos, inicialização não demonstrada

Cada helper começa com três LDR X literais para origem, fim da origem e
destino. Seguem leitura/escrita com pós-incremento, CMP, B.LT, DSB SY, ISB
e RET. Dois usam passos de quatro bytes; os demais, pares de 16 bytes.
O inspetor só aceita esses corpos exatos e extensão positiva divisível pelo
passo; não transforma o laço do/while em uma cópia vazia se início=fim.

| Helper | Origem, fim exclusivo | Destino, fim exclusivo | Bytes / passo |
|---|---|---|---|
| `0x161b0` | `0x02120000–0x02122000` | `0x02036000–0x02038000` | `0x2000` / 16 |
| `0x161d8` | `0x0203d000–0x0207a000` | `0x02175000–0x021b2000` | `0x3d000` / 4 |
| `0x16200` | `0x02175000–0x021b2000` | `0x90014000–0x90051000` | `0x3d000` / 4 |
| `0x16228` | `0x02122000–0x02127000` | `0x0203d000–0x02042000` | `0x5000` / 16 |
| `0x16250` | `0x02127000–0x02151000` | `0x02048800–0x02072800` | `0x2a000` / 16 |
| `0x16278` | `0x02153000–0x02167000` | `0x90000000–0x90014000` | `0x14000` / 16 |
| `0x162b4` | `0x02167000–0x02175000` | `0x15b00000–0x15b0e000` | `0xe000` / 16 |

Nenhum destino intersecta os 28 bytes observados do descritor. Isso exclui
**esses corpos, com esses literais**, como inicializadores daquela janela.
Não prova a execução dos helpers, as condições dos caminhos que os chamam,
o conteúdo das origens ou ausência de stores por outros caminhos, aliases,
serviços seguros e estágios anteriores. DSB/ISB no corpo não demonstram a
coerência da futura Image do diagnóstico.

## A duplicata não fecha os campos que faltam

Os 140 bytes de `0x1643c–0x164c8` e `0x36154–0x361e0` são idênticos,
incluindo os deslocamentos relativos dos branches. O intérprete restrito
anterior foi aplicado a ambos, parando antes de seus veneers SMC distintos.
Para os quatro modos selecionáveis, argumentos e campos conferem:

| Modo | Campos sem escrita nos dois construtores |
|---|---|
| 0 | Nenhum dentro da janela de 28 bytes |
| `0x14` | +0x18 |
| `0x20` | Nenhum dentro da janela de 28 bytes |
| `0x40` | +0x10, +0x14, +0x18 |

O censo de palavras B/BL alinhadas em `[0x16000,0xec000)` encontra a chamada
`0x1cb54` para o primeiro construtor e nenhuma para o segundo. Isso **não**
prova que a duplicata seja inalcançável: referências indiretas, relocação e
outros pontos de entrada não estão cobertos por esse censo. Também não se
conclui que um campo sem escrita seja erro ou que o provedor o consuma.

## O endereço do LK é parecido, mas diferente

Uma busca limitada de sequências MOVZ X/MOVK X encontrou oito candidatos
nos bytes alinhados da imagem de 4 MiB:

- quatro constroem `0xe7ffe000`: dois em cada construtor BL2;
- quatro constroem **`0xe7fffe00`** no LK, em
  `0x12e220/0x12e224`, `0x12e2a0/0x12e2a4`,
  `0x12e6d8/0x12e6dc` e `0x12e93c/0x12e940`.

O segundo endereço está **0x1e00 bytes acima** do início do descritor.
Nos blocos LK conferidos, ele alimenta SUB/CMP e branches condicionais
dos percursos de carregamento; não há store ao descritor nesses blocos.
Não deve ser apresentado como outra referência ao mesmo campo ou como
garantia de que a região esteja reservada/livre.

O scan aceita MOVZ X com halfword baixo seguido de MOVK X no halfword 16,
separados por até duas instruções conhecidas que não sobrescrevam a base.
Recusa instruções intermediárias desconhecidas, chamadas e base alterada.
É um conjunto de testemunhos sintáticos, sem prova geral de fluxo ou
alcançabilidade. Os dois endereços tampouco aparecem como literais contíguos
little-endian de quatro/oito bytes no arquivo. Essa ausência não exclui
construção aritmética, outro encoding ou ponteiro recebido de fora.

## Reprodução e testes

```sh
python3 scripts/inspect_descriptor_provenance.py /caminho/sboot.bin
(cd scripts && python3 -m unittest test_descriptor_provenance test_bl2_service_chain -v)
```

A leitura é limitada e aceita somente tamanho/hash originais. Não extrai
chaves, modifica firmware, executa cópias/MMIO/SMC ou fornece resposta segura.
As comparações entre construtores reutilizam o modelo restrito anterior;
não constituem uma emulação completa do BL2.

**16 testes novos + 24 regressões = 40 PASS**. Os casos cobrem deslocamentos
LDR negativos, largura/registrador/alinhamento, laços vazios/parciais e
limites com sinal não suportados, corpo/barreiras alterados, interseção de
intervalos semiabertos, base sobrescrita e limites do scan. Um caso sintético
faz a cópia intersectar o descritor para conferir que a ferramenta detecta
isso sem marcar execução ou inicialização como observadas.

GNU aarch64 objdump 2.44 coincidiu nas **165 palavras de instrução e 23
destinos relativos** dos blocos selecionados, mais os **21 endereços de
literais** dos sete helpers. Essa conferência valida palavras/destinos;
não é uma segunda execução da cadeia Samsung ou de sua coerência física.

- [Intervalos, duplicatas, candidatos e hashes](references/descriptor-provenance-hzc2.json)
- [Conferência GNU por instrução e literal](references/descriptor-provenance-validation.json)
- [Saída dos 40 testes de host](references/descriptor-provenance-host-tests.txt)

## Estado após a investigação

A busca retirou hipóteses específicas: as cópias fixas examinadas e o
limite parecido do LK não explicam os campos herdados. `initializer_identified`,
`prior_field_values_known` e `complete_writer_census` permanecem falsos no
relatório. Repetir respostas simuladas não resolveria essa origem.

O próximo limite é a preparação anterior/externa à janela analisada e a
transformação/despacho seguro onde existam bytes verificáveis. Em paralelo,
o [primeiro diagnóstico físico](roadmap.md) continua dependendo de posse e
coerência da imagem, carregamento Samsung e leitura do registro. Nenhum
arquivo extra foi necessário nesta etapa; não houve novo ensaio QEMU/S21.
