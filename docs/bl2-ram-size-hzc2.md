# BL2 HZC2: produtor do tamanho de RAM

Análise de **2026-10-24 (Campo Grande)** do sboot recebido: 4194304 bytes,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
O BL2 tem uma escrita de 64 bits em **`0x02038848`**, endereço já ligado aos
leitores LK e Harx. Uma folha candidata calcula bytes a partir de quatro
palavras de geometria. Suas **44 instruções originais** coincidiram com o
modelo em **66 execuções QEMU**, com entradas sintéticas.

Isso avança a origem do total, sem recuperar a geometria do aparelho ou seu
FDT final. O getter/cache/limite do LK já estavam documentados em
[ajustes dinâmicos](lk-dynamic-fdt.md); a novidade é o produtor anterior.
Complementa o [construtor de bancos](lk-memory-bank-constructor.md) e os
[leitores Harx/uH](el2-earlymem-hzc2.md).

## Caminho selecionado até a escrita

Todos os offsets abaixo são de arquivo. O destino literal `0x02038848`
é um endereço construído pelo firmware, sem leitura física nesta análise.

| Etapa | Instruções / resultado estático |
|---|---|
| Entrada BL2 | `0x160bc` e `0x16128` chamam o inicializador `0x17e14` em caminhos distintos |
| Retorno da inicialização | `0x18000` chama `0x1dc90`; `0x18004/8` constroem `0x02038848` em X1 |
| Publicação | `0x1800c: STR X0,[X1]`, 64 bits, se a chamada retornar |
| Cálculo intermediário | `0x1e85c` chama `0x1d830`; `0x1e860` grava X0 no estado relativo `0x31688+0x2b8 = 0x31940` |
| Retorno posterior | Após outras operações, inclusive `BL 0x20724`, `0x1f9cc` lê a mesma célula em X0; `0x1f9e4` retorna |

Há inicialização de hardware, callbacks e polling no caminho maior. Não
foram executados. A ligação entre as duas referências à célula é um caminho
de dados selecionado: não exclui escritores indiretos ou alterações durante
as chamadas intermediárias. Tampouco demonstra que o telefone alcançou a
escrita. A busca é evidência positiva deste produtor, sem censo completo de
todos os escritores de `0x02038848`.

## Callbacks e tradução nominal

O helper `0x1d830` chama dois ponteiros da tabela, testa W0 após o segundo
e termina em `BR X0` com um terceiro ponteiro. Se W0 for zero, chama antes
`0x1fdb8(3)`; não se presumiu que esse helper de falha retorna.

| Célula no arquivo | Ponteiro bruto | Alvo com delta nominal `0x020ea000` |
|---|---|---|
| `0x31500` | `0x02119130` | `0x2f130`: preparação/empacotamento candidato |
| `0x31558` | `0x02119a98` | `0x2fa98`: callback cujo retorno passa pelo teste W0 |
| `0x31358` | `0x02116aec` | `0x2caec`: folha de cálculo |

A tradução subtrai o delta do ponteiro. Os alvos são coerentes com os papéis
observados, mas a colocação física, a integridade da tabela e sua resolução
em execução não foram medidas. O ensaio QEMU seleciona a folha pelos bytes
do arquivo identificado; não resolve esses callbacks nem comprova essa
tradução no S21.

## Aritmética da folha `0x2caec–0x2cb9c`

O trecho usa endereçamento relativo à página, lê quatro u64 em
`0x31978`, `0x31980`, `0x31988`, `0x31990` e sete u16 little-endian em
`0x30080`. A tabela contém **256, 384, 512, 768, 1024, 1536, 2048**, em
unidades de MiB conforme o shift final de 20 bits.

| Campo de cada palavra | Efeito observado |
|---|---|
| Bits 4–7 da **palavra zero** | Valor 3 seleciona dois termos para todas as quatro palavras; qualquer outro seleciona um |
| Bits 8–15 | Zero zera a contribuição inteira daquela palavra |
| Bits 28–31 / 24–27 | Índice de densidade / seletor de duplicação do primeiro termo |
| Bits 20–23 / 16–19 | Índice / seletor do segundo termo, quando habilitado pelo modo global |
| Índice 0–6 | Seleciona a entrada u16; índices 7–15 contribuem zero |
| Seletor igual a 1 | Duplica a entrada; os demais valores não duplicam |

