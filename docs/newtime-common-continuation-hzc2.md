# HZC2: continuação comum NEWTIME em 0x1aff0

Análise estática de 2026-10-28 (Campo Grande), base `054f5c8`, após PR #49.
A fronteira comum do [primeiro switch](newtime-jump-tables-hzc2.md) agora
tem grafo local, argumentos e escritas delimitados. **O chamador do slot 47
e a origem do X0 de `0x2d364` permanecem abertos.**

## Escopo e nomes locais

Mesmo `sboot.bin` HZC2 de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs abaixo são offsets de arquivo; delta nominal BL2 `0x020ea000`.
Não houve execução Samsung, leitura MMIO nem ampliação QEMU.

O grafo sintático de `[0x1aff0,0x1b37c)` cobre 227 PCs, sete BLs e um RET
em `0x1b378`. Não há BR/BLR nessa janela. Ambos os braços de cada condição
são seguidos sem prova de viabilidade; seguir após BL exige retorno normal.
Isso não fecha os efeitos dos callees nem prova execução desse caminho.

| Nome | Origem sob preservação dos valores e metadados |
|---|---|
| F | X29, frame após prólogo de 224 bytes em `0x1aab4` |
| D | X28, retorno do lookup em `0x1ab94`, ou zero |
| n | W23, carga `[D+16]` em `0x1aba0`, ou zero |
| B | X25, retorno do alocador em `0x1abb4` |
| C | X24, retorno do lookup em `0x1ab58`, ou zero |
| E | X26: lookup inicial `0x1ab7c`/zero; pode ser substituído em `0x1ad78` pelo retorno de `0x1ad74` |
| G | estrutura global nominal correspondente ao arquivo `0x31aa8` |
| Q | zero ou retorno opaco de `0x1a804`, conforme o caminho |

Os nomes são papéis locais. Não atribuem significado físico aos campos nem
estabelecem que um descritor, buffer ou endereço zero seja válido no aparelho.
O retorno em `0x1b35c` copia B para X0 antes de restaurar o X25 do chamador.

Antes do switch, `0x1ad68` busca o handle de MARGIN. Se ele é zero,
`0x1ad6c` preserva o X26 inicial. Se não é zero, `0x1ad74` procura a entrada
por nome e `0x1ad78` substitui X26 pelo resultado, inclusive se esse resultado
for zero. Essa redefinição foi acrescentada ao cruzar a auditoria MIF com
a continuação; E não deve ser descrito apenas pela busca inicial.

## Alocação e layout do resultado

`0x1abb0` calcula **u32(4*n)** em W0. O alocador `0x18068` usa SXTW
em `0x18078`, atualiza a célula de cursor `0x31a50` antes do teste unsigned
contra o limite de `0x31a58`, e retorna o cursor antigo. O comportamento
já delimitado na [análise do record](newtime-record-hzc2.md) permanece:
ultrapassar o limite leva ao laço em `0x18090`; não há retorno NULL/rollback.
O pedido pode tornar-se negativo ou sofrer wrap antes da extensão:
n=`0x20000000` produz W0=`0x80000000`; n=`0x40000000` produz W0=0.
Esses são modelos de host, não tamanhos observados nem condições aceitas
com segurança pelo firmware. A base B e sua separação das células do slot
47/binding não foram demonstradas.

| Store | Destino/valor condicional |
|---|---|
| `0x1b0d0` | byte em B+4*i+3, vindo de descritor no caminho de fallback |
| `0x1b318/0x1b320` | byte em B+4*i+3, resultado do helper com/sem correção |
| `0x1b110` | soma de byte de E ao byte B+4*i+3, módulo 256 |
| `0x1b134` | soma semelhante no byte Q+4*i+3 se W27 != 255 |
| `0x1b178` | low8(i) no ponteiro recebido pelo argumento X5, se o level coincide |
| `0x1b198` | palavra em B+4*i, preservando o byte superior |

A última palavra é
`(anterior & 0xff000000) | (u32(level[i]*1000) & 0x00fffff8)`.
O caminho com correção interpreta um byte v como v para v<=160 e como
160-v para v>=161; soma ao W0 retornado e armazena apenas low8.
O cálculo numérico de W0 pelo helper não foi implementado nesta entrega.

Os laços usam n, índices W/X e condições próprias; as fórmulas pressupõem
que descritores/frame e as bases carregadas conservem os valores indicados.
Não são uma prova de bounds de leitura/escrita nem de ausência de aliases.

## Leitor de quatro campos e fronteiras de chamadas

