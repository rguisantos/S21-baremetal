# HZC2: escopo e resultado da observação no gate NEWTIME

Atualizado em **2026-10-27 (Campo Grande)**, base `a12a8e2` após PR #44.
**As observações foram executadas no runner do repositório.** Os dois casos
chegaram ao mesmo gate, em duas colocações. O ponteiro e o scratch não
mudaram desde a entrada. A predição recebida de scratch zerado foi refutada:
os 108 bytes já entram como `ff` na preparação baseada no arquivo.

O [escopo recebido](references/newtime-gate-scope-received.md.txt) fica
preservado sem alterações, com as predições anteriores à execução. Esta
página revisa a reprodução e registra os resultados sem reclassificar uma
predição refutada como um teste aprovado. Complementa o
[plano consolidado](newtime-plan-consolidated-hzc2.md).

## Escopo aplicado

Somente o callback 0x193fc e a cadeia que já constava no runner foram
executados. O máximo permanece **20000 instruções por caso**. Cada acesso
de memória é conferido antes do single-step. Código fora da lista, operações
de sistema, acesso fora da RAM permitida, epílogo compartilhado e orçamento
continuam sendo fronteiras. Não houve resposta MMIO/SMC, valor de gate,
mudança de PC durante a cadeia, execução de consumidores ou avanço do gate.
A seleção inicial de PC/registros é a preparação de laboratório já existente.

`0x26e14`, `0x25b80`, `0x2d568`/`0x2d5f8`, `0x2e4b4`, `0x2cdb8` e vddcal
não foram executados. O resultado não amplia esse escopo. PSCI/PR #44 é uma
investigação independente e não fornece valores para este ensaio.

## Revisão dos arquivos recebidos

- [obs.gdb recebido](references/newtime-gate-obs-gdb-received.txt): a soma de
  IMAGE_BASE aos offsets está correta. O script usa continue, não possui o
  preflight, o orçamento de instruções e o hash de trilha do runner. Foi
  conservado como texto de referência, não utilizado para executar a cadeia.
- [Patch recebido](references/newtime-gate-image-base-received.patch):
  preservado para auditoria. Não foi aplicado a um runner inexistente.
- run_case.sh e compare.py originais não vieram nos anexos. Não afirmamos
  tê-los executado nem reproduzido o teste simulado de quatro casos citado
  no documento recebido. O comparador desta entrega tem código próprio,
  [compare_newtime_gate.py](../scripts/compare_newtime_gate.py).
- A proposta newtime-scope-proposal-hzc2.md citada no texto recebido não
  existe nesta main. Não foi inventado um documento anterior para substituí-la.

## Reprodução no ambiente com QEMU funcional

```sh
python3 scripts/trace_newtime_columns_qemu.py /caminho/sboot.bin \
  --observe-gate --observation-output-dir out > out-run.json
python3 scripts/compare_newtime_gate.py out > out-comparison.json
python3 -m unittest discover -s scripts -p test_newtime_gate_observation.py
python3 -m unittest discover -s scripts -p test_newtime_columns.py
```

O modo novo restaura os dados mutáveis baseados no arquivo antes de cada
caso, reaplicando os mesmos metadados relocados/ponteiros do runner. Heap,
pilha e destinos mantêm a preparação anterior. As capturas de entrada e
parada são leituras do debugger em regiões permitidas; não executam uma
instrução guest. Os dois arquivos de saída são criados sem sobrescrever.
O modo padrão conserva o formato anterior, sem snapshots extras.

A parada segue sendo produzida por **single-step e preflight**, não por
continue até um breakpoint. O rótulo `bp:gate_0x19774` é compatibilidade de
resultado com o escopo recebido. O motivo original também permanece em
`stop.reason=before_access_outside_lab_ram`.

O sentinela CALLBACK_RETURN pode ser reconhecido antes de executar código
fora da lista. A parada anterior no epílogo compartilhado continua ativa:
ela pode preceder esse retorno, portanto o modo não promete observar todo
RET da callback. Nessa condição não se declara retorno completo.

## Identidade, colocação e LR capturado

Sboot de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
QEMU **10.0.13**, pacote Debian `1:10.0.13+ds-0+deb13u1`. A receita de
lançamento completa consta em `gate_observation.launch_recipe` dos JSON,
com o caminho temporário de build substituído por `<BUILD>`.
Usa virt/gic-version=3/virtualization=off, CPU max, uma CPU, sem NIC/display/
monitor/serial e GDB stdio. A Image de laboratório é parada antes de sua
primeira instrução, antes da preparação e entrada do callback.

