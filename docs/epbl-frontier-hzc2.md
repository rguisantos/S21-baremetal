# HZC2: fronteira do prefixo EPBL e dois produtores de VBAR

Auditoria de **2026-10-23 (Campo Grande)**, continuação da
[preparação EPBL e dispatcher comum](epbl-preparation-hzc2.md). Imagem
original: sboot de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets abaixo são no arquivo; valores nominais são identificados como tal.

**Resultado:** o inventário do prefixo tem 1182 instruções, duas escritas de
VBAR_EL3 e 13 arestas diretas para a região pendente. O segundo produtor de
VBAR corrobora o delta nominal anterior. O grafo não liga a entrada aos
handlers: ele para nos bytes pendentes e não modela a entrada por exceção.
Não houve transformação de firmware, MMIO ou execução no telefone.

## Raiz e regras do inventário

O veneer de entrada foi conferido: ADR X30 em `0x3020` aponta a `0x3028`,
B em `0x3024` alcança `0x3128`, cujo corpo é RET. Por isso o inventário
começa explicitamente na continuação **`0x3028`**.

O inspetor percorre `[0x3000,0x4540)`, com orçamento de 2048 PCs únicos.
Branches diretos para `[0x4700,0xfde0)` são registrados como fronteira e
não desassemblados como código verificado. Destinos em outra região ou
desalinhados provocam recusa. O intervalo entre os dois recortes não é
tratado automaticamente como código.

As duas alternativas de cada condicional são exploradas, sem executar
instruções ou provar viabilidade. O passo posterior a BL/BLR é incluído
**sob hipótese de retorno normal**; isso não demonstra que a chamada
retorne, altere corretamente a memória ou tenha sucesso. B/BR não têm
continuação automática; RET, ERET e chamadas de exceção encerram o ramo.
As instruções comuns de dados não recebem interpretação geral.

Só um salto indireto foi expandido: BR X9 em `0x3c30`, pela tabela de quatro
bytes com sinal em `0x4228`: `03 00 00 02`, base `0x3c34`, escala quatro.
O limite é o CMP W8,#3 do consumidor. Os destinos distintos são `0x3c34`,
`0x3c3c` e `0x3c40`. Isso não autoriza bindings arbitrários de ponteiros.

## As 13 saídas para a região pendente

| Origem | Transferência | Destino |
|---|---|---|
| `0x3070` | BL | `0xbaa8` |
| `0x3088` | BL | `0xb98c` |
| `0x30b4` | BL | `0xba1c` |
| `0x30bc` | BL | `0xbe04` |
| `0x30cc` | BL | `0xb7f8` |
| `0x30d4` | BL | `0xba68` |
| `0x30f8` | BL | `0x47dc` |
| `0x30fc` | BL | `0x4838` |
| `0x3100` | BL | `0x9964` |
| `0x3104` | B | `0xb964` |
| `0x3a40` | BL | `0x8100` |
| `0x3a74` | BL | `0x8100` |
| `0x4350` | BL | `0xc9ec` |

São arestas do recorte estático, não 13 chamadas executadas numa sequência
medida. Ramos incompatíveis podem estar presentes ao mesmo tempo. O salto
BR X0 em `0x3060` permanece sem expansão no grafo conservador. O helper
anterior `0x431c` contém MOV X0,XZR/RET; sob código inalterado, retorno normal
e sem efeitos externos, ele explica por que o ramo BR pode ser inviável.
O inventário não elimina automaticamente esse ramo por propagação de valores.

Nenhum nó do dispatcher em `0x43d8/0x4424/0x4494` é alcançado por esse
percurso direto. **Isso não prova que o dispatcher seja inalcançável no
runtime:** a entrada por exceção e o código de preparação pendente não
fazem parte do grafo. Interpretar a ausência desses nós como prova de que
os SMC não funcionam seria incorreto.

## Segunda escrita de VBAR: corroboração independente

| Caminho observado | Produtor | Escrita |
|---|---|---|
| Relativo ao PC | ADR em `0x3064` prepara o candidato `0xe800` | MSR VBAR_EL3 em `0x3068` |
| Ponteiro literal | LDR em `0x4354` lê `0x02032800` da célula `0x43c0` | MSR VBAR_EL3 em `0x4358` |

