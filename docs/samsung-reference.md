# Referência Samsung usada no R10

Arquivos recebidos do usuário; sem atribuir ao pacote uma identidade binária que ele não declara.

## Pacote de atualização

O ZIP externo `SM-G998B_15_Opensource_G998BXXSJHZA6_G998NKSSCHZA5_G998NKSSCHZA9_G998BXXSJHZC2 (1).zip` inclui o build alvo HZC2 no nome. Dentro dele estão `G998BXXSJHZA6_kernel.tar.gz` (34 arquivos) e instruções para aplicar diretamente sobre a base `G998BXXUEHYD5`. Não exige os deltas intermediários. Os oito DTS p3s são overlays, não o DTB base completo. O delta não substitui UART, GIC ou MCT.

O `Kernel.tar.gz` completo recebido separadamente contém Linux 5.4.242 e `exynos2100-p3sxxx_defconfig`. Sua procedência foi informada pelo usuário; o arquivo isolado não identifica o build Samsung exato. SHA-256: `c5ad9994240e67ebdc40878c191be040bf30db398bc8513ea1f156eaebd86bf2`.

## Conferências no código

- GIC: `gic_iterate_rdists()` usa afinidade completa, respeita `redistributor-stride` quando presente e avança RD+SGI com frames extras para VLPIS.
- UART: `exynos_usi_init()` respeita `dbg_uart_ch`, libera reset e solicita clock. O baud usa o clock efetivo obtido pelo framework, não a frequência do oscilador presumida. `has_fracval` seleciona fração numérica ou tabela DIVSLOT.
- MCT: TCNTB/ICNTB/TCON e WSTAT confirmam que o antigo protocolo do payload precisa ser substituído; MCT está fora da sequência inicial.

## Hashes dos arquivos consultados

| Caminho no Kernel.tar.gz | SHA-256 |
|---|---|
| `Makefile` | `9021bc5a2bf11176af99ec6979e87729aa6084272c38e1c7f6215794661b2ab3` |
| `arch/arm64/configs/exynos2100-p3sxxx_defconfig` | `e0d7cfe4c8fceb31a5e44a9ba916c00338834a58011a44494e15120efe76c4fd` |
| `drivers/irqchip/irq-gic-v3.c` | `b7c4a3305f12c4a7dbdf634075bf8cfee85c6b7456c32e33a995ca3bc150fd81` |
| `drivers/tty/serial/exynos_tty.c` | `f8e0f52ca9cd2a29e65096749f3498eeef19856fd250c3a272bcf0fb6182b267` |
| `drivers/clocksource/exynos_mct.c` | `672999b9f93351d31c4fa2c24738b56ee8e291c98ea31c07069d203992063c15` |
| `include/linux/serial_s3c.h` | `e5c60b29c65ba77a469aa562a5fc4c5b6d64d0abbf48c295967885f6ebdc1aaa` |

A conferência do pacote-fonte não substitui a identificação do DTB ativo, da revisão da placa, do estado de clock/pinmux e do contrato real do carregador.

## READMEs reapresentados — revisão 2026-10-21 UTC

Lidos diretamente dos anexos nesta revisão. README_Kernel.txt menciona p3s, GCC 4.9/Clang r383902 e variáveis Android 11/r; README_Platform.txt indica Android 15.0 para módulos AOSP. Essas instruções não identificam o estado de execução do aparelho nem comprovam a cadeia de boot. O kernel não foi recompilado a partir delas nesta etapa.

| Anexo | SHA-256 dos bytes recebidos |
|---|---|
| README_Kernel.txt | `943e571a11d4ba2ff4f02736e587e2700c1265d939fcb63f49dd93174527ba08` |
| README_Platform.txt | `608870f35c667416e24a42749407191699ac583102552c3b632d0807162b8dd8` |

A pasta [samsung_kernel](../samsung_kernel/README.md) é um recorte, não uma cópia completa desse pacote. Os arquivos necessários para a próxima investigação estão na [revisão do repositório](repository-review-2026-10-21.md).

## Cruzamento UART0 com LK HZC2

O pacote completo foi recuperado novamente e seu hash conferido. `exynos2100.dts` identifica UART0 em 0x10540000, canal debug 115200/8 e pads gpg0-2/gpg0-3; o nó está disabled. [Evidências, hashes e reprodução](lk-console-handoff.md#cruzamento-com-as-fontes-samsung--2026-10-21).

## Referência externa FlopKernel — 30/10/2026

A [análise fixada em4553117](flop-kernel-reference.md) consulta Linux5.4.304, fontes p3s e SRPMB. A árvore tem fluxo unified próprio, distinto das instruções dos anexos. Probe C confirma o layout RPMB; não estabelece equivalência com o pacote Samsung/HZC2 nem compatibilidade de boot no aparelho.
