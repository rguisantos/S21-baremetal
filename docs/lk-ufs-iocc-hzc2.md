# LK HZC2: isolamento PHY e caminho candidato de IOCC

O cruzamento do LK com duas fontes fixadas do FlopKernel separa dois
controles antes tratados apenas como endereços locais do host UFS:

- `0x15860728`, OR1: corresponde ao bypass de isolamento do PHY na referência.
- `0x11020700`, OR`0x00300000`: corresponde aos bits de IOCC declarados
  pela referência, quando o LK seleciona a tabela alternativa e a consulta
  posterior devolve1.

Isso fecha a correspondência nominal desse ramo de configuração. **Não
é uma leitura de IOCC do telefone nem uma demonstração de DMA coerente.**
A tabela primária usa outro endereço, `0x13020700`, cuja identificação
não foi estabelecida por essa correspondência.

Análise de31/10/2026, Campo Grande, base main `ef20d23`, após PR #72.
Sboot HZC2:4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs e tabelas são offsets de arquivo; `0xcd31c8` é um endereço global
relativo ao delta de link LK, não um offset respaldado pelos4MiB do arquivo.

## O que o código original escreve

| Instrução | Operação local |
|---|---|
| `0x10e8a8` | LDP X3/X4 da tabela+40/+48 |
| `0x10e8c8..0x10e8d0` | Lê u32 em X3, faz OR1 e grava no mesmo endereço |
| `0x10e8d4` | Se X4=0, pula a consulta e a operação IOCC |
| `0x10e8d8` | Consulta novamente `0x147ea8` |
| `0x10e8e0..0x10e8e8` | Carrega o ponteiro da tabela+48, lê u32 e escolhe o ramo |
| `0x10ebc0/0x10ebc4` | Consulta=1: OR`0x00300000`, store |
| `0x10e8ec/0x10e8f0` | Outros valores: OR`0x00c00000`, store |

As duas tabelas fixadas contêm ponteiros não nulos em+48. O ramo de skip
existe no código, mas o ponteiro zero usado no ensaio é um controle sintético.
Esses trechos fazem OR, preservando bits anteriormente ligados. Não limpam
a máscara do outro ramo: um valor antigo`0x00c00000` com a consulta1
resultaria em`0x00f00000`, e não em`0x00300000`.

## Seleção da tabela e consultas distintas

O getter `0x147ea8` é ADRP + LDR W0 de relativo`0xcd31c8` + RET.
Os acessos são feitos em instantes diferentes:

1. `0x10e868`: zero seleciona diretamente a tabela primária`0x303198`.
2. Se o primeiro valor é não zero, `0x10eba8` consulta de novo. Somente
   o segundo valor1 seleciona a alternativa`0x3038d8`; outros voltam à primária.
3. `0x10e8d8`, depois da escrita PHY: uma nova leitura escolhe a máscara.

| Valores fornecidos ao seletor | Consulta posterior | Endereço nominal / OR |
|---|---:|---|
| 0, segunda consulta omitida | 0 | `0x13020700` / `0x00c00000` |
| 1, 1 | 1 | `0x11020700` / `0x00300000` |
| 1, 0 | 1 | `0x13020700` / `0x00300000` |
| 1, 1 | 0 | `0x11020700` / `0x00c00000` |

As duas últimas linhas são controles de mudança entre leituras, não
relatos do aparelho. Demonstram por que não se deve deduzir a máscara
somente da tabela selecionada. O produtor, o valor vivo e a estabilidade
desse global continuam abertos. Não se atribuiu ao retorno significado
de EVT/revisão de silício a partir da tela Download.

## Referência FlopKernel fixada

Repositório `FlopKernel-Series/flop_exynos2100_kernel`, commit
`4553117a5014928dff55595f46627e0d77bcf133`. O
[manifesto](references/flop-ufs-iocc-source-reference.json) fixa tamanho,
SHA-256 e blob Git de dois arquivos; eles são conferidos antes da análise.
As fontes completas ficam externas ao repositório deste projeto.

