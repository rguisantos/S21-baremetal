# FlopKernel: referência ACPM SRAM, mailbox e ECT

O cruzamento independente usou **oito arquivos** do FlopKernel fixados em
`4553117a5014928dff55595f46627e0d77bcf133`, conferidos por tamanho,
SHA-256 e blob Git. O [manifesto](references/flop-acpm-source-reference.json)
permite repetir a leitura. Não reproduz a rodada externa de16 arquivos
cujos artefatos não foram fornecidos.

## ABI SRAM medida com o compilador do host

O probe extrai apenas declarações com campos de largura fixa, seleciona o
ramo de representação u32 usado pelo kernel e mede `sizeof`/`offsetof`.
Não compila funções ou scripts do repositório externo.

| Declaração/campo | Resultado C | Relação com o sboot |
|---|---:|---|
| `struct plugin` | 48 bytes | IDs7/9 em `0x3b2a0` e `0x3b300` |
| `struct channel_info` | 52 bytes | Campos embutidos no descritor de canal |
| `struct ipc_channel` | 72 bytes | Canal3 em `0x3b3c0 + 3×72 = 0x3b498` |
| `ipc_channel.type` | +12 | Valor2 no canal3 |
| `ch.rx_base` | +24 | Local`0xa5900100` |
| `ch.tx_base` | +48 | Local`0xa5900108` |
| `ch.q_len / q_elem_size` | +52/+56 | Valores1/16 |
| `ch.mbox_addr` | +64 | Local`0xa5900000` |

As fontes são
[`common.h`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/soc/samsung/acpm/fw_header/common.h) e
[`framework.h`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/soc/samsung/acpm/fw_header/framework.h).
O stride48 refere-se ao registro de plugin; não certifica por si o layout
de outros descritores que também tenham48 bytes.

## Direção dos buffers e campainha

Em [`channel_init`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/soc/samsung/acpm/acpm_ipc.c#L835),
TX do AP usa `ch.rx_base` do firmware, enquanto RX do AP usa `ch.tx_base`.
Essa inversão de perspectiva importa para interpretar o canal3. O
[produtor do magic](newtime-dmc-magic-hzc2.md) usa a célula candidata
correspondente a RX do firmware+12.

O [`header IPC`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/soc/samsung/acpm/acpm_ipc.h)
define INTGR0=8, INTSR1=0x28 e INTCR1=0x20. O driver publica a campainha
como `(1 << id) << 16`; para canal3 isso é `0x80000`, compatível com a
store A64 em `0x369ac`. Compatibilidade de offsets não mede entrega,
limpeza de pendência ou identidade física dos aliases AP/local.

## Namespace ECT

O [`header ECT`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/include/soc/samsung/ect_parser.h)
e o [parser](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/soc/samsung/ect_parser.c)
contêm a assinatura PARA e os nomes GEN, ASV, NEWTIME, THERMAL, PIDTM,
DVFS, PLL, MINLOCK e MARGIN presentes no diretório extraído do sboot.
Isso confirma namespace e formato geral, sem provar a mesma versão,
execução ou interpretação de todos os campos.

A busca textual pelo magic é limitada aos oito arquivos listados. Ausência
nesses arquivos não prova ausência em todo o kernel ou em firmware externo.

## Reprodução e limites

```sh
python3 scripts/inspect_flop_acpm_reference.py /path/to/pinned-sources /private/path/sboot.bin > /tmp/flop-acpm.json
cmp /tmp/flop-acpm.json docs/references/flop-acpm-reference.json
python3 -m unittest discover -s scripts -p 'test_flop*.py'
```

O [relatório](references/flop-acpm-reference.json) inclui o resultado do
probe C, os campos binários e a orientação dos buffers. Há14 testes novos
de gramática, ABI, hashes, recusa antes do compilador e limites das
alegações. O kernel custom continua distinto do firmware HZC2; nenhum
build de kernel, driver ou firmware foi executado.
