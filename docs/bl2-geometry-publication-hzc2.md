# HZC2: segunda publicação NEWTIME da geometria

Continuação do [empacotamento](bl2-geometry-packing-hzc2.md), sobre o sboot
de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets abaixo são do arquivo; ponteiros usam delta nominal 0x020ea000.

**Foi identificada uma segunda chamada ao wrapper NEWTIME que lê o slot
0x31978 e pode publicar sua geometria pelo ponteiro de 0x30520.** O trecho
original, as duas chamadas indiretas e o prefixo até a primeira escrita
executaram no QEMU com bindings e tradução de memória de laboratório.
Isso fecha a ligação condicional de dados; não observa a publicação no S21.

## Caminho selecionado até a escrita

| Offset | Ação conferida | Condição / limite |
|---|---|---|
| 0x1e85c | Chama 0x1d830, ligado ao empacotador e à folha | Fases e callbacks intermediários não executados nesta entrega |
| 0x1ea18–0x1ea30 | Incrementa u32 de 0x31c28, módulo 2^32 | Páginas X19/X20/X22 devem carregar o contexto selecionado |
| 0x1ea3c | Copia o contador para AP0x02073648 | Store fixo de 32 bits, anterior à publicação |
| 0x1ea44 | Lê u64 de 0x31978 para X0 | Primeira amostra do slot |
| 0x1ea48 | BLR X3, carregado de 0x31510 | Alvo inicial nominal 0x2f6c0 |
| 0x2f6cc | Grava o argumento recebido em AP0x02073638 | Store fixo u64; independe do destino R do callback |
| 0x2f6d8 | Relê 0x31978 para X0 | Segunda amostra, após o store fixo |
| 0x2f6dc–0x2f6e4 | Lê contexto de 0x31998, campo +40 e BLR | Campo inicial em 0x30808 aponta nominalmente para 0x193fc |
| 0x193fc–0x19694 | Busca NEWTIME/chave 0x11111111, seleciona linha e escreve | Só alcança o store se os lookups e a seleção permitirem |
| 0x19694 | STR u64 para R, carregado de 0x30520 | Valor original da segunda amostra, antes de normalizar a chave de comparação |

Os argumentos originais W1/W2 de 0x1dc90 são salvos em W23/W24 e passados
nessa fase, mas o wrapper selecionado obtém a entrada do callback pela
recarga de 0x31978. O ensaio começa no fragmento de 0x1ea18: não executa
0x1dc90 inteiro ou prova que todas as fases anteriores retornam/preservam
os registradores e tabelas.

Há **dois stores de valores diferentes em potencial**: AP0x02073638 recebe
a primeira amostra; R+0 recebe a segunda. Coincidem sob estabilidade do
slot e bindings disjuntos/preservados. Não há sincronização que imponha
igualdade entre as duas leituras no trecho selecionado. Uma mudança foi
fornecida explicitamente pelo harness em seis casos; não se afirmou que
ela ocorra no aparelho.

O callback normaliza a chave para low32 quando o bit 63 da entrada está
ligado, mas conserva o u64 original para o store. Erros anteriores ao store
são 3 para nome ausente, 2 para chave ausente e 1 para linha não encontrada.
O contador e a cópia fixa do argumento já foram escritos nesses casos.
**Alcançar 0x19694 não significa concluir o callback:** ainda existem versões,
diretório, gate, alocações/cópias e erro 4, analisados separadamente no
[ciclo NEWTIME](newtime-record-hzc2.md).

## R variável e recarga fixa

O wrapper não deriva sua cópia de argumento de R: constrói o endereço
AP0x02073638. Já 0x19694 usa o ponteiro ativo de 0x30520. A cadeia ACPM
anterior permite a hipótese R=AP0x02073600; ela continua condicionada a
aliases, valor lido e preservação, conforme o [handshake](acpm-handshake-hzc2.md).

No laboratório foram usados R=0x02073600 e R=0x02075600. No segundo, o
primeiro u64 do registro fixo permanece com o marcador, mesmo quando o
callback publica geometria em R. A escolha alternativa testa a separação
dos destinos; não confirma o valor do ponteiro no telefone.

Se o wrapper retornar, as chamadas seguintes no fragmento são:

