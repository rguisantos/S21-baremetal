# HZC2: destino NEWTIME e origem dos parâmetros bootstat

Continuação de **2026-10-24 (Campo Grande)** das
[referências BL2 no kernel](bl2-kernel-consumers-hzc2.md). Mesmo sboot de
4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets de código/estado são **relativos ao arquivo/imagem**; endereços de
registradores e literais físicos são identificados à parte.

**Foi resolvido um callback nominal que consulta NEWTIME e escreve u64
por um ponteiro mutável.** Sua escrita no primeiro u64 de 0x02073600 segue
condicional. Os três formatos bootstat também foram ligados aos argumentos
do LK. Nenhum valor físico, tabela viva ou duração de boot foi observado.

## Callback anterior à recarga DRAM

| Testemunho selecionado | Ligação nominal |
|---|---|
| 0x17fbc–0x17fc4; call 0x18000 | X3 recebe 0x307e0 antes de chamar 0x1dc90 |
| 0x1dcb4–0x1dcbc | Se X3 não for zero, guarda contexto em estado 0x31688+784 = 0x31998 |
| 0x2f6d0–0x2f6e4 | Lê o slot 0x31978 para X0, o contexto de 0x31998 e seu ponteiro +40, depois BLR |
| Célula inicial 0x30808 | 0x021033fc; com delta 0x020ea000, destino nominal 0x193fc |
| 0x19454–0x19484 | Passa NEWTIME, string de 0x2fd48, a 0x1c55c; depois chave 0x11111111 a 0x1c83c |
| 0x1967c–0x19694 | Lê ponteiro de 0x30520 e escreve nele um u64 carregado do frame+136 |

O frame+136 é inicialmente preenchido com X0 em 0x19418. Sua preservação
por todo o callback e o efeito líquido das chamadas/escritas posteriores
não foram provados. As recusas selecionadas retornam 3 se a primeira
consulta retorna NULL e 2 se a segunda retorna NULL. Os dados retornados
e a linha escolhida não foram recuperados do aparelho.

A [continuação ECT/NEWTIME](newtime-ect-hzc2.md) recuperou a tabela
embutida e executou o parser e o prefixo até 0x19694 no QEMU. O frame+136
e as 16 células da linha foram conferidos em bindings de laboratório;
isso não comprova preservação pelo corpo posterior ou execução no aparelho.

O [rastreio posterior do registro](newtime-record-hzc2.md) conferiu o
primeiro u64 no retorno direto do callback em blocos originais com ramos
do gate fornecidos pelo harness. O wrapper encaminha códigos de erro a
outro helper; seus efeitos e a preservação física permanecem pendentes.

O slot de entrada pode conter o marcador temporário 0xcafe da
[etapa anterior](bl2-geometry-record-hzc2.md); não convertê-lo em geometria
real. Passagem pelo callback, binding e retorno normal são condicionais.

## Destino: literal inicial e atualização do ponteiro

0x30520 contém inicialmente **0x02075600**, distinto do registro DRAM
**0x02073600**. Um escritor em **0x17fe8** lê X1 da configuração relativa
**0x31a48**, adiciona 0x1000 e 0x800 e guarda X2 no ponteiro. O literal do
arquivo não determina seu destino ativo depois dessa atualização.

Um escritor selecionado da configuração em **0x17a0c** recebe uma leitura
de 32 bits de **0x15900108**, soma 0x02039000 em W e grava o resultado
estendido com zeros em X. Com preservação das células entre essas etapas:

```text
destino = ((leitura_u32(0x15900108) + 0x02039000) & 0xffffffff) + 0x1800
```

**Nessa cadeia, destino == 0x02073600 exige leitura_u32 == 0x38e00.**
É um critério calculado, sem valor fornecido ao inspetor ou medido.
Não foram executados o poll anterior ou a leitura do registrador,
excluídos outros escritores ou demonstrada preservação por chamadas.
Portanto 0x19694 ainda não é uma escrita comprovada no registro DRAM do
telefone. Também não se descarta o alias usando somente o literal inicial.

O avanço é a fronteira explícita: contexto, store u64, ponteiro mutável,
escritor do ponteiro e entrada de registrador. Origem/valor desse
registrador, bindings e conteúdo real continuam pendentes.

A [continuação ACPM](acpm-handshake-hzc2.md) encontrou um produtor Thumb
de **0x38e00** no endereço local **0xa5900108**, com espera pela confirmação
zero. O critério acima agora tem um produtor estático correspondente;
alias com AP 0x15900108, execução/preservação e valor real seguem abertos.

## Bootstat: rótulos e argumentos fornecidos pelo LK

| Formato | Índice no getter 0x149848 | Call do getter | Call do helper de formatação |
|---|---:|---|---|
| sec_bootstat.boot_time_bl1=%d | 0 | 0x1452b0 | 0x1452c0 |
| sec_bootstat.boot_time_bl2=%d | 1 | 0x1452c8 | 0x1452d8 |
| sec_bootstat.boot_time_bl3=%d | 2 | 0x1452e0 | 0x1452f0 |

Cada retorno X0 é movido para X1; **0x144618** recebe o formato em X0.
A entrega final da linha ao kernel não foi reexecutada/observada.
Setter **0x149830** e getter **0x149848** usam tabela de estado relativa
**0xcd3568**, stride de oito bytes e índice W0. O setter estende W1 com
zeros e escreve 64 bits; o getter lê 64 bits. Os dois corpos não contêm
checagem de limites do índice. O inspetor não executa esses acessos.

A busca de encodings BL no intervalo de arquivo LK 0xec000–0x20c630
encontrou quatro calls diretos do setter:

| Call | Índice | Origem selecionada do argumento |
|---|---:|---|
| 0xee6ac | 0 | **Literal 100** |
| 0xee6e4 | 1 | Retorno de 0x111c40 + entrada zero, seguido de conversão inteira |
| 0xeec30 | 2 | Mesma forma, em outro trecho |
| 0xeed50 | 2 | Mesma forma, em outro trecho |

A busca não é censo de código alcançável, aliases ou chamadas indiretas;
não foi presumido qual dos dois últimos caminhos executou. **0x111c40**
lê **CNTPCT_EL0** e segue para **0x1118f8**. O resultado da conversão do
contador e suas unidades ainda não foram validados nesta entrega.
No trecho posterior, a expressão selecionada é:

```text
n = (retorno_do_helper + entrada_zero) mod 2^64
y = UMULH(n >> 3, 0x20c49ba5e353f7cf) >> 4
setter recebe os 32 bits baixos de y
```

O literal 100 no campo BL1 e os cálculos no LK mostram por que os rótulos
não comprovam três durações medidas de BL1/BL2/BL3. Tampouco fornecem
geometria ou capacidade RAM.

## Validação e reprodução

```bash
python3 scripts/inspect_boot_metadata_hzc2.py /caminho/sboot.bin
python3 scripts/check_boot_metadata_gnu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
```

O inspetor exige tamanho/SHA exatos, sem valores opcionais de registrador
ou tabela. [Estático](references/boot-metadata-hzc2.json): 156 palavras.
[GNU 2.44](references/boot-metadata-gnu-hzc2.json): 156 palavras, 26 alvos
relativos, 39 operandos, três produtores MOV/MOVK e seis ponteiros/strings.

Os **70 testes BL2 existentes** passaram. Os dois comandos recusaram
imagem curta, longa ou alterada com exit 2 e sem JSON parcial: seis
controles CLI. Compilação Python, reprodução dos relatórios e aritmética
do critério de alias conferidas. Sem novo QEMU, MMIO, kernel, serviço
seguro ou operação no telefone.
