# HZC2: dois switches BL2 com entradas relativas

Análise **estática, 2026-10-28 (Campo Grande)**, base `e9bcc87` após PR #48.
Os BRs `0x1ada4` e `0x2f928` agora têm conjuntos finitos de destinos sob
preservação das tabelas iniciais. **Não foi encontrado chamador do slot 47
nem reconstruída a origem do X0 recebido por `0x2d364`.**

## Arrays de dados e bases de código

Mesmo sboot HZC2 de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs e tabelas abaixo são offsets de arquivo. O delta nominal BL2 continua
`0x020ea000`; não houve execução Samsung, MMIO/SMC ou ampliação QEMU.

| BR | Array de entradas | Quantidade/largura | Base de código ADR | Default unsigned |
|---|---|---|---|---|
| `0x1ada4` | `[0x30108,0x30130)` | 20 × u16 LE | `0x1ada8` | W0 > 19 → `0x1aff0` |
| `0x2f928` | `[0x30130,0x30135)` | 5 × u8 | `0x2f92c` | W0 > 4 → `0x2f940` |

`0x1ada8` e `0x2f92c` são **bases de código**, não arrays de ponteiros.
A carga vem do endereço formado por ADRP+ADD, antes do ADR. O destino é:

`base_de_codigo + 4 * sign_extend(entrada, 16 ou 8)`.

O primeiro caminho testa W0 carregado de `[X29+156]` em `0x1ad7c`, e
recarrega o mesmo campo em W1 em `0x1ad90`. Não há chamada nem store
entre as duas cargas; a ligação exige frame estável e ausência de alias
externo que o modifique. `LDRH` usa `UXTW #1`; o ADD seguinte usa `SXTH #2`.
O segundo testa o W0 recebido, carrega com `LDRB`/UXTW e aplica `SXTB #2`.
Os defaults incluem o padrão W `0xffffffff`; não são comparações signed.

## Destinos iniciais enumerados

| Índices do primeiro switch | Destino |
|---|---|
| 0 | `0x1ada8` |
| 1, 12, 17, 18 | `0x1add4` |
| 19 | `0x1ae0c` |
| 2 | `0x1ae30` |
| 3 | `0x1ae6c` |
| 4 | `0x1aea8` |
| 6 | `0x1aecc` |
| 5, 16 | `0x1aef0` |
| 11 | `0x1af28` |
| 7, 8, 13, 14, 15 | `0x1af4c` |
| 9 | `0x1af84` |
| 10 | `0x1afbc` |

| Índices do segundo switch | Destino |
|---|---|
| 0 | `0x2fa54` |
| 1 | `0x2f92c` |
| 2, 3 | `0x2f944` |
| 4 | `0x2f9ec` |

Há **12 e quatro destinos distintos**, respectivamente. Nenhuma das 25
entradas aponta para `[0x2d364,0x2d3bc)`. Isso resolve estes dois saltos
como enumerações condicionais; não demonstra preservação das tabelas,
execução de um índice ou ausência global de chamador.

## Fronteiras após os destinos

O grafo sintático local percorre ambos os ramos condicionais sem decidir
viabilidade. Calls são opacas; continuar pelo PC seguinte pressupõe retorno
normal. Nenhum registrador ou resultado de callee é inventado.

- Primeiro switch: 146 PCs na janela `[0x1ada8,0x1aff0)`, uma chamada
  `0x1adcc → 0x1a668` e continuação comum em `0x1aff0`. O callee e a
  continuação ficam fora deste grafo; portanto não são excluídos como
  caminhos indiretos posteriores até outro código.
- Segundo switch: 91 PCs em `[0x2f92c,0x2fa98)`, com RETs em `0x2f940`,
  `0x2f9e8`, `0x2fa50` e `0x2fa94`. Há um BLR em `0x2fa78`, no caso 0,
  condicionado ao bit 12 da leitura de AP`0x02073698` estar ligado.

Nesse BLR, ADRP `0x2fa64` e LDR `0x2fa74` selecionam nominalmente a
célula `0x31538`, **slot 38** de `0x31408`. O valor inicial
`0x021172e4` corresponde a `0x2d2e4`; `0x2fa68` passa o W4 recebido em
W0. Não é o slot 47. O valor efetivo da célula, o bit de gate e os efeitos
do callback não foram observados. Não se explorou o corpo do callee.

## Reprodução e procedência

```sh
python3 scripts/inspect_newtime_jump_tables_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

O [extrator limitado](../scripts/inspect_newtime_jump_tables_hzc2.py)
exige tamanho/hash exatos. Deriva limites, arrays e anchors das instruções;
confere no GNU **256 palavras, 26 alvos relativos e 26 operandos**.
O [JSON](references/newtime-jump-tables-hzc2.json) preserva as 25 entradas,
hashes, grafos locais e testemunhas. Os testes incluem sinal, escala,
endianness, guard unsigned, ADR/ADRP, fronteiras e chamadas opacas.
[Validação](references/newtime-jump-tables-validation-20261028.json).

O material externo v5 recebido motivou esta continuação: seus 137 testes
passaram com o firmware presente e seu JSON foi reproduzido, exceto pelo
caminho absoluto de entrada. ADR e shifts W corrigidos foram conferidos.
Esse resultado não valida uma ISA completa, todos os rótulos de seu CFG
ou as 540 candidaturas condicionais como execuções. O extrator desta entrega
usa as formas e janelas declaradas acima; não incorpora o motor externo.
Os hashes dos três anexos constam na validação, sem redistribuir o firmware.

A [continuação 0x1aff0](newtime-common-continuation-hzc2.md) foi seguida
separadamente: 227 PCs, sete BLs, campos packed e escritas condicionais.
A [folha 0x1a668](newtime-mif-bins-hzc2.md) tem dois bins e três stores
globais nominais delimitados; `0x1a804` e bases/aliases seguem abertos.
O despacho real do slot 47 e X0
continuam pendentes; a contagem de 593 do JSON externo não foi reescrita
como uma nova contagem global deste extrator.
