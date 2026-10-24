# BL2 HZC2: reescrita condicional das bases da consulta

Análise de **2026-10-24 (Campo Grande)**. Mesmo sboot de 4194304 bytes,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Continua a [consulta de geometria](bl2-geometry-query-hzc2.md): sua tabela
`0x30f98` tem um escritor positivo identificado. As cinco bases literais
do arquivo **não são uma configuração runtime comprovada**.

## Condição e escritas

O corpo `0x2d270` carrega um callback da célula `0x31458`, cujo ponteiro
bruto `0x021183d0` corresponde nominalmente a `0x2e3d0`, com o delta
`0x020ea000`. O getter tem cinco instruções: constrói `0x10000010`, lê
32 bits, extrai os bits **20–23** e retorna. O endereço/campo vêm do código;
não se atribuiu nome de registrador, identidade de silício ou valor real
ao nibble.

`CMP W0,1` / `B.NE 0x2d2c4` seleciona o trecho de 15 instruções em
`0x2d288–0x2d2c4`. Ele reconstrói valores com ADRP, MOVZ/MOVK e ADD,
incluindo ADD com `LSL #12`, e escreve **cinco u64**:

| Célula relativa | Valor inicial no arquivo | Valor escrito se o callback retornar 1 | Store |
|---|---|---|---|
| `0x30f98` | `0x1c036000` | `0x1c03f000` | `0x2d298` |
| `0x30fa0` | `0x1c136000` | `0x1c13f000` | `0x2d2a4` |
| `0x30fa8` | `0x1c236000` | `0x1c23f000` | `0x2d2ac` |
| `0x30fb0` | `0x1c336000` | `0x1c33f000` | `0x2d2b4` |
| `0x30fb8` | `0x1a346000` | `0x1a34f000` | `0x2d2c0` |

Se o retorno for diferente de 1, **não há escrita nessa tabela pelo corpo**.
O conteúdo anterior é preservado; o ramo não restaura as bases do arquivo.
Se a rotina já tiver reescrito a tabela e depois rodar com outro nibble,
essas escritas não serão desfeitas por esse caminho. Outros escritores e
aliases não foram excluídos.

O trecho escreve a tabela de **bases de acesso**, sem alterar por esse
corpo os ponteiros de código em `0x30e50`/`0x30fe8` ou a tabela de bases de
preparação em `0x30fc0`. Isso não prova imutabilidade dessas outras tabelas.

## Ligação selecionada com a inicialização

`0x1e0dc` adiciona `0x408` a X20 e o load seguinte usa `+32`; a página
produzida em `0x1dee4` é `0x31000`. Sob a preservação de X20 pelas chamadas
intermediárias, a célula é `0x31428`. Seu ponteiro `0x02118ff0` corresponde
nominalmente a `0x2eff0`, que chama diretamente `0x2d270` em `0x2effc`.

O call indireto em `0x1e0e4` aparece antes da etapa de geometria em
`0x1e85c` no caminho selecionado. A ligação depende da tabela e da
preservação do registrador; não comprova alcançabilidade, execução física
ou ausência de alterações entre as etapas. A tradução nominal e o nibble
continuam sem observação.

Com a tabela reescrita, a consulta do slot 0 acessaria comando/disparo/
resposta em `0x1c03f000`, `0x1c03f004`, `0x1c03f00c`, em vez de
`0x1c036000`, `0x1c036004`, `0x1c03600c`. No slot 4, a leitura inicial
continuaria usando a entrada zero, agora reescrita, e os demais acessos
usariam `0x1a34f000/+4/+0xc`. São consequências condicionais das instruções,
sem solicitação de leitura desses endereços pelo Android.

## Reprodução e escopo das ferramentas

```bash
python3 scripts/inspect_bl2_query_base_rewrite.py /caminho/sboot.bin
python3 scripts/inspect_bl2_query_base_rewrite.py /caminho/sboot.bin --register-word 0x100000 --slot 0 --term 2 --selector 8
python3 scripts/check_bl2_query_base_rewrite_gnu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
```

O exemplo fornece uma palavra **sintética**, não medida. Sem argumento, o
inspetor emite somente a condição, os valores iniciais e as escritas
possíveis. Com `--register-word`, aplica apenas esse escritor, assumindo
explicitamente a tabela inicial do arquivo como estado anterior. O plano
opcional conserva o controle e a resposta como desconhecidos. Os quatro
argumentos são exigidos juntos quando há plano; a palavra é u32.

O intérprete de host aceita somente as formas declaradas no trecho de até
16 instruções, recusa registradores desconhecidos, memória lida, branches,
calls, pilha, stores W ou fora das cinco células e escritas repetidas/
incompletas. Não executa o callback, o getter ou os stores do firmware.
O inspetor anterior agora identifica suas bases/plano como **valores
iniciais do arquivo, sem aplicar a reescrita condicional**.

**58 testes BL2 passaram**: dez novos controles e 48 regressões. Incluem
os 16 nibbles, persistência após uma reescrita seguida de skip, limites de
largura, instruções não suportadas e limites do construtor. A CLI passou
três planos condicionais e quatro recusas sem JSON parcial.

GNU objdump **2.44** conferiu **39 palavras, dois destinos relativos,
sete operandos, cinco stores reconstruídos e sete ponteiros**. A segunda
reconstrução interpreta texto ADRP/MOV/MOVK/ADD/STR do GNU; não reutiliza o
decodificador binário do construtor. Evidências
[estática](references/bl2-query-base-rewrite-hzc2.json) e
[GNU](references/bl2-query-base-rewrite-gnu-hzc2.json).

Nenhum novo QEMU, MMIO, serviço ou ensaio físico; nenhum blob adicionado.
A [continuação do estado anterior](bl2-geometry-record-hzc2.md) identificou
duas recargas da primeira palavra a partir de `0x02073600`, sem recuperar
seu valor. A próxima investigação segue os produtores dessa palavra e os
escritores/configuração restantes, sem fixar uma das bases como ativa.
Bindings, nibble, respostas reais, limite LK e mapa FDT final permanecem
pendentes. Essa reescrita não estabelece capacidade ou RAM livre.
