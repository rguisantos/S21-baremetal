# HZC2: registro NEWTIME, ramos e escritas posteriores

Continuação de **2026-10-24 (Campo Grande)** da
[seleção NEWTIME](newtime-ect-hzc2.md). Mesmo sboot de 4194304 bytes,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets de código são de arquivo; offsets de registro são relativos ao
ponteiro ativo da célula **0x30520**, chamado **R** nesta página.

**O restante do callback monta um registro limitado a R+0x2400.** Nas
condições de base estável e regiões disjuntas, suas escritas posteriores
preservam o primeiro u64, inclusive ao retornar erro 4 por chave ausente.
Erro 4 deixa dados já gravados no destino; o wrapper encaminha esse código
a outro helper. Não foi observada a execução física ou o conteúdo do registro.

## Layout e publicação do tamanho

| Offset relativo a R | Conteúdo selecionado |
|---|---|
| +0, oito bytes | Argumento original escrito em 0x19694 |
| +8, quatro bytes | Versão ECT, lida por ponteiro de estado 0x31c18; no fixture: 007n |
| +12, quatro bytes | Versão do handle NEWTIME; no bloco embutido: 0.81 |
| +16, quatro bytes | Cursor final menos ponteiro ativo 0x30520, truncado em W; escrito somente no caminho de sucesso |
| +32, oito bytes | Ponteiro absoluto R+0x1a0 para o diretório |
| [+0x1a0, +0x2a0) | 16 descritores de 16 bytes: chave baixa32, offset do payload, colunas e linhas |
| [+0x2a0, +0x2400) | Dados copiados das tabelas escolhidas; capacidade 0x2160 |

As lacunas reservadas não são zeradas pelo trecho estudado. O modelo e o
QEMU conferem que preservam o preenchimento anterior do fixture.
Para a forma embutida, **n=17−1=16** tabelas. O trecho 0x19738–0x19764
produz em W a capacidade equivalente a **0x2260−16n = 0x2160**. O início
dos dados é R+0x1a0+16n = R+0x2a0; o fim fica em **R+0x2400**.

O helper **0x18054** instala cursor/limite em estado **0x31a50/0x31a58**.
O alocador **0x18068** retorna o cursor anterior e calcula o próximo como:

```text
novo_cursor = ((cursor + 3 + SXTW(pedido_W)) mod 2^64) & ~3
```

Ele grava o cursor **antes** da comparação unsigned com o limite.
Se exceder, entra em **B 0x18090 → 0x18090**, sem retornar NULL ou desfazer
escritas. O arredondamento não alinha o ponteiro anterior retornado. As
tabelas reais analisadas têm pedidos pequenos e positivos; essa folha não
foi tratada como um validador geral de intervalos.

## Gate reamostrado e chaves ausentes

Cada iteração lê **AP 0x158609bc[31]** em **0x19774**. Seu valor e sua
estabilidade não foram observados. Para índices **0 a 8**, um bit ativo
transforma a chave: se o nibble baixo é 8, soma 3; caso contrário, subtrai
3, com aritmética u64. Nos índices 9 a 15, essa transformação é ignorada.

Há **512 sequências efetivas** dos nove ramos relevantes. A enumeração
das **22 linhas × 512 = 11264** combinações do bloco embutido produziu:

| Resultado do modelo condicional | Combinações |
|---|---:|
| As 16 consultas encontram tabela e a construção termina | 8512 |
| Uma consulta encontra chave ausente e prepara código 4 | 2752 |
| Exaustão do alocador nesses dados | 0 |

Essas contagens são combinações de ramos, **não probabilidades ou amostras
do aparelho**. Entre os caminhos completos, o campo de bytes usados varia
de **0x1da0 a 0x22dc**, com no mínimo **292 bytes** até o limite 0x2400.

Foram encontradas nove chaves ausentes em caminhos selecionados:
0x3128, 0x312b, 0x3148, 0x3248, 0x4248, 0x4348, 0x5148, 0x5248 e 0x5348.
A linha de índice 3 não completa nenhuma das 512 combinações nesse bloco.
Isso não demonstra que ela seja selecionada no telefone, nem determina
quais ramos ou dados estão ativos. Contagens por linha e testemunhos de
cada ausência estão no [relatório estático](references/newtime-record-hzc2.json).

