# HZC2: tabela da cauda DMC17 e consumidor de publicação

Continuação de 30/10/2026 (Campo Grande), base `296bc4a`, na PR53.
Sboot:4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets do arquivo; endereços core e aliases físicos não são
intercambiáveis. Mantêm-se as condições de instalação/preservação das raízes.

**Os serviços `0x641a4/0x641d0` usados pela cauda operam uma tabela em
memória. Um consumidor separado pode encaminhar seus valores ao publicador
`0x615ec`, que retorna zero após stores, sem confirmação local.** A ligação
não estabelece a ordem física de aplicação depois do DMC17.

## Registro de quatro bytes: primeiro resultado versus todas as escritas

S=core `0x381c8`: count é M8[S], e a tabela vem de M32[S+8]. Cada registro
tem quatro bytes; os serviços usam valor em+0 e ID em+1. Bytes2/3 não
participam desses corpos. As rotinas não contêm chamadas nem polls locais.
PUSH/POP continuam produzindo os acessos usuais à pilha nos testes.

| Serviço | Comportamento selecionado |
|---|---|
| `0x641a4`, leitura | Captura count e ponteiro uma vez; devolve o primeiro valor u8 cujo ID coincide com R0, ou0xffffffff |
| `0x641d0`, escrita | Captura o ponteiro uma vez, relê count em cada iteração e grava low8(R1) em todos os registros coincidentes |
| Retorno da escrita | Mantém R0, o ID recebido, inclusive sem coincidência ou com count0; não informa quantidade de alterações |

O ID de entrada é comparado como R0 completo com um byte, sem truncamento.
ID0x10b não equivale a11. Duplicatas são lidas pela primeira ocorrência e
atualizadas em todas. A escrita de memória pode alterar count: fixtures
fazem o laço crescer de1 para2 ou parar depois da primeira store. Outra
store muda a própria célula S+8; o laço continua usando o ponteiro capturado.
Os testes de memória ausente conservam escritas anteriores e não inventam0.

Sob raízes explícitas, a [cauda do carregador](newtime-dmc-loader-hzc2.md)
foi integrada com os dois corpos reais, substituindo os hooks anteriores.
Ela altera valores da tabela sem precisar das raízes do publicador MMIO.
Isso não exclui aliases arbitrários da tabela ou outros escritores no
aparelho; identifica os acessos selecionados e seu encaminhamento nominal.

## Consumidor separado

`0x63fb0` captura primeiro a leitura do ID18. Depois percorre registros,
relendo count e ponteiro da tabela em cada iteração. O código em
`0x64120` o chama com argumento0, dentro da rotina `0x640e8`, alvo inicial
do método+0 da tabela core `0x37fb4`.

| Tipo de registro | Caminho local |
|---|---|
| ID16 | Pula o registro |
| ID18 | Usa low8 do resultado inicial de leitura18, com OR0x10 quando M8[S+0x229]==1; duplicatas usam o mesmo resultado capturado |
| ID21 | Chama método+104 de core0x37d40 com (0,1,21); publica somente se low3 do retorno forem7 |
| ID30 | Tem subcaminho especial ainda não interpretado nesta entrega; bytes estáticos exportados |
| Demais | Publica o byte do registro se argumento0 for zero ou o filtro local do ID retornar não zero |

O filtro compara15 IDs do arquivo:1,2,3,10,11,12,14,15,17,18,19,20,24,30,41.
Com argumento zero, os registros ordinários não passam por ele. Outros
valores do argumento habilitam o filtro. O retorno low3=7 do ID21 é um
teste de bits, não uma classificação de sucesso:0xffffffff também passa.
O alvo inicial desse leitor é core0x34471 → arquivo0x61c70 e permanece hook.

As chamadas de publicação usam o método+100 da mesma tabela, inicialmente
core0x33ded → arquivo0x615ec, com argumentos
`(4,M8[S+0x209],ID,valor)`. O retorno não é agregado nem testado no avanço.
R0 final depende do caminho: count0 ou somente ID16 podem conservar-1 da
leitura18 inicial; uma publicação pelo corpo nominal deixa0. Não existe
um status agregado do conjunto de registros.

O teste de integração executa carregador→cauda→serviços da tabela e só
então invoca explicitamente o consumidor. Confere os bytes preparados e
os valores encaminhados, inclusive duplicatas. **Essa ordem é uma fixture,
não uma observação de boot nem prova de chamada automática do consumidor.**
Outro teste interpreta `0x640e8`, sua publicação inicial de ID16 e a chamada
direta do consumidor, mantendo o alcance real desse método como condição.

## Canal4: entrada0 na leitura, entrada4 na escrita

`0x615ec` aceita canais unsigned0..4; outros retornam-1 antes de ler a
tabela. Para0..3, lê a configuração pela própria entrada. Para canal4,
lê a palavra na **entrada0** e escreve na **entrada4** de core `0x37df8`.
Não se presumiu igualdade das bases. Sob essas raízes preservadas:

`config = (((old & 0xcfffffff) | ((arg1 & 3)<<28)) & 0xf80fffff) | ((arg2 & 127)<<20)`.

| Ordem | Store selecionada |
|---|---|
| 1 | destino+0 = config |
| 2 | destino+0x38 =22 |
| 3 | destino+8 = R3 completo |
| 4 | destino+4 =16 |

O publicador não relê status após essas stores nem faz poll local; retorna0.
O consumidor normalmente fornece um valor u8, mas a rotina isolada não
trunca R3. Esses acessos não comprovam aceitação, sucesso físico ou função
elétrica dos registradores. Erros posteriores e outros consumidores
continuam fora dessa conclusão.

## Reprodução e validação

```sh
python3 scripts/inspect_newtime_dmc_table_services_hzc2.py /caminho/sboot.bin --json /tmp/table-services.json
python3 -m unittest discover -s scripts -p 'test_newtime_dmc_table_services.py'
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_dmc_table_services_hzc2.py),
[20 testes](../scripts/test_newtime_dmc_table_services.py),
[JSON](references/newtime-dmc-table-services-hzc2.json) e
[validação](references/newtime-dmc-table-services-validation-20261030.json).
GNU:258 instruções/267 halfwords/33 alvos/12 literais/32 operandos.
Suíte NEWTIME: **683 testes aprovados**, com80 tabelas aleatórias,
duplicatas, aliases, raízes distintas, releituras e retornos do consumidor.
ADCS foi adicionado ao avaliador com carry/overflow e carry de entrada
conferidos. JSON reproduzido exatamente e três imagens inválidas recusadas
exit2 sem stdout/JSON. R10 não foi alterado; seu baseline permanece no CI.

Sem execução Samsung ou ampliação QEMU do firmware. Próximo: caminho ID30,
leitor0x61c70 e quem aplica a tabela em relação à cauda. Restante de0x5a2b8,
produtor de0xabcd1234, ordem init9/máscaras, condições físicas e slot47/X0
continuam abertos. Validações anteriores permanecem históricas das suas árvores.
