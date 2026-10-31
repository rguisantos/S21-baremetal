# LK HZC2: origem do host UFS, buffers e endereços DMA

A [sequência de conclusão UFS](lk-ufs-completion-hzc2.md) agora está ligada
ao alocador do host, aos buffers e às tabelas locais de configuração. O
slot publicado pelo alocador é o mesmo usado pela inicialização e pelo
gateway. As verificações de alinhamento e os endereços programados foram
separados da prova ainda ausente de identidade CPU/DMA e coerência.

Base main `e4d6ba00cdeed08164cb38a61c855925567bcae1`, após PR #67.
`sboot.bin` HZC2 tem 4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; globais relativos usam delta nominal
VA−arquivo `0xe7f14000`. Nenhum firmware, MMIO, DMA, SMC ou pedido de
armazenamento foi executado nesta etapa.

## Publicação do host e alocações

`0x10ec98` zera o índice relativo `0x8a7710`, solicita 8176 bytes por
`0x18fd50` e publica o retorno no slot relativo `0x8a7718` **antes** do
teste de NULL. O inicializador `0x10e7c8` lê esse mesmo slot; o gateway
`0x10e758` seleciona pela tabela iniciada nele. As saídas selecionadas do
inicializador também zeram o índice. Isso liga nominalmente o slot0;
não é um censo de todos os escritores/aliases nem uma observação ativa.

Após zerar a estrutura do host, o alocador prepara:

| Uso nominal | Bytes solicitados | Argumento de alinhamento | Slot do host |
|---|---:|---:|---:|
| Metadados auxiliares | 32 | Nenhum nesse wrapper | +8112 |
| Descritor de comando | 8192 | 4096 | +144 |
| Descritores de transferência | 64 | 4096 | +152 |
| Descritores de gerenciamento de tarefa | 160 | 4096 | +160 |

Os três pedidos alinhados usam `0x18fd90`. Seus retornos são gravados nos
slots, testados contra NULL e conferidos com máscara `0xfff`. O bloco de
objetos SCSI de 3072 bytes é solicitado depois e publicado em relativo
`0x8a7708`. Mais tarde, a inicialização solicita outro bloco de 8192 bytes
e o publica em relativo `0x8a73f0`, sem testar esse retorno antes da store
local; não se atribui a esse scratch o papel dos buffers já alocados.

Falhas selecionam retorno local−1. O corpo não desfaz explicitamente as
publicações anteriores nem libera esses buffers antes desse retorno;
isso não prova como o chamador ou efeitos transitivos recuperariam o
estado. Não se trata um ponteiro global não nulo como host pronto.

Os wrappers de alocação seguem para `0x20c098`: o simples fornece
alinhamento0; o alinhado repassa tamanho em X0 e low32 do alinhamento em
W1. Há um possível helper opaco `0x18fbf0` antes disso. O backend do
alocador, a procedência física e os atributos de cache não foram
certificados. A forma de chamada não é um contrato de DMA equivalente
à API Linux.

## Tabelas de configuração

O inicializador escolhe a tabela em `0x303198` ou `0x3038d8` mediante
consultas repetidas ao helper `0x147ea8`. Não se presume estabilidade
entre essas consultas nem se atribui significado de revisão de silício
ao retorno sem analisar seu produtor.

| Offset na tabela | Copiado para host | Valor primário | Valor alternativo |
|---:|---:|---|---|
| 0 | +24 | `0x13100000` | `0x13100000` |
| 8 | +32 | `0x13101100` | `0x13101100` |
| 16 | +40 | `0x132a0000` | `0x132a0000` |
| 24 | +48 | `0x13180000` | `0x13180000` |
| 32 | +64 | `0x13104000` | `0x13104000` |
| 40 | Outros acessos locais | `0x15860728` | `0x15860728` |
| 48 | Outros acessos locais | `0x13020700` | `0x11020700` |
| 56 | Outros acessos locais | `0x13040020` | `0x11040040` |

As cinco cópias de campo são verificadas mecanicamente. Os endereços HCI
e vendor são coerentes com a [referência de fontes Exynos](flop-ufs-dma-reference.md),
mas a presença dos valores não mede energia, clocks, pinmux, acesso
permitido ou configuração ativa. Helpers de reset/link/dispositivo e
acessos MMIO posteriores continuam condicionais.

## Projeção de endereço e limite de DMA

A inicialização zera os descritores e programa as bases de transferência
e tarefa com a parte baixa de ponteiros em registradores de 32 bits,
gravando zero nos registradores altos. Também copia somente os quatro
bytes baixos do ponteiro do descritor de comando para a base no descritor
de transferência; o dword alto permanece zerado no caminho selecionado.

Assim, os bits de `0x0000000100001000` seriam programados como base
`0x0000000000001000` nesse resumo sintético. Não houve aquisição de um
ponteiro real acima de 4 GiB. Mesmo quando a base cabe em 32 bits, isso
não certifica o intervalo inteiro, a tradução para endereço de barramento
ou a posse do buffer.

Os alinhamentos, stores e barreiras locais não demonstram coerência
CPU/dispositivo ou identidade entre endereço virtual e DMA. O
[cruzamento com FlopKernel](flop-ufs-dma-reference.md) mostra justamente
quais contratos o driver Linux solicita e quais não podem ser importados
automaticamente para o LK.

## Verificação e continuidade

`inspect_lk_ufs_host.py` exige tamanho/SHA antes de GNU e confere 432
palavras, 93 destinos relativos, 112 operandos, sete literais e cinco
grafos. Liga publicação/consumo do host, índice, argumentos/slots das
alocações, cópias das tabelas e largura dos stores de bases. Grafos
mantêm retornos condicionais de chamadas opacas, sem avaliar execução
real, aliases ou preservação de estado.

```sh
python3 scripts/test_lk_ufs_host.py -v
python3 scripts/inspect_lk_ufs_host.py /private/path/sboot.bin > /tmp/lk-ufs-host.json
cmp /tmp/lk-ufs-host.json docs/references/lk-ufs-host-hzc2.json
python3 scripts/test_lk_ufs_completion.py
python3 scripts/test_lk_rpmb_transport.py
python3 scripts/validate_baseline.py --output-dir build/baseline-ufs-host
```

Os 19 testes novos exercitam recusas, mutações de registradores/slots,
bounds/endian das tabelas e projeção low32 sem declarar DMA válido.
Evidências: [relatório](references/lk-ufs-host-hzc2.json) e
[validação](references/lk-ufs-host-validation-20261030.json).

Próximo: backend de alocação/atributos de memória, helpers de escolha da
configuração e origem dos gates RPMB. A implementação segura, posse dos
buffers, frescura física e persistência permanecem abertas.

Continuação: o [pool do heap](lk-heap-pool-hzc2.md) foi ligado nominalmente a 3043 páginas abaixo de4GiB, com ensaios do código original em QEMU. A falha UFS preservando host parcial foi reproduzida; identidade DMA e estado físico continuam abertos.
