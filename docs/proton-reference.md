# Proton+ v6.1.0: referência de código para Exynos 2100

Análise estática feita pelo GitHub em 2026-10-20, após indicação do usuário. Tag `v6.1.0`, commit **a0d73239d600d9ec89e7ac4775d2139d4d61290e**. Foram conferidos a release, Makefile, configuração, DTS e partes da integração Mali/Exynos. Não é uma auditoria completa do kernel.

## Correspondência com o arquivo enviado

A [release v6.1.0](https://github.com/ProtonKernel/Proton/releases/tag/v6.1.0) lista exatamente `ProtonPlus-v6.1.0-KSU-exynos2100-20260125-1906.zip`, nome do pacote enviado pelo usuário. O ZIP publicado já foi baixado e inspecionado; seu digest confere com a API da release, e a Image identifica Linux 5.4.302. Hashes, headers Linux/EFI e DTB extraído estão em [proton-binary.md](proton-binary.md). Não foi comparado byte a byte com o upload anterior nem reproduzida a compilação da tag.

O [Makefile](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/Makefile) define VERSION=5, PATCHLEVEL=4, SUBLEVEL=302: **Linux 5.4.302**. “v6.1.0” é a versão do projeto Proton+, não Linux 6.1. A imagem stock HZC2 anteriormente examinada contém Linux 5.4.242; as duas referências devem permanecer distintas. O envio de um kernel alternativo não foi tomado como confirmação de que ele está instalado no aparelho.

## Driver Mali e configuração

O [proton_defconfig](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/arch/arm64/configs/proton_defconfig) seleciona:

- `CONFIG_MALI_DDK_VALHALL_R38P1=y`;
- `CONFIG_MALI_MIDGARD=m`, portanto driver configurado como módulo;
- `CONFIG_MALI_REAL_HW=y` e plataforma `exynos`;
- clock, DVFS, PM, runtime PM, QoS, thermal e LLC Exynos habilitados;
- `CONFIG_MALI_CSF_SUPPORT` desabilitado.

O [Kbuild](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/drivers/gpu/arm/Kbuild) direciona a seleção r38p1 para [drivers/gpu/arm/bv_r38p1/](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/drivers/gpu/arm/bv_r38p1). Esse diretório contém código de gerenciamento da GPU, memória/MMU, jobs e interfaces Linux. A integração específica Samsung fica em [drivers/gpu/arm/exynos/](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/drivers/gpu/arm/exynos), incorporada ao módulo Mali.

Nos arquivos consultados, [gpexbe_clock.c](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/drivers/gpu/arm/exynos/backend/gpexbe_clock.c) obtém o identificador de clock do DT e usa chamadas `cal_dfs_*`; [gpexbe_pm.c](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/drivers/gpu/arm/exynos/backend/gpexbe_pm.c) usa o domínio Exynos e `cal_pd_status/control`. Isso mostra dependências reais da camada CAL/PM Samsung; o endereço MMIO isolado não fornece uma sequência completa de ativação bare-metal.

O módulo Android [GpuDriverUpdate_Exynos2100](https://github.com/elitetest1/GpuDriverUpdate_Exynos2100/tree/026c0923fbe67f7a3a58fcf4f768d67e5abbb677), indicado antes, declara bibliotecas userspace r38p1. A versão nominal coincide com a opção selecionada neste defconfig, mas essa coincidência não comprova ABI, integração ou funcionamento conjunto no HZC2.

## Recursos descritos no DTS

Foi lido [arch/arm64/boot/dts/exynos/exynos2100.dts](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/arch/arm64/boot/dts/exynos/exynos2100.dts). É uma árvore extensa com phandles numéricos e símbolos; não uma configuração mínima pronta para o R10. O Makefile de DTS seleciona `exynos2100.dtb` para CONFIG_SOC_EXYNOS2100. Também existem oito DTS p3s em `samsung/p3s/`, de r02 a r22, cuja presença não prova qual overlay ou revisão o aparelho usa.

| Recurso no DTS consultado | Valor |
|---|---|
| Nó GPU | mali@18500000, compatible arm,mali |
| GPU reg | 0x18500000, tamanho 0x5000 |
| sysreg_g3d | 0x18420000 |
| GPU JOB | SPI 339 → INTID 371 |
| GPU MMU | SPI 340 → INTID 372 |
| GPU GPU | SPI 338 → INTID 370 |
| Energia | referência power-domains; g3d_genpd_name=pd-embedded_g3d |
| GICD | 0x10200000 / 0x10000 |
| GICR | 0x10240000 / 0x200000 |
| Timer físico NS | PPI 14 → INTID 30; clock-frequency 26 MHz |
| PSCI | method=smc |
| Nós memory / device_type=memory | ausentes no arquivo consultado |

As conversões SPI→INTID somam 32 e seguem a ordem JOB, MMU, GPU declarada no nó. Esses dados são desta referência Proton; não foram novamente cruzados com o nó GPU da imagem stock ou com registradores do telefone nesta revisão.

O DTS contém uma reserva `gpu_buffer` com `size=0x4000000` (64 MiB) e alinhamento, sem endereço fixo nesse nó. Isso não permite escolher sua posição ou tratar a região como livre. A árvore também inclui alterações de política/frequência, como uma entrada de 949000 na tabela DVFS da GPU; não copiar parâmetros de overclock/tuning como especificação stock.

## Utilidade para S21-baremetal

Esse repositório fornece uma referência de código para a futura investigação GPU: mapa de registradores, interrupções, gerenciamento de jobs/MMU e integração de clock/energia. O driver depende das abstrações Linux e Samsung; não pode ser simplesmente ligado ao payload R10.

Para o estágio inicial continuam prioritários o contrato do carregador, mapa final de RAM/reservas, console e timer em uma CPU. O DTS Proton não preenche a ausência de RAM do DTB estático stock, nem demonstra o EL/estado de caches do handoff. Nenhum driver, tabela DVFS ou binário Proton foi incorporado ao R10. A análise de fonte não compilou esse kernel nem o executou no telefone. A etapa posterior inspecionou o ZIP e implementou ferramentas de contêiner, sem incorporar os drivers ao R10.

Referências do firmware usado como base: [stock-firmware-hzc2.md](stock-firmware-hzc2.md), [samsung-reference.md](samsung-reference.md). Política atual do payload: [fdt-resources.md](fdt-resources.md).

## Complemento: build e instalação

O caminho Image → boot/vendor_boot e os scripts AnyKernel foram analisados separadamente. Veja [loader-contract.md](loader-contract.md) para as revisões fixadas, digest publicado do ZIP, diferenças entre headers e PC real, matriz EL/RAM/caches e limitações da análise do firmware de boot. A revisão do AnyKernel observada hoje não é automaticamente a embutida no ZIP de janeiro.
