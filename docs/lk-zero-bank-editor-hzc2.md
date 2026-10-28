# HZC2: banco de tamanho zero no editor FDT

Continuação de **2026-10-27 (Campo Grande)**, base `c2e41bb` após PR #42.
**O escritor do LK não descarta o tamanho zero. Com espaço suficiente no
FDT, seu editor cria o nó com reg de 12 bytes e tamanho zero.** A execução
isolada do código original também confirmou edições parciais por falta de
espaço e retorno zero que pode ocultar uma falha anterior de reg.

Isso resolve a semântica local da chamada de tamanho zero encontrada no
[cenário do bugreport](bugreport-boot-hzc2.md). Não é captura do FDT final
nem execução desse caminho no S21; as entradas do cenário continuam condicionais.

## Evidência fixada e reprodução

Sboot bruto de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo. O [extrato estático](references/lk-bank-editor-hzc2.json)
confere 366 palavras GNU e 67 destinos relativos com decoder independente,
oito grafos locais e seis strings. Chamadas ficam opacas nesses grafos;
o [ensaio QEMU](references/lk-bank-editor-qemu-hzc2.json) testa seus efeitos
em árvores sintéticas separadamente. [Validação](references/lk-bank-editor-validation-20261027.json).

```sh
python3 scripts/inspect_lk_bank_editor.py /caminho/sboot.bin
python3 scripts/emulate_lk_bank_editor_qemu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p test_lk_memory_banks.py
python3 -m unittest discover -s scripts -p test_lk_uh_ranges.py
python3 -m unittest discover -s scripts -p test_lk_payload_return.py
python3 -m unittest discover -s scripts -p test_lk_final_edges.py
```

## Caminho do escritor e erros não agregados

`0xf1570` preserva base em X19 e tamanho em W21. Executa as operações abaixo
sem testar os retornos das duas primeiras:

| Chamada | Argumentos nominalmente preparados | Implementação seguinte |
|---|---|---|
| 0xf15b8 → 0xf12c8 | raiz `/`, nome `memory@%lx` | verifica header, busca pai, tenta adicionar subnó em 0x11fce0 → 0x11fbb8 |
| 0xf1608 → 0xf13b0 | `/memory@%lx`, `reg`, `<base_hi base_lo size_lo>` | converte valores em células big-endian e chama 0x11fb48 |
| 0xf1634 → 0xf13b0 | mesmo caminho, `device_type`, `memory` | copia string incluindo NUL e chama 0x11fb48 |

O parser de células usa REV W0 e stores de quatro bytes; tamanho zero produz
uma terceira célula zero, sem teste especial. Para base 0xc0000000, o resultado
bem-sucedido observado na árvore sintética equivale a:

```dts
memory@c0000000 {
    device_type = "memory";
    reg = <0x0 0xc0000000 0x0>;
};
```

As rotinas de criação/propriedade reportam falhas locais, mas o escritor
continua. Seu epílogo não agrega status: **W0 conserva o retorno da última
edição de device_type**. Não há remoção local do nó nem rollback das
propriedades já escritas. O construtor também não testa W0 após 0xfaf50,
antes de atualizar seu cursor para o fim Harx.

Um nó já existente faz a tentativa de criação falhar, mas pode receber novos
reg/device_type nas etapas seguintes. Essa condição é diferente de uma
propriedade ou nó duplicado na estrutura serializada: o ensaio confirmou um
único nó atualizado, não duas definições sobrepostas.

## Execução original em árvores sintéticas

Foram executados o escritor, os helpers e a implementação FDT embutida no
HZC2, sem modificar seus bytes. O harness substitui **snprintf, strtoul e
printf diagnóstico** por operações de host limitadas aos formatos/tokens
usados aqui. Strings/memcpy/memset e as operações FDT selecionadas executam
seus bytes originais em RAM do QEMU. Não é execução integral do bootloader.