O helper de dez instruções `[0x1a26c,0x1a294)` lê campos de 16 bits:

`index = u32((part >> 1) + u32(selector << 1))`

`resultado = (M32[nominal(G)+108+4*index] >> (16*(part&1))) & 0xffff`.

Os quatro BLs em `0x1b1b0`, `0x1b1c4`, `0x1b1d4` e `0x1b1e4` passam
part=0,1,2,3 e o seletor W21. Os últimos três só ocorrem se o primeiro
campo não for zero; todos dependem de uma linha C encontrada e habilitada.
O corpo exato só altera X0/X1/X2, preservando X3 (linha C) e W4 (enable).
Não se usou a ABI para presumir preservação desses registradores voláteis.

Nos 20 casos do switch, as definições locais dão seletores 0..11. Sob
preservação, as cargas cobrem 24 palavras em `[0x31b14,0x31b74)`.
**O default unsigned W0>19 salta essas definições**: não há limite de W21
estabelecido para esse caminho. O caso 0 também passa por `0x1a668`, cujos
efeitos são outra frente de investigação; sua preservação é uma condição.

| BL | Argumentos demonstrados localmente, sob as condições anteriores |
|---|---|
| `0x1b278 → 0x1a294` | X0=F+192, X1=F+208, W2=0, W3=0 |
| `0x1b2e4 → 0x1a294` | mesmos arrays, W2=level[i], W3=1 |
| `0x1b354 → 0x1a804` | W0=[F+156], X1=F+192, X2=F+208, X3=D, W4=[F+152], W5=W19, X6=B |

O corpo `[0x1a294,0x1a5b0)` tem 199 palavras, nenhum BL/BLR/BR e nenhuma
referência aos GPRs X13/X14/X15/X18/X25 usados através da chamada do laço.
Isso sustenta a preservação desses GPRs pelo corpo selecionado; não prova
pureza de memória ou valores numéricos. Operações FP e efeitos de memória
desse helper permanecem opacos aqui. O [corpo de 0x1a804](newtime-secondary-result-hzc2.md)
foi seguido separadamente: pode retornar B ou uma nova alocação.

## Casos que exigem cautela na continuação

A busca de registros usa passo 48 e contagem **signed32([D+20])**.
No fallback, escolhe a primeira chave correspondente e, se não houver,
o primeiro registro. Para contagem signed<=0, X2 continua zero e a carga
em `0x1b074` lê endereço zero **antes** de qualquer fallback. No caminho
habilitado, X18 pode igualmente continuar zero antes da carga `0x1b2e8`
se n>0. Isso identifica endereços sintáticos; não demonstra fault,
alcançabilidade ou mapeamento real.

Q é zero no fallback (`0x1b0d8`) e no caminho habilitado com W27=255
(`0x1b334`). Com W27!=255 no caminho habilitado, vem de `0x1a804`.
A store `0x1b134` testa E, n e W27, **sem guard Q!=0**. A combinação
sintática fallback/W27!=255/E presente/n>0 deixa endereços 4*i+3.
Não foi demonstrado que essa combinação de entradas ocorra no aparelho.

Não há chamada direta ao slot 47 na janela; essa constatação local não
exclui transporte/alias por B, Q, argumentos ou efeitos dos callees.
A ausência de base dinâmica e de preservação comprovadas impede concluir
que `0x31580` ou `0x31998` não sejam escritas por esses caminhos.

## Reprodução

```sh
python3 scripts/inspect_newtime_common_continuation_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

O [extrator](../scripts/inspect_newtime_common_continuation_hzc2.py) exige
hash/tamanho exatos, confere GNU 784 palavras, 111 alvos relativos e 56
operandos selecionados. O [JSON](references/newtime-common-continuation-hzc2.json)
inclui as testemunhas completas, grafo e condições. Os
[testes](../scripts/test_newtime_common_continuation.py) verificam wrap W,
SXTW, campos packed, contagens signed, byte de correção, low24 e base Q
zero sem guard inventado. [Validação](references/newtime-common-continuation-validation-20261028.json).

A [folha 0x1a668](newtime-mif-bins-hzc2.md) foi delimitada separadamente:
dois bins e três stores globais nominais, com contrato corrigido. As próximas
fronteiras incluem a origem das bases/metadados e os demais ramos indiretos.
O [resultado secundário](newtime-secondary-result-hzc2.md) mostra Q=B nos
caminhos rápidos dos seletores 2/3 e duas adições ao mesmo byte sob
preservação, E estável e execução do laço; não é uma observação do aparelho.
