# HZC2: retorno completo, cache e resposta publicada

Análise estática em 2026-10-29, base `5ec3ea2` (merge da PR #50).
Complementa [FVP](newtime-fvp-effective-hzc2.md) e
[receptor DVFS](newtime-dvfs-receiver-hzc2.md), sem substituir a investigação DMC.
PCs abaixo são offsets do sboot; dados são endereços core nominais.
Firmware 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.

## Três resultados distintos

No caminho comando6/domínio0/canal1, seja R o resultado u32 do relay:

| Consumidor | Campo preservado | Evidência |
|---|---|---|
| Cache FVP | R inteiro; só escreve se R=0 e índice signed>=0 | 3f120, 3f130, 3f132/134 |
| Retorno do callback FVP | R inteiro | helper3f144; caller3f2d4 guarda R5; epílogo3f202 devolve R5 |
| Palavra construída da resposta | header alto OR low16(R) | 3f2d0/2d8; 3f1de/1e0 |
| Palavra publicada | header alto, sob estabilidade da fila | publicador3877a/3877c, auditado na ponte do comando6 |

Logging/publicação retornando normalmente e preservando os registradores
carregados são condições. O retorno de publicação em R0 não substitui o
resultado guardado em R5 no epílogo selecionado. A [continuação do dispatcher](newtime-dispatch-completion-hzc2.md) agora
rastreia o logging e o avanço local após esse retorno; políticas externas
a essa janela permanecem abertas.

Exemplo sintético particularmente discriminante: R=0x00010000. O helper
não atualiza cache, o callback devolve65536, mas low16(R)=0. Com header alto
zero, tanto a palavra construída quanto a publicada são zero. Para R=10,
a construída tem10 e só a publicação remove esses bits. Isso distingue
truncamento na construção de projeção posterior; não demonstra esses erros
no dispositivo nem define códigos de erro do plugin.

## Estado após falha e nova invocação

A seleção FVP já escreve pedido/efetivo antes do relay. Sob preservação dos
campos pelos callees, um retorno não zero deixa o cache anterior, sem desfazer
as stores locais. A igualdade do pedido repetido com o estado efetivo não
suprime a seleção do helper no caminho delimitado.

Fixture: estado antigo200, pedido300, concorrentes0, cap desabilitado.
A primeira invocação seleciona300; um resultado0xffffffff impede a store
no cache. Uma segunda invocação explícita do mesmo pedido, com estado
preservado300, volta a alcançar o helper e não reescreve o indicador de
direção por igualdade. **Não há prova de retry automático**, nem de que
hardware, filas, interrupções e outros escritores preservem esse cenário.

Retorno zero pode gravar no cache o valor relido do frame, inclusive alterado
pelo destinatário. Esse cache não é confirmação física. Não se conclui rollback
global, sucesso de DMC ou resolução do chamador do slot47.

## Reprodução

- [Extrator](../scripts/inspect_newtime_return_planes_hzc2.py): valida imagem e reutiliza a conferência GNU do FVP; exige14 operandos adicionais e exporta os witnesses selecionados.
- [Evidência](references/newtime-return-planes-hzc2.json): seis cenários, PCs/bytes e condições.
- [Nove testes](../scripts/test_newtime_return_planes.py): pequeno decoder de palavras Thumb cruas para separação dos retornos, clobber de R0, argumento alterado, índice signed e duas invocações pelo interpretador existente da seleção.

```sh
python3 scripts/inspect_newtime_return_planes_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime_return_planes.py'
```

Interpretação limitada no host com chamadas opacas; sem execução Samsung,
sem ensaio físico e sem ampliar o escopo QEMU.
