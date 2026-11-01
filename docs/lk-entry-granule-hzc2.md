# LK HZC2: entrada por EL e granule herdado

O helper original `0xf9b4c` foi executado em QEMU e preservou o TCR_EL1
fornecido, inclusive ao descer de EL2h para EL1h. O getter original
`0x189e50`, com leitura real do registrador por `0x189480`, retornou
4096, 65536 ou 16384 conforme TG0. **Entrar em EL1 não seleciona4KiB.**
O perfil de4KiB da [construção do pool](lk-pool-mmu-hzc2.md) continua
condicionado ao valor herdado; o novo TCR só é escrito depois da construção.

Análise de31/10/2026, Campo Grande, base main `a3f60b0`, após PR #71.
Imagem sboot:4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Os PCs abaixo são offsets no arquivo, não endereços físicos adquiridos.

## Entrada: resultado ensaiado e distinção de modo

A ligação estática `0xec000 → 0xf9b4c` já estava registrada em
[estágios do sboot](sboot-layout-hzc2.md). Esta rodada acrescenta execução
dos bytes originais, dependência do TCR, efeitos em X0 e o controle EL1t.

| Entrada fornecida | Saída observada no helper | X0 | TCR_EL1 / SCTLR_EL1 |
|---|---|---|---|
| EL1h | EL1h, retorno imediato | Preservado | Preservados |
| EL1t | EL1t, retorno imediato | Preservado | Preservados |
| EL2h | EL1h via ERET | SP de entrada | Preservados |

Em EL1, o teste de CurrentEL retorna antes de configurar SPSR ou SP_EL1.
Portanto, a descrição “preserva EL1 ou programa EL1h” deve conservar essa
distinção: EL1t não é convertido em EL1h pelo helper.

No caminho EL2, SPSR_EL2 recebe `0x3c5`, ELR_EL2 aponta para o RET local
`0xf9bbc`, CPTR_EL2 recebe `0x33ff`, HCR_EL2 recebe `0x80000000` e
CPACR_EL1 recebe `0x300000`. A instrução `0xf9bac` move SP para X0;
`0xf9bb0` escreve esse valor em SP_EL1. X1–X3 foram preservados. Isso
impede assumir preservação universal do argumento X0 nesse helper; não
identifica o argumento de entrada como FDT nem o handoff final do kernel.

O ramo superior consulta SCR_EL3, pede RW e programa SPSR_EL3/ELR_EL3.
Foi conferido estaticamente e **não foi executado**. O ensaio não estabelece
estado seguro/não seguro, política de traps ou comportamento completo do boot.

## Getter e fronteiras de erro

O argumento W0 deve ser1; a rotina consulta TCR_EL1 por `0x189480` e extrai
os bits15:14. A ordem dos encodings não é uma ordem crescente de tamanho.

| TG0 | Resultado original | Caminho |
|---|---:|---|
| 0 | 4096 | `0x189e98` |
| 1 | 65536 | `0x189ed0` |
| 2 | 16384 | `0x189e84` |
| 3 | Sem tamanho aceito | chamada `0x189ec8 → 0x18f8a8` |
| Argumento EL diferente de1 | Sem tamanho aceito | chamada `0x189f00 → 0x18f8a8` |

Nos controles inválidos, o debugger para na entrada do helper de assert.
Seu corpo não é executado, e não se presume que retorne, aborte ou produza
um tamanho. O caso TG0=3 foi fornecido com MMU desligada apenas como
controle do ramo reservado; não certifica essa configuração em hardware.

Os chamadores `0x18a244`, `0x18a270`, `0x189f94` e `0x189fa4` consultam
o getter durante a construção. O instalador posterior `0x18a1d0..0x18a1dc`
monta `0x11b51c351c` e chama o writer `0x1894a0`. O TG0 dessa constante
não retroage sobre as consultas anteriores.

## Censo limitado de escritores

Foram examinadas todas as posições alinhadas a4 bytes em `[0,0x400000)`
para o opcode exato `MSR TCR_EL1,Xn`, mantendo os cinco bits de registrador.
Há dois candidatos, ambos confirmados por disassembly nos seus trechos:

| Offset | Fonte | Papel delimitado |
|---|---|---|
| `0xedf5c` | X4 | Restauração: LDP em `0xedf40` lê o campo do contexto em +280 |
| `0x1894a0` | X0 | Writer genérico chamado pelo instalador posterior |

A captura correspondente lê TCR_EL1 em `0xedee8` e armazena X4 em +280
pelo STP `0xedf08`. Isso delimita um formato de contexto; não fornece
o valor salvo nem prova a ordem de uma restauração em relação ao startup.

O censo não é uma prova de unicidade global. Não recupera todas as
fronteiras de instrução nem cobre outras imagens, código copiado,
agentes externos ou a execução efetiva da restauração. A origem e o valor
do TCR herdado do aparelho permanecem abertos.

## Reprodução e validação

O extrator confere131 palavras GNU,17 destinos relativos,54 operandos
selecionados e11 grafos locais, além do censo em todo o arquivo. Aceita
somente o tamanho/hash fixados. Os14 testes de host incluem encodings,
limites do censo e recusa antes de chamar GNU ou iniciar QEMU.

O ensaio nativo usa duas posições de código em RAM do QEMU, deltas
`0x3ff14000` e `0x41f14000`, três modos iniciais e quatro valores TG0:

- 24 execuções do helper de entrada, com TCR e SCTLR preservados.
- 48 chamadas do getter:18 retornos de tamanho e30 paradas no assert.
- Leitura original de TCR, sem substituir o getter ou a transição de EL.
- Código original intacto, guardas de pilha e ABI dos retornos conferidas.

O fixture `r8/tests/lk_entry_state.S` fornece estado e lê registradores;
é código de laboratório separado dos segmentos Samsung. O TCR é variado
com SCTLR_EL1.M=0, a pilha é fornecida e nenhum mapa é instalado. O ensaio
não executa o startup completo, serviços seguros ou MMIO Samsung.

```sh
python3 scripts/test_lk_entry_granule.py -v
python3 scripts/inspect_lk_entry_granule.py /private/path/sboot.bin > /tmp/entry-granule.json
cmp /tmp/entry-granule.json docs/references/lk-entry-granule-hzc2.json
python3 scripts/emulate_lk_entry_granule_qemu.py /private/path/sboot.bin > /tmp/entry-granule-qemu.json
cmp /tmp/entry-granule-qemu.json docs/references/lk-entry-granule-qemu-hzc2.json
python3 -m unittest discover -s scripts -p 'test_lk*.py'
python3 scripts/validate_baseline.py --output-dir build/baseline-lk-entry-granule
```

Os relatórios [estático](references/lk-entry-granule-hzc2.json) e
[QEMU](references/lk-entry-granule-qemu-hzc2.json) foram reproduzidos byte
a byte. [Validação da rodada](references/lk-entry-granule-validation-20261031.json):
353 testes LK, incluindo os14 novos, e baseline completo9/9.

Próximo: fonte do estado herdado e caminho IOCC/DMA do host UFS. A seleção
de EL e a leitura real do registrador estão agora ensaiadas em laboratório;
isso não resolve carregamento físico, coerência ou recuperação do diagnóstico.

Continuação de31/10/2026: A [continuação PHY/IOCC](lk-ufs-iocc-hzc2.md) liga nominalmente a tabela alternativa ao controle da referência FlopKernel e separa as consultas do seletor/máscara. O estado herdado de CPU e a coerência física continuam abertos.