| IMAGE_BASE | CALLBACK_RETURN e LR de entrada, nas duas linhas | PC absoluto de parada |
|---|---|---|
| 0x40000000 | 0x40015000 | 0x40019774 |
| 0x40200000 | 0x40215000 | 0x40219774 |

O sentinela foi capturado de X30 após a preparação existente e antes da
primeira instrução do callback. Não é endereço do firmware ou retorno visto
no aparelho. É igual entre as linhas na mesma colocação; muda com a
colocação do laboratório. O LR na parada é outro valor (base+0x19768),
conservado separadamente. Não se deve substituir um pelo outro.

## Endereços observados

| Campo | Endereço | Bytes | Resultado nas quatro capturas |
|---|---|---:|---|
| ptr_31c30 | IMAGE_BASE+0x31c30 | 8 | ff repetido; igual à entrada |
| scratch_31f30 | IMAGE_BASE+0x31f30 | 108 | ff repetido; igual à entrada |
| ptr_col1_31758 | IMAGE_BASE+0x31758 | 8 | zero |
| count_col12_31698 | IMAGE_BASE+0x31698 | 1 | zero |
| ptr_col12_316a0 | IMAGE_BASE+0x316a0 | 8 | zero |
| result_col1_0207365c | literal absoluto 0x0207365c | 4 | não lido: not_in_lab_regions |

O literal AP não recebe IMAGE_BASE e não foi mapeado para a observação.
Recusamos inclusive a leitura pelo debugger fora das regiões de laboratório,
sem atribuir valor a um eventual dispositivo/flash existente nesse endereço
no mapa QEMU. Esse campo é indisponível, não zero nem igual entre os casos.
Os outros três campos informativos são comparados separadamente dos dois
principais; suas igualdades não provam uso físico dessas colunas.

## Comparação e predições anteriores

| Predição recebida | Resultado |
|---|---|
| Gate 0x19774 nos dois casos | confirmada nas duas colocações; X0=0x158609bc, antes do LDR |
| ptr_31c30 = ff×8 | confirmada; sem mudança da entrada |
| scratch_31f30 = zero×108 | **refutada**: ff×108 desde a entrada |
| Linhas 10 e 15 iguais | confirmada para os campos selecionados, por colocação; não para inputs/trilhas inteiros |

O arquivo exato já contém ff×108 em 0x31f30. A preparação fresca conserva
esses bytes; o snapshot de entrada os confirma. O rastreio registra **zero
escritas que sobreponham** ptr_31c30 ou scratch_31f30 até a parada, e a
captura final é igual à entrada. Portanto scratch não zero não demonstra
preenchimento pelo descritor NEWTIME. A interpretação causal sugerida no
texto recebido era forte demais sem esse controle inicial.
Esses ff descrevem a preparação baseada no arquivo neste laboratório, não
o estado após inicialização/BSS no telefone, que não foi observado.

Também não se pode concluir que um eventual ponteiro diferente prove sozinho
passagem por 0x25ef0: seria necessário localizar a escrita na trilha e
considerar aliases/outros produtores. Aqui não houve mudança dos campos.

As linhas 10/15 executaram **1355/1495 instruções**, respectivamente, em cada
colocação. As contagens e os quatro hashes de trilha são **idênticos** aos do
[ensaio contínuo anterior](references/newtime-columns-qemu-hzc2.json).
Adicionar os snapshots e restaurar os dados por caso não alterou a execução
do prefixo observado. Não se observaram retorno completo ou efeitos depois
do gate. A conclusão é **nenhuma alteração observada nesses campos nesse
prefixo permitido**, e não ausência global de relação entre as colunas.

## Evidências entregues e validação

- [line10__none.json](references/newtime-gate-observation/line10__none.json)
- [line15__none.json](references/newtime-gate-observation/line15__none.json)
- [Comparação](references/newtime-gate-observation/comparison.json)
- [Validação e hashes](references/newtime-gate-observation-validation-20261027.json)

Cada arquivo de linha contém as duas colocações, os snapshots inicial/final,
LR capturado, campos/endereço/tamanho, contagens de escritas, trilha com hash,
versão e receita QEMU. O comparador exige mesma proveniência e ponto de
parada; recusa identidades/colocações/larguras/bytes inconsistentes e não
compara campos quando o stop ou o retorno diferem. Uma comparação concluída
pode conter predição refutada: isso não é aprovação de todas as hipóteses.
O comparador não autentica a origem de um JSON fornecido.

Passaram dez testes novos de confinamento/proveniência/comparação e treze
regressões do preflight/decoder. Os fixtures de host não são execução no
telefone. O original recebido fica separado do documento revisto para que
as predições anteriores possam ser auditadas sem apagar o resultado negativo.