No [DTS exynos2100](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/arch/arm64/boot/dts/exynos/exynos2100.dts#L14375),
o nó UFS declara `dma-coherent` e referencia dois syscons por phandles
numéricos. O extrator resolve cada phandle a seu nó e região:

| Controle | Base / offset | Máscara / valor | Endereço calculado |
|---|---|---|---|
| `ufs-phy-iso`, PMU | `0x15860000` + `0x728` | `1` / `1` | `0x15860728` |
| `ufs-iocc`, sysreg | `0x11020000` + `0x700` | `0x00300000` / `0x00300000` | `0x11020700` |

No [driver Exynos](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/ufs/ufs-exynos.c#L433),
a configuração externa pede primeiro o bypass PHY por `exynos_pmu_update`
e depois a atualização IOCC por `regmap_update_bits`. Há nove testemunhas
de fonte com linhas no [relatório](references/flop-ufs-iocc-reference.json).
O parse de DT coloca o valor IOCC em zero quando `dma-coherent` está ausente.
Esse caminho de limpar a máscara não equivale aos ramos OR/skip do trecho LK.

O parser suporta a sintaxe achatada dessa fonte, preserva outras
propriedades como tokens opacos e interpreta somente células u32 literais.
Não resolve referências por labels, expressões, includes ou overlays,
não compila o DTS e não executa scripts/macros do kernel. O arquivo é uma
referência custom fixada; não foi tratado como DTB stock HZC2 ou estado vivo.

## Ensaio dos fragmentos originais em QEMU

São32 casos: oito cenários, dois valores iniciais das células e duas
posições de código, deltas`0x3ff14000`/`0x41f14000`. Executam os bytes
originais do seletor, do LDP de ponteiros, do getter e dos ramos RMW.
Os resultados coincidem com o modelo, incluindo combinações mistas,
preservação de bits antigos e o controle de ponteiro nulo.

**Os alvos são células de RAM no QEMU.** Os ponteiros+40/+48 das cópias
das tabelas são substituídos; o debugger fornece o global antes de cada
leitura. ADRP/LDR/RET do getter executam de verdade, sem substituir o
resultado por um valor no registrador. As operações entre o LDP e a escrita
PHY, relativas ao ponteiro+56, e o restante do inicializador são omitidos.

Foram conferidos guardas das células, SP, registradores não envolvidos e
bytes originais de código. Nenhum MMIO Samsung, serviço seguro ou pedido
de armazenamento foi executado; não há modelo de cache/snooping nesse ensaio.

## Reprodução e resultado

```sh
python3 scripts/test_lk_ufs_iocc.py
python3 scripts/test_flop_ufs_iocc.py
python3 scripts/inspect_lk_ufs_iocc.py /private/path/sboot.bin > /tmp/ufs-iocc.json
cmp /tmp/ufs-iocc.json docs/references/lk-ufs-iocc-hzc2.json
python3 scripts/inspect_flop_ufs_iocc.py /path/to/pinned/sources /private/path/sboot.bin > /tmp/flop-iocc.json
cmp /tmp/flop-iocc.json docs/references/flop-ufs-iocc-reference.json
python3 scripts/emulate_lk_ufs_iocc_qemu.py /private/path/sboot.bin > /tmp/ufs-iocc-qemu.json
cmp /tmp/ufs-iocc-qemu.json docs/references/lk-ufs-iocc-qemu-hzc2.json
python3 scripts/validate_baseline.py --output-dir build/baseline-lk-ufs-iocc
```

O extrator LK confere29 palavras GNU,9 destinos,29 operandos e5 grafos.
Há12 testes novos LK e14 da referência; regressões completas365 LK e40
Flop, incluindo os26 novos. Os três relatórios foram reproduzidos byte
a byte; baseline9/9. [Validação](references/lk-ufs-iocc-validation-20261031.json).

Próximo: produtor de`0xcd31c8`, preservação/estado físico de IOCC e tradução
de barramento/SMMU. O [pool da CPU](lk-pool-mmu-hzc2.md), o pedido nominal
de IOCC e uma transferência coerente observada continuam evidências distintas.