A Image de diagnóstico do laboratório serve somente para iniciar a CPU e é
interrompida antes de sua primeira instrução. Não se deve contar esse ensaio
como uma execução da sonda no aparelho. O FDT é criado no host com células
2/1 e não é obtido do telefone. Há limites de 64 paradas, 15 s por caso e
10 s de timeout de transporte; os dois limites de tempo são de host.

| Caso | Folga no blob | Retornos criar/reg/tipo | Resultado local |
|---|---:|---|---|
| Sem espaço | 0 | 1 / 1 / 1 | nenhum nó criado |
| Espaço só para nó | 32 | 0 / 1 / 1 | nó sem propriedades |
| Espaço para nó e reg | 64 | 0 / 0 / 1 | reg com tamanho zero; tipo ausente |
| Zero completo | 128 | 0 / 0 / 0 | nó com reg zero e device_type=memory |
| Atualizar nó existente | 128 | 1 / 0 / 0 | reg anterior substituído por zero; tipo atualizado |
| Falha de reg ocultada | 0, nó existente com tipo e sem reg | 1 / 1 / 0 | W0 final zero, mas reg continua ausente |
| Controle não zero | 128 | 0 / 0 / 0 | reg com tamanho 0x1000 |
| Metade alta do tamanho | 128 | 0 / 0 / 0 | argumento 0x100000000 vira zero em W21 |

Os tamanhos de folga pertencem às fixtures específicas, não são um requisito
universal do editor. Retorno 1 é a normalização do wrapper nos erros exercidos;
não se atribui esse número a todo erro libfdt ou a falhas de header não testadas.

**16/16 casos passaram:** oito condições em cada delta de laboratório
0x40000000 e 0x40200000. Foram conferidos status em cada retorno, propriedades
exatas, ausência de nós extras, células da raiz, SP/X19..X29, sentinelas do
FDT/pilha e preservação de todos os segmentos originais carregados. Os hashes
dos blobs resultantes são iguais entre as duas posições para o mesmo caso.
As substituições envenenam registradores voláteis; seus efeitos não devem ser
confundidos com a execução das implementações originais desses três helpers.

## Efeito no percurso de intervalos uH

O [percurso LK já delimitado](lk-uh-range-registration.md) seleciona o prefixo
memory e lê a primeira tupla reg, sem descartar tamanho zero. O modelo desse
percurso, aplicado aos bytes realmente produzidos no QEMU, obtém base
0xc0000000/tamanho zero. O guard base/tamanho não zero do handler uH falharia.
Isso é cruzamento de execução local com modelo estático; o walker/HVC/uH não
foram executados neste ensaio e sua aceitação global não foi observada.

Nó sem reg é ignorado nesse percurso. Nó com reg e sem device_type ainda
corresponde ao filtro: aquele código não consulta device_type. Também não
se pode usar o W0 final do escritor como certificado de que todos os bancos
foram editados com sucesso.

## Conclusão e fronteira restante

O tamanho zero não é filtrado pelo escritor nem recusado por sua rotina FDT
por esse motivo: ele é serializado quando as edições têm sucesso. Esse nó
não descreve bytes de RAM pelo seu reg. Isso não demonstra erro no boot
stock ou disponibilidade de memória para um payload.

Continuam abertos os bytes do FDT após todas as edições, a admissão dos bancos
pelo consumidor e o estado da lista uH. A próxima análise deve acompanhar as
edições posteriores e os consumidores, sem promover a árvore sintética a mapa
físico. Nenhuma coleta, Odin ou alteração no telefone é necessária nesta etapa.

## Continuação de 27/10 — método PSCI após a base

O [editor posterior do LK](lk-psci-final-edit-hzc2.md) pode trocar
/psci/method de smc para hvc sob o flag Harx. O bugreport contém a mensagem
do ramo após setprop não negativo. Vinte e quatro casos QEMU conferem
essa rotina; não são captura do FDT final ou execução de serviço PSCI.
A main de uma CPU permanece sem sondagens SMC/HVC.
