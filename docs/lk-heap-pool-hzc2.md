# LK HZC2: pool nominal que abastece o heap UFS

A origem dos buffers deixou de parar no wrapper de malloc. O código liga o
heap genérico ao alocador de páginas e a um pool nominal de **3.043 páginas
(0xbe3000 bytes), `[0xe8c1d000,0xe9800000)`**. O alocador original também
foi executado em QEMU: um cenário UFS completo passou e um cenário de
esgotamento retornou erro mantendo o ponteiro global do host publicado.

Essa é uma conclusão sobre os bytes e os ensaios fornecidos. O pool pertence
à infraestrutura de memória do LK; não é uma região livre para carregar a
sonda. Tradução física/DMA, atributos e estado real continuam sem aquisição.

Análise de 30/10/2026, Campo Grande, base main `45f4821` após PR #68.
Sboot HZC2: 4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs abaixo são offsets de arquivo. O delta nominal VA−arquivo é
`0xe7f14000`; ele não foi medido no aparelho.

## Pool e ordem de inicialização

O binding em `0x18d8e8` prepara argumentos para o construtor `0x18d808`:

| Argumento | Valor recuperado | Papel local |
|---|---|---|
| X0 | relativo `0xd07910` | Contexto do pool |
| X1 | string `main`, arquivo `0x25f1c8` | Nome |
| X2 | relativo `0xd09000` | Base nominal `0xe8c1d000` |
| X3 | `0xe9800000 − X2` | Extensão até o limite literal |
| X4 | relativo `0xd06110` | Bitmap externo |
| X5 | 6144 | Capacidade fornecida para o bitmap |

Com o delta nominal, a base e o fim são alinhados a 4096 e a extensão
contém 3043 páginas. O construtor usa **um byte por página**: esse número
cabe na capacidade externa fornecida, sem precisar retirar o bitmap do
próprio pool no ramo selecionado. Publica base, tamanho, quantidade e
ponteiro do bitmap nos campos +80/+88/+64/+72 do contexto.

O registro de 24 bytes em `0x29b190` tem nível `0x1ffff`, flags1, função
`0x18d8e8` e nome `novm`. A preparação em `0xfa990–0xfa99c` fornece flags1
à faixa `[0x10000,0x1ffff]` do dispatcher `0xfa7b0`. O init do heap é
chamado depois, em `0xfa9c8 → 0x18fd30`. Isso estabelece a ordem nominal
nesse percurso, sob elegibilidade, preservação dos registros e retorno
dos helpers; não prova que o aparelho percorreu esse estado.

O nome `novm` não foi usado como prova de MMU desligada. Também não se
converte a faixa nominal em identidade entre ponteiros e endereços físicos.

## Do pool ao heap e aos buffers

A cadeia delimitada é:

1. `0x18fd30 → 0x18fef8 → 0x18da28` pede a semente do heap.
2. Havendo sobra cacheada em contexto+96/+104, o helper a devolve e zera
   os dois campos. No outro ramo pede uma página por `0x18d9f0` e fornece
   tamanho4096 ao chamador.
3. `0x18d9f0 → 0x18d918` procura uma sequência de bytes zero no bitmap,
   marca os selecionados com1 e retorna `base + índice×4096`. O flag bit0
   do pedido precisa estar ligado; os caminhos selecionados passam `−1`.
4. `0x20c410` inicializa o contexto do heap relativo `0xd089b8`, sua lista
   e o bloco inicial. O alocador `0x20c098` e o inseridor/coalescedor
   `0x20bf58` usam o mesmo contexto.
5. Na falta de bloco, o heap arredonda a carga para páginas e pede mais
   por `0x18fef0 → 0x18d9f0`. Insere/coalesce o resultado e tenta a lista
   novamente uma vez; falha do provedor registra diagnóstico e retorna0.
6. Os [wrappers e slots UFS](lk-ufs-host-memory-hzc2.md) usam esse heap.

O retorno para o usuário tem um cabeçalho de dois u64 em ponteiro−16:
ponteiro do bloco original e tamanho debitado. A carga normal inclui16
bytes de cabeçalho, mínimo24 e arredondamento a8. Alinhamentos não zero
precisam ser potência de dois; os menores que16 são promovidos a16.
Alinhamento aumenta a reserva e arredonda o ponteiro do usuário.