A folha soma as contribuições e retorna `soma << 20` em X0. Não usa pilha,
não escreve memória e não contém chamadas ou acessos MMIO. O máximo desta
aritmética é 32 GiB; isso é limite da combinação dos campos e da tabela,
sem inferência sobre a capacidade física do S21. Não se atribuíram nomes de
canal/rank ou semântica JEDEC aos campos só pela aparência do código.

## Origem candidata das palavras de geometria

`0x2f130` percorre quatro slots e dois termos, zera os slots e prepara
pedidos com W0=slot, W1=1/2 e W2=5/6/7/8. O ponteiro do pedido vem da
célula relativa **`0x30f20`**. Há outros callbacks de seleção ao redor dos
pedidos; eles também não foram resolvidos ou executados.

Nos trechos de empacotamento `0x2f28c–0x2f360`, o byte baixo da resposta
do seletor 5/termo 0 alimenta os bits 8–15. Os bits 2–5 da resposta do
seletor 8 alimentam os índices; os bits 6–7 alimentam os seletores de
duplicação. O primeiro termo vai para os nibbles 28/24 e o segundo, 20/16.
Isso identifica produtores candidatos dos campos usados na fórmula, mas
não fornece os retornos reais nem comprova a associação nominal da tabela.

## Reprodução e limites do ensaio

```bash
python3 scripts/inspect_bl2_ram_size.py /caminho/sboot.bin
python3 scripts/check_bl2_ram_size_gnu.py /caminho/sboot.bin
python3 scripts/emulate_bl2_ram_size.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
```

`--geometry arquivo.json` no inspetor aceita apenas um array explícito de
quatro u64, em números JSON ou strings inteiras, sem valor padrão de RAM.
O JSON é limitado a 4096 bytes; tipos incorretos, booleanos, negativos,
overflow e estruturas aninhadas são recusados. O sboot deve coincidir em
tamanho e SHA-256 antes de emitir evidência. Erros de entrada na CLI do
inspetor retornam 2, sem JSON parcial.

O harness usa QEMU virt, uma CPU e EL1. A Image de diagnóstico serve apenas
de veículo de boot: o GDB para antes de sua primeira instrução e injeta
somente a folha original e a tabela em RAM. São 33 casos em cada delta de
laboratório `0x40000000` e `0x40200000`. Esses deltas preservam o alinhamento
de página exigido pelo ADRP e não são endereços Samsung medidos.

Os casos incluem gates zero, modo global divergente entre slots, todos os
16 índices nas duas posições, fator 1 versus 2, bits altos, exemplos
sintéticos de 8/12/32 GiB e oito entradas determinísticas de seed `0x2caec`.
O retorno para um breakpoint deve preservar SP inválido `0x12345678`,
X19–X29 e X30, código, tabela, entradas e guardas. **66/66 coincidiram**.
Não se executam o inicializador, os callbacks, a publicação em `0x02038848`,
serviços seguros ou edições FDT. Não é um boot Samsung nem um novo ensaio
do diagnóstico físico/R10.

GNU objdump **2.44** conferiu **300 palavras, 23 destinos relativos e
12 operandos selecionados**. Os **34 testes de host BL2** passaram: dez
novos controles de geometria/parser/identidade e 24 regressões da cadeia
de serviços. Outras **73 regressões LK** passaram. A CLI aceitou um
exemplo sintético explícito de 12 GiB e recusou quatro entradas inválidas
com exit 2, sem JSON. As evidências textuais são
[estática](references/bl2-ram-size-hzc2.json),
[GNU](references/bl2-ram-size-gnu-hzc2.json) e
[QEMU](references/bl2-ram-size-qemu-hzc2.json). Nenhum blob foi adicionado.

O próximo passo nesta frente é resolver a preparação e o callback de
`0x30f20`, seguindo a origem das respostas e os bindings mutáveis. Permanecem
pendentes geometria real, conteúdo publicado, eventual limite aplicado
pelo LK, respostas soc_info/SEC_PGTBL/Harx e resultado das edições do FDT.
Um total calculado não estabelece bancos, reservas ou RAM livre.
