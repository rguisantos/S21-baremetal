# HZC2: publicações do carregador DMC17 e cauda de configuração

Continuação de 30/10/2026 (Campo Grande), base `6573250`, na PR53.
Mesmo sboot de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets do arquivo; dados core têm a tradução Thumb selecionada,
sem alias físico observado. A [rota DMC17](newtime-domain0-callees-hzc2.md)
fornece dois argumentos ao carregador: byte header+8 e índice low8.

**O teste inicial de tamanho não interrompe o carregador: seu callee é um
`BX LR`. O corpo publica ponteiros antes da cauda e só retorna zero após
ela retornar.** Não há certificação física ou rollback obtido desse zero.

## Comparação inicial e seleção de grupo

`0x647be/0x647c0` comparam, com sinal,
`u32(0x3a600+M32[core0x3a610])` e `0x3c9ff`. Quando o primeiro é maior,
chamam `0x60c6c` com R0=4. Essa rotina contém somente `BX LR`, então o
corpo continua em `0x647c8`. O argumento original R0 já foi salvo na pilha.
O teste não impõe o limite comparado nesse trajeto; outras fronteiras de
memória, serviços e execução física não foram excluídas.

O carregador lê a palavra em `0xa58609bc`. Com segundo argumento completo
k, há duas decisões distintas:

| Decisão | Expressão selecionada |
|---|---|
| Indicador superior | `(((mask>>16)&0x7fff) ASR low8(k))&1`; grava state+0x229 e core0x3a658 |
| Grupo alternativo | `s32(k)>5` e bit0 de `(mask&0xffff) ASR low8(k)` não zero |
| Índice ajustado | `j=u32(k-6)` no grupo alternativo; j=k no comum |

Bit31 da palavra não entra no indicador superior. O ASR usa low8 da
contagem, mas a comparação signed com5 usa o k completo. Para o k u8 do
caller modo2, somente6..15 podem selecionar o grupo alternativo. k255
seleciona o grupo comum, sem um guard local de limite desse índice.
Fixtures com argumentos completos distinguem esse contrato do caller u8;
não se afirma que todos esses argumentos sejam alcançáveis pelo callback.

## Ponteiros publicados antes da cauda

Na tabela abaixo, B=core `0x3a600`, S=core `0x381c8` e
`off_i=M32[core0x3a7a0+16*i+4]`. Todas as contas têm wrap u32.
As fórmulas correspondem a descritores preservados e fixtures sem aliases
intermediários; a sequência de stores e releituras define os casos com alias.

| Campo de S | Grupo comum | Grupo alternativo |
|---|---|---|
| +0xa4 | B+off1+64j | B+off2+64j |
| +0xa8 | B+off9+8j | B+off10+8j |
| +0xa0 | B+off3+4×stride3×j | B+off4+4×stride3×j |
| +0x1ec | B+off5+4×stride5×j | B+off6+4×stride5×j |
| +0x1e8 | B+off5+4×stride5×arg0 | B+off6+4×stride5×arg0 |
| +8 | B+off7+4×M8[S]×j | B+off8+4×M8[S]×j |

stride3/5 são as palavras +8 dos descritores3/5, inclusive no grupo
alternativo. **Os campos +0x1e8 e +0x1ec usam argumentos diferentes.**
O primeiro alimenta a fonte do [método seguinte](newtime-domain0-callees-hzc2.md);
o segundo é usado pela cauda para editar o descritor da linha ajustada.

Publicações comuns: S+0x10 recebe B+off11; +0x1e4 recebe B+off12;
+0x23c recebe B+off14 (cache h/g2); +0x204 recebe B+off15 e +0xac recebe
B+off0. Uma store indireta usa `M32[S+0x9c]+36` para B+off13. Depois,
S+0x240/+0x244 recebem as duas primeiras palavras do header e S+0x209
recebe o nibble4..7 da primeira palavra copiada.

Os descritores não são congelados todos de uma vez. Uma fixture faz a
store indireta alcançar stride3; a publicação posterior de S+0xa0 usa
o novo stride. Isso confirma a sequência condicional, sem demonstrar esse
alias no aparelho ou excluir outros escritores.

## A cauda lê controles e ainda pode alterar dados

`0x6494c` chama `0x64a64` depois dessas publicações. A cauda relê
`0xa58609a8`: bits24/25/26 habilitam alterações de campos no descritor
apontado por S+0x1ec. Há stores de byte, halfword e palavra. Os testes
conferem os campos sobrepostos e permitem valores diferentes entre
releituras do mesmo controle; não se modelou uma fotografia única.

Outro controle, `0xa58609ac`, é relido para gates dos bits24..28. As
sequências podem chamar os métodos+16/+40 da tabela core `0x37fb4`, com
IDs11,41,18,17 e3. Seus alvos iniciais são core `0x369a5`/`0x369d1`,
arquivos `0x641a4`/`0x641d0`. Na entrega inicial, fixtures substituíam seus
retornos e alteravam registradores voláteis. A [continuação dos serviços](newtime-dmc-table-services-hzc2.md)
agora delimita ambos como operações sobre tabela e identifica um consumidor
separado, sem estabelecer sua ordem real de aplicação depois da cauda.

Não há agregação local de erros dos serviços. Valores devolvidos pelos
leitores são tratados como dados; a cauda termina com R0=0, e o próprio
carregador também coloca R0=0 depois que ela retorna. Se a cauda não
retorna, o carregador não alcança seu zero final; as publicações anteriores
já aconteceram. Retorno zero e ponteiro publicado não são sucesso físico.

A integração agora interpreta wrapper de dois métodos → carregador inteiro
→ cauda → método0x65124, sob controles zero e raízes explícitas. Outros
testes habilitam campos e serviços da cauda. Isso fecha os corpos locais,
mantendo efeitos dos serviços, estado físico e preservação como condições.
Não se afirma que todos os ponteiros/descritores fiquem intactos após a cauda.

## Reprodução e validação

```sh
python3 scripts/inspect_newtime_dmc_loader_hzc2.py /caminho/sboot.bin --json /tmp/loader.json
python3 -m unittest discover -s scripts -p 'test_newtime_dmc_loader.py'
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_dmc_loader_hzc2.py),
[20 testes](../scripts/test_newtime_dmc_loader.py),
[JSON](references/newtime-dmc-loader-hzc2.json) e
[validação](references/newtime-dmc-loader-validation-20261030.json).
GNU:479 instruções/499 halfwords/20 alvos/32 literais/33 operandos.
Suíte NEWTIME: **663 testes aprovados**. Os256 índices u8, os dois grupos,
ASR signed/low8/carry, UXTH e STRH com wrap, aliases e retornos parciais
foram conferidos com palavras reais. Relatórios de validação anteriores
permanecem históricos das suas árvores; este registra os hashes atuais.
JSON reproduzido exatamente e três imagens inválidas recusadas exit2 sem
stdout/JSON. Sem execução Samsung ou ampliação QEMU do firmware.

Restam outros serviços/caminhos do consumidor, o restante de0x5a2b8, produtor do magic
0xabcd1234, ordem init9/máscaras e slot47/X0. As condições físicas e de
alcançabilidade continuam separadas dos resultados do modelo de host.

Continuação de31/10: o [produtor local do magic](newtime-dmc-magic-hzc2.md) foi delimitado em0x369a0, com publicação/campainha/poll e sem alegação de escritor global único ou EL3 efetivo. Aliases físicos, ordem ACPM e slot47/X0 continuam abertos.