1. 0x1ea50, tabela+136: alvo nominal **0x2ef90**;
2. 0x1ea60, tabela+192: alvo nominal **0x2d568**, que contém a recarga fixa
   AP0x02073600 → estado 0x31978;
3. 0x1ea68: outro callback, fora deste escopo.

0x2ef90 pode ler 0x158609b0 e atualizar campos de **0x158609bc** a partir
de metadados apontados pelo registro. Esse helper e as chamadas posteriores
não executam no novo ensaio. Portanto a primeira escrita identificada não
estabelece preservação final, nova amostra do gate, conteúdo após a recarga
ou capacidade RAM/FDT final.

## QEMU com mapeamento MMU fornecido pelo harness

[Resultado](references/bl2-geometry-publication-qemu-hzc2.json): **160 casos**,
**74 chegam à primeira escrita** e **86 param no erro do prefixo**. São
80 vetores por colocação de código, deltas 0x40000000/0x40200000:
as 22 linhas embutidas, o primeiro slot dos 50 vetores do empacotador,
dois casos de R alternativo, três mudanças entre cargas, dois controles de
lookup e uma entrada bit63 com wrap do contador.

As saídas do empacotador são materializadas pelo modelo já conferido na
entrega anterior; **o empacotador não executa novamente neste runner**.
Metadados de parser são materializados no host, com todos os descritores.
Os dois ponteiros de chamadas e os ponteiros de dados são ligados às
regiões RAM do laboratório.

O fixture de MMU já existente em `r8/tests/entry_diag_state.S` executa em
EL1 e instala M=1, C=0. O harness fornece tabelas **RW** distintas do caso
RO usado pelo teste original do diagnóstico: identidade para RAM QEMU
[0x40000000,0x80000000), mais o bloco virtual
**[0x02000000,0x02200000)** mapeado para RAM física QEMU
**0x41000000/0x41200000**, conforme a colocação. Todo esse mapeamento é
sintético; não é o alias de barramento Exynos ou uma região física validada.

Assim, as instruções originais produzem os endereços AP fixos e os stores
atravessam a tradução para RAM. **Não se alteram instruções de firmware,
não se pulam as chamadas de publicação e não se reatribuem seus registradores
de endereço.** Entre os stops do wrapper e do prefixo, a única alteração
de dados fornecida pelo GDB é a mudança declarada do slot nos três vetores
indicados. Não fornece respostas de MMIO.

Execução para em 0x19698, imediatamente após o store, ou em 0x199fc,
antes do epílogo de erro. Não executa o restante do callback, retorno do
wrapper, helper de erro, gate MMIO ou chamadas posteriores. Como para dentro
do callback, não declara ABI/SP restaurados no retorno. Foram conferidos
os LRs salvos das duas chamadas, frame/entrada, linha/tail quando encontrados,
contador, amostras, ponteiro ativo, **0x4400 bytes** da janela com guardas
pelas duas visões de endereço, pilha, código, fontes, metadados, contexto,
slot do wrapper, fixture e tabelas de tradução.

## Reprodução e próximos passos

```bash
python3 scripts/inspect_bl2_geometry_publication.py /caminho/sboot.bin
python3 scripts/check_bl2_geometry_publication_gnu.py /caminho/sboot.bin
python3 scripts/emulate_bl2_geometry_publication_qemu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
python3 -m unittest discover -s scripts -p 'test_newtime*.py' -v
```

[Estático](references/bl2-geometry-publication-hzc2.json) e
[GNU 2.44](references/bl2-geometry-publication-gnu-hzc2.json): **464 palavras**,
111 novas e 353 do prefixo, **59 alvos relativos, 29 operandos e cinco
ponteiros nominais**. Índice SHA-256
`e69c013fddb93ce3b3335900cca58aa993e4f256bd37975c79156718677cbf4f`.
**Oito testes novos e 111 anteriores passaram**, nove recusas CLI de
imagem curta/longa/alterada antes de GNU/QEMU, relatórios estático/GNU
reproduzidos byte a byte, Python compilado e links conferidos.
[Validação](references/bl2-geometry-publication-validation-hzc2.json).

Próximo: seguir os efeitos após o retorno do wrapper e a recarga do registro,
preservando a distinção entre publicação condicional e estado físico. Aliases,
respostas reais, preservação transitiva, limite LK e bancos/reservas finais
continuam pendentes.
