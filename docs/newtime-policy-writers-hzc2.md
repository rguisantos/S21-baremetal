# HZC2: escrita do limite FVP e de sua habilitação

Análise estática em 2026-10-29, base `2d80c18`. Complementa a
[seleção FVP](newtime-fvp-effective-hzc2.md) e os
[retornos do serviço](newtime-return-planes-hzc2.md).
Firmware4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; dados são endereços core ACPM nominais.

## Dois setters e uma seleção posterior

| Caminho selecionado | Dado e destino | Continuação direta |
|---|---|---|
| Comando4, canal1 | palavra1 inteira → `S+140*domínio+16` em3f5aa | aloca resposta, publica e retorna0 |
| Comando5, palavra3=2 | palavra1 inteira → core120a0 em3f69c | aloca resposta, publica e retorna0 |
| Comando6, domínio0 | relê esses campos durante o cálculo do efetivo | seleciona helper3f0d0, sujeito a seus gates |

S=core120f0. Domínio do comando4 vem de low16 da palavra0; valor vem de
palavra1, carregada emR8. O gate3f33c exige canal1 para a store. O braço
selecionado não verifica se domínio é apenas0/1 antes de multiplicá-lo
por140; a análise funcional e as fixtures principais usam esses dois
domínios. Nenhuma configuração ou entrada fora deles foi observada.

No comando5, subseletor é a **palavra3**, não o domínio da palavra0.
3f35e/3f362 leva ao setter global. O braço não impõe o mesmo gate canal1;
a fixture canal2 alcança a store sob entrada/raízes compatíveis, sem
provar entrega real desse evento. A palavra de habilitação não é
normalizada para0/1: 2,0x80000000 e0xffffffff são preservados. O consumidor
comando6 usa teste zero/não zero.

## O que uma resposta zero confirma nesse caminho

Não há BL/BLX direto ao helper3f0d0 ou ao relay DVFS nos dois trajetos
selecionados após as stores. Também não há store selecionada ao efetivo
S+0, espelho12208, direção12210 ou cache12714. As chamadas indiretas são
alocação da resposta (API+12) e publicação (API+16), seguidas de logging.
Se terminam normalmente e preservam o estado carregado, o callback
retorna0. Seus efeitos opacos continuam fora da conclusão local.

Assim, o retorno0 do setter é compatível com o novo limite gravado e o
estado efetivo anterior ainda presente. A store de limite3f5aa precede o
alocador3f5b0; resposta não concluída não prova desfazer essa store. Não se
conclui execução imediata no hardware a partir dessa confirmação.

Fixture encadeada: efetivo300, concorrentes0, limite inicialmente1000 e
habilitação1. Comando4 grava limite100 sem alterar efetivo300 no trajeto
selecionado. Uma **nova invocação explícita** de comando6/pedido300 relê
limite100 e seleciona efetivo100. Desabilitar o cap por comando5 também
não atualiza o efetivo nesse braço; novo comando6/pedido500 pode selecionar500.
Nenhum retry automático, temporizador ou outro evento foi demonstrado.
Outros escritores/handlers podem recomputar a seleção e continuam abertos.

## Reprodução e limites

[Extrator](../scripts/inspect_newtime_policy_writers_hzc2.py),
[JSON](references/newtime-policy-writers-hzc2.json) e
[dez testes](../scripts/test_newtime_policy_writers.py).
O extrator reutiliza a validação de tamanho/hash e GNU do FVP e confere
os operandos dos setters, gates e retorno. O JSON exporta as janelas
selecionadas; a contagem GNU é do escopo completo do extrator FVP reutilizado.

O decoder dos testes interpreta palavras Thumb cruas, com hooks explícitos
para alocação/publicação/logging que alteram R0–R3/IP e preservam os
registradores carregados. As fixtures encadeiam os setters ao interpretador
já usado na seleção comando6. Não se substituiu callback opaco por prova de
preservação física, nem orçamento de host por timeout do firmware.

```sh
python3 scripts/inspect_newtime_policy_writers_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime_policy_writers.py'
```

Sem execução Samsung, sem alteração do escopo QEMU e sem novo resultado
sobre slot47/X0. DMC método+12/subcomandos8/9 continua frente complementar.