Por exemplo, pedido8192/alinhamento4096 solicita inicialmente12304 bytes
de bloco; pedido64/4096 solicita4176. Um resto pequeno pode fazer debitar
o bloco inteiro. São regras de heap, sem solicitação de um handle DMA.
O modelo conserva wrap A64 nas somas; não certifica pedidos arbitrários
nem a extensão de memória resultante.

Isso esclarece a [programação low32 das bases](lk-ufs-host-memory-hzc2.md):
a faixa nominal do provedor cabe abaixo de4GiB. A perda de bits de um
ponteiro hipotético alto continua aritmeticamente correta, mas a análise
não encontrou aqui uma alocação real acima desse limite. Estado corrompido,
outros escritores/usuários, cache e tradução para o dispositivo continuam
fora dessa conclusão.

## Ensaio original em QEMU

`emulate_lk_heap_qemu.py` executa os corpos originais do construtor do pool,
alocador de páginas, semente, heap, wrappers e alocador UFS. O binding com
endereços nominais, dispatcher e startup Samsung não são executados.
São fornecidos contextos zerados, lista de frees diferidos vazia e um
pool pequeno em RAM da VM. Mutexes e memset limitado ao pool/bitmap são
substituições do debugger; printf apenas conta diagnósticos.

Foram **28 casos** em duas posições do código (`+0x40000000` e
`+0x40200000`): 24 pedidos aritméticos/alinhamentos e quatro inicializações
UFS. Incluem alinhamento inválido, falta de capacidade, soma com wrap e
sucesso completo. Nos casos fornecidos, guardas e ABI foram conservadas,
os segmentos originais ficaram idênticos e as duas posições concordaram.

| Resultado UFS fornecido | Pool32 páginas | Pool4 páginas |
|---|---|---|
| W0 | `0` | `0xffffffff` (−1) |
| Host global | `0x41000010` | `0x41000010` |
| Metadados host+8112 | `0x41002010` | `0x41002010` |
| Comando host+144 | `0x41003000` | `0` |
| Transferência host+152 | `0x41006000` | `0` |
| Tarefa host+160 | `0x41007000` | `0` |
| Páginas marcadas | 9 | 3 |

Esses endereços são da VM. O caso de falta de memória confirma em execução
isolada que **host global não nulo não significa host pronto**: os buffers
não foram criados e o helper retorna erro, mas host/metadados continuam
publicados. Não se infere um defeito explorável, recuperação transitiva ou
um estado que tenha ocorrido no telefone.

## Verificação e próxima fronteira

O extrator exige tamanho/SHA antes de GNU e confere562 palavras,105
destinos,111 operandos, quatro literais, o registro init e15 grafos.
Os17 testes de host cobrem arredondamento/wrap, bindings, capacidade do
bitmap, mutações e recusas. Os19 testes UFS host e21 de conclusão passam.
O getter de configuração `0x147ea8` também foi reduzido a um load u32 de
relativo `0xcd31c8`; origem e valor desse campo permanecem em aberto.

```sh
python3 scripts/test_lk_heap.py -v
python3 scripts/inspect_lk_heap.py /private/path/sboot.bin > /tmp/lk-heap.json
cmp /tmp/lk-heap.json docs/references/lk-heap-hzc2.json
python3 scripts/emulate_lk_heap_qemu.py /private/path/sboot.bin > /tmp/lk-heap-qemu.json
cmp /tmp/lk-heap-qemu.json docs/references/lk-heap-qemu-hzc2.json
python3 scripts/validate_baseline.py --output-dir build/baseline-lk-heap
```

[Relatório estático](references/lk-heap-hzc2.json),
[ensaio QEMU](references/lk-heap-qemu-hzc2.json) e
[validação](references/lk-heap-validation-20261030.json) conservam os hashes.
Próximo: atributos/tradução do pool e produtor de `0xcd31c8`, além dos
gates RPMB. O resultado fecha a origem nominal da memória; não fecha os
contratos físicos de carga e captura do diagnóstico.

A [construção de tradução/atributos](lk-pool-mmu-hzc2.md) agora liga o pool ao mapper EL1/4KiB, com seis casos originais QEMU. Identidade de estágio1 e atributos cacheáveis foram delimitados; granule herdado e tradução/coerência DMA permanecem abertos.