## Erro parcial, preservação e wrapper

**0x19840** prepara W0=4 e segue ao epílogo. Nesse ponto, o argumento
original, versões, ponteiro do diretório e os descritores/payloads anteriores
já podem ter sido gravados. O campo final +16 ainda não foi publicado.
Não há rollback nesse caminho do callback.

Os campos diretos posteriores começam em +8; diretório e payloads ficam
nas regiões acima. Assim, o primeiro u64 permanece sob as hipóteses de
ponteiro estável, ausência de wrap e não sobreposição com fonte, tabelas,
estado e pilha. Isso não prova exclusividade ou preservação física.

O wrapper **0x2f6c0** interpreta o retorno do callback:

| W0 do callback | Ação selecionada do wrapper |
|---:|---|
| 1, 3 ou 4 | Tail branch a 0x1fdb8 com W0=27 |
| 2 | Tail branch a 0x1fdb8 com W0=5 |
| Outros | Retorna (W0−3) mod 2^32; para zero, retorna 0xfffffffd |

A [continuação do helper **0x1fdb8**](newtime-error-hzc2.md) delimita flags,
dump e console nominal. Essas chamadas não executam neste ensaio.
Portanto a preservação conferida no retorno direto do callback não se
estende automaticamente ao tratamento feito pelo wrapper.

## Execução condicional de blocos originais no QEMU

O novo runner usa duas colocações RAM, deltas **0x40000000/0x40200000**.
O formato dos metadados já foi conferido com o parser original na etapa
anterior; neste ensaio, o host materializa esses metadados. Fonte ECT,
ponteiros, pilha, destino e entrada são bindings de laboratório.

O prefixo original executa até a primeira escrita. Depois o harness para
em **0x19770**, antes da carga do endereço e do LDR MMIO, e escolhe PC
**0x19788** ou **0x19810** conforme o ramo explícito do caso. Nenhuma
leitura do gate ou resposta de registrador é executada/injetada. A seguir
executam os blocos originais de transformação, lookup, alocação, cópia,
publicação do tamanho e epílogo. **O fluxo do gate é fornecido pelo harness.**

São 96 combinações representativas por colocação, cobrindo as 22 linhas,
quatro padrões de ramos e cada chave ausente, mais duas entradas bit63/low32
0xcafe. Total: **196 casos**, **142 retornos zero e 54 retornos 4**.
O registro inteiro de **0x2400 bytes** foi comparado byte a byte; argumento,
guardas, pilha e registradores preservados pelo ABI foram conferidos.
Código, fonte ECT e metadados permaneceram intactos.

Outros **seis casos** executaram somente a folha original do alocador:
encaixe exato, exaustão com cursor atualizado e arredondamento, em duas
colocações. Na exaustão, o debugger para em 0x18090; não há retorno observado.
[Resultado QEMU](references/newtime-record-qemu-hzc2.json).

## Reprodução e próximo passo

```bash
python3 scripts/inspect_newtime_record_hzc2.py /caminho/sboot.bin
python3 scripts/check_newtime_record_gnu.py /caminho/sboot.bin
python3 scripts/emulate_newtime_record_qemu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py' -v
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
```

[GNU 2.44](references/newtime-record-gnu-hzc2.json): **270 novas palavras,
24 alvos e 37 operandos**, mais as 353 palavras/50 alvos/24 operandos do
prefixo, total **623 palavras**. Relatórios estático/GNU reproduzidos byte
a byte. **12 testes novos e 80 existentes passaram**. Nove recusas CLI de
imagem curta/longa/alterada, exit 2 sem JSON parcial e antes de QEMU;
[validação](references/newtime-record-validation-hzc2.json).

A continuação delimita os efeitos selecionados de 0x1fdb8. Próximo: seguir
a origem da geometria que substitui o marcador e corroborar aliases/bindings,
com efeitos transitivos do tratamento de erro ainda abertos. Não foram
medidos gate, registro físico, RAM ou FDT final; o destino AP 0x02073600
continua dependente da cadeia ACPM e de preservação fora deste escopo.