A diferença **`0x02032800 - 0xe800 = 0x02024000`** coincide com a hipótese
nominal obtida antes pela versão e registros EBRS/EBHS. Essa nova relação
é coerente com os dois caminhos apontando ao mesmo vetor nominal; não é
medição do carregamento ou prova de propriedade da região.

O segundo caminho começa em `0x4344`, contém teste com laço e chama
`0xc9ec` **antes** do LDR/MSR. Essa chamada está na fronteira pendente.
Portanto, a escrita não demonstra um caminho completo executável apenas
com o prefixo conferido.

O candidato de vetores AArch64 `[0xe800,0xf000)` — 16 slots de 128 bytes —
fica inteiro na região pendente. Seus bytes e hash são conservados, sem
ligar um slot a uma entrada SMC por uma tabela fictícia. A classificação
inicial em zero e a janela conservadora de endereços dos slots do dispatcher
continuam sem comprovação runtime. Essa janela não é prova de que existam
128 descritores válidos alocados.

## Referência SSS pública: o que ela permite comparar

Foi lido o arquivo
[s5p-sss.c no commit 37c14d8](https://github.com/Exynos-2100/android_kernel_samsung_universal2100/blob/37c14d86996a49edbea8953f2523b202546b8958/drivers/crypto/s5p-sss.c)
do repositório indicado pelo usuário. O blob Git
`86a13b738c2deb168edf749b3268e57131bca22e` foi recalculado a partir dos bytes.
É fonte primária do driver consultado, **não especificação correspondente
demonstrada para o MMIO EPBL HZC2**.

| Variante no arquivo | Offset AES | Offset HASH |
|---|---|---|
| s5pv210 | `0x4000` | `0x6000` |
| exynos4210 | `0x200` | `0x400` |
| exynos5433 slim | `0x400` | `0x800` |

Os compatibles listados são dessas três famílias. As definições de engine
HASH consultadas nomeiam SHA1, MD5 e SHA256. O prefixo EPBL constrói grupos
de acessos em +0x400 e +0x1000; a presença de constantes parecidas não basta
para importar toda a configuração, as unidades ou a semântica de saída.
Isso tampouco prova ausência de outros algoritmos no Exynos 2100.

Essa referência ajuda a comparar convenções e a evitar um decoder baseado
na variante errada. Não demonstrou binding no DTB, chave, algoritmo do
pedido EPBL ou plaintext verificado. O fato de o arquivo estar numa árvore
Exynos 2100 não torna cada variante nele o driver do bloco em uso.

## Reprodução e validação

```sh
python3 scripts/inspect_epbl_frontier.py /caminho/sboot.bin
(cd scripts && python3 -m unittest test_epbl_frontier test_epbl_preparation -v)
```

Leitura limitada, tamanho/hash exatos e zero execução do firmware. O índice
ordenado PC/palavra tem SHA-256
`a87c2dac6b1e0c193a90d4a7f2154a52e8410a044bf5f97efeeb64d92ee4e9bd`.
Os intervalos do índice e todas as arestas pendentes constam no relatório.

**18 testes novos + 18 regressões = 36 PASS.** Incluem ciclos, PC budget,
fronteiras B/BL, condicionais, indiretos, bindings inválidos, lacunas de
intervalo, ADR com sinal, RET X29 e encerramento em exceção. São testes do
inventário; não de retorno, caches ou progresso do hardware.

GNU objdump 2.44 coincidiu nas **1182 palavras e 138 destinos relativos**,
com o mesmo hash PC/palavra. Nenhuma palavra visitada foi apresentada como
UDF/indefinida. Isso valida a desmontagem do recorte, sem validar como código
os destinos pendentes, a tabela de handlers ou os vetores.

- [Grafo, fronteiras e produtores de VBAR](references/epbl-frontier-hzc2.json)
- [Conferência GNU do índice completo](references/epbl-frontier-validation.json)
- [Referência SSS fixada e variantes](references/epbl-sss-reference.json)
- [Saída dos 36 testes](references/epbl-frontier-host-tests.txt)

A próxima evidência útil é a preparação/transformação correspondente e a
ligação dos vetores, obtidas de implementação verificável ou observação
autorizada. Repetir o mesmo grafo ou inventar respostas MMIO não fecharia
essas fronteiras. O [roadmap físico](roadmap.md) mantém carregamento,
posse/coerência e recuperação do diagnóstico como requisitos separados.
Nenhum arquivo adicional foi necessário para esta entrega e nenhum ensaio
QEMU/S21 foi repetido.
