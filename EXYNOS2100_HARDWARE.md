# Exynos 2100 Hardware Reference — Galaxy S21 Ultra (SM-G998B)

Extraído de `exynos2100.dts` (kernel público Samsung) — base para portabilidade
bare-metal e validação cruzada com QEMU `virt`.

---

## Mapa de Memória Física (resumo)

| Device | Base | Size | Descrição |
|--------|------|------|-----------|
| **GIC-600 Distributor** | `0x1020_0000` | 0x10000 | GICD_CTLR, GICD_TYPER, etc. |
| **GIC-600 Redistributor** | `0x1024_0000` | 0x40000 | GICR_BASE + frames por CPU |
| **GIC-600 ITS** | `0x1028_0000` | 0x20000 | Interrupt Translation Service |
| **MCT (Local Timer)** | `0x1004_0000` | 0x10000 | Memory Controller Timer |
| **Chip ID** | `0x1000_0000` | 0x1000 | ID do SoC, rev, etc. |
| **SYSREG / PMU** | `0x1001_0000` | 0x10000 | Power management, sysregs |
| **UART0 (Debug)** | `0x1080_0000` | 0x10000 | `uart0` — `samsung,exynos-uart` |
| **UART1 (Console)** | `0x1084_0000` | 0x10000 | `uart1` — console principal |
| **UART2** | `0x1088_0000` | 0x10000 | `uart2` |
| ... UARTs até 19 | ... | ... | 20 portas USI v2 no total |
| **I2C / SPI / GPIO** | `0x11C0_0000`+ | variados | Pinctrl + controllers |
| **USB PHY / Controller** | `0x1200_0000`+ | — | xHCI, PHYs |
| **MMC / UFS** | `0x1250_0000`+ | — | Armazenamento |
| **Display / GPU** | `0x1300_0000`+ | — | Mali-G78, DPUB, etc. |
| **NPU** | `0x1400_0000`+ | — | Neural Processing Unit |
| **DRAM** | `0x8000_0000` | 8–12 GiB | Início da RAM física |

> **Nota**: O mapa completo tem 200+ nodes. Este resumo foca no bring-up
> inicial (GIC, Timer, UART, Clock, Reset).

---

## GIC-600 (ARM GICv3 + ITS)

```dts
gic: interrupt-controller@10200000 {
    compatible = "arm,gic-v3";
    #interrupt-cells = <3>;
    interrupt-controller;
    reg = <0x0 0x10200000 0x0 0x10000>,   // GICD
          <0x0 0x10240000 0x0 0x40000>,   // GICR
          <0x0 0x10280000 0x0 0x20000>;   // ITS
    interrupts = <GIC_PPI 9 (GIC_CPU_MASK_SIMPLE(4) | IRQ_TYPE_LEVEL_HIGH)>;
    interrupt-parent = <&gic>;
    // ...
};
```

- **GICD**: 0x1020_0000 (vs QEMU 0x0800_0000)
- **GICR**: 0x1024_0000 (vs QEMU 0x080A_0000) — 4 redistributors (4 CPUs Cortex-X1 + 3 Cortex-A78 + 4 Cortex-A55 = 8 CPUs? Verificar)
- **ITS**: 0x1028_0000 (para MSI/MSI-X)
- **PPIs**: 16 por CPU (0-15), **SPIs**: 0x200+ (512+)
- **Redistributor stride**: 0x20000 por CPU (padrão GICv3)

---

## MCT (Memory Controller Timer) — Timer Local

```dts
mct: timer@10040000 {
    compatible = "samsung,exynos-mct";
    reg = <0x0 0x10040000 0x0 0x10000>;
    interrupts = <GIC_SPI 224 IRQ_TYPE_LEVEL_HIGH>,
                 <GIC_SPI 225 IRQ_TYPE_LEVEL_HIGH>,
                 <GIC_SPI 226 IRQ_TYPE_LEVEL_HIGH>,
                 <GIC_SPI 227 IRQ_TYPE_LEVEL_HIGH>;
    clocks = <&oscclk>;
    clock-names = "mct";
};
```

- **Base**: 0x1004_0000
- **Clock**: 26 MHz (oscclk)
- **IRQs**: SPI 224–227 (4 canais globais)
- **Registradores chave**: `MCT_GLOBAL_CNT`, `MCT_LOCAL_CNT`, `MCT_INT_ENB`, `MCT_INT_CSTAT`
- **Diferença do architected timer**: MCT é SoC-local, não por-CPU. Para timer por-CPU, usar CNTPIP_EL1 (PPI 30) ou CNTPSIRQ (PPI 29) do GIC.

---

## UART (Samsung USI v2)

```dts
uart1: serial@10840000 {
    compatible = "samsung,exynos-uart";
    reg = <0x0 0x10840000 0x0 0x100>;
    interrupts = <GIC_SPI 533 IRQ_TYPE_LEVEL_HIGH>;  // 0x215
    clocks = <&clk_uart1>, <&oscclk>;
    clock-names = "uart", "clk_baud";
    status = "okay";
};
```

- **Console principal**: `uart1@10840000`
- **Compatível**: `samsung,exynos-uart` (USI v2 — **não** PL011)
- **IRQ**: SPI 533 (0x215)
- **Clock baud**: oscclk (26 MHz)
- **Registradores**: Diferentes do PL011 — ver `drivers/tty/serial/samsung_usi.c` no kernel

**Outras UARTs** (20 total, `uart0`..`uart19`):
- `uart0@10800000` (debug)
- `uart1@10840000` (console)
- `uart2@10880000`
- ... espaçamento 0x4000 entre cada

---

## Clocks e Reset

```dts
oscclk: oscillator {
    compatible = "fixed-clock";
    #clock-cells = <0>;
    clock-frequency = <26000000>;  // 26 MHz
};
```

- **Oscilador de referência**: 26 MHz fixo
- **PLLs**: Múltiplos (APLL, MPLL, VPLL, etc.) — configurados pelo firmware/ATF
- **Clock tree**: Complexo — ver `drivers/clk/samsung/clk-exynos2100.c`

---

## Inicialização (Boot Flow)

1. **BL1 (ROM)** → **BL2 (TF-A)** → **BL31 (EL3 Runtime)** → **U-Boot** → **Linux**
2. **EL3** (TF-A): Configura GIC, clocks, PSCI, TZASC
3. **U-Boot**: Carrega kernel + dtbo + initrd em 0x8400_0000
4. **Kernel**: Entra em EL1, habilita MMU, monta rootfs

**Endereços de boot conhecidos**:
- Kernel Image: `0x8008_0000` (típico)
- DTB: `0x8300_0000` (típico)
- Initrd: `0x8400_0000` (confirmado no DTS/boot header)

---

## Diferenças Críticas vs QEMU `virt`

| Aspecto | QEMU `virt` | Exynos 2100 Real |
|---------|-------------|------------------|
| **GIC Base** | 0x0800_0000 | **0x1020_0000** |
| **GIC Redist** | 0x080A_0000 | **0x1024_0000** |
| **Timer** | Architected (PPI 30) | **MCT (SPI 224-227)** + Architected |
| **UART** | PL011 @ 0x0900_0000 | **USI v2 @ 0x1084_0000** |
| **UART IRQ** | SPI 33 | **SPI 533** |
| **CPU Topology** | 1-8 CPUs genéricas | **1+3+4 (X1+A78+A55)** |
| **PSCI** | QEMU emulado | **TF-A real (SMC)** |
| **Secure Boot** | Não | **Sim (AVB + Knox)** |

---

## Próximos Passos para Portabilidade (R10+)

1. **EL3/TF-A chainload**: Carregar payload via U-Boot `go` ou TF-A `bl33`
2. **GIC-600 init**: Sequência distinta do GICv3 genérico (GICD_CTLR.DS, ARE, etc.)
3. **MCT driver**: Substituir timer architected por MCT para timestamp local
4. **USI v2 UART driver**: Registradores diferentes do PL011
5. **MMU page tables**: Mapear 0x1020_0000 (GIC), 0x1084_0000 (UART), DRAM
6. **PSCI calls**: `CPU_ON`, `CPU_OFF`, `SYSTEM_RESET` via SMC
6. **Device tree parsing**: Usar `parse_fdt.py` para extrair endereços em runtime

---

## Referências de Código (Kernel Público)

- `arch/arm64/boot/dts/exynos/exynos2100.dts` — SoC description
- `arch/arm64/boot/dts/exynos/exynos2100-p3s.dts` — Board S21 Ultra
- `drivers/tty/serial/samsung_usi.c` — USI v2 UART driver
- `drivers/clocksource/exynos_mct.c` — MCT timer driver
- `drivers/irqchip/irq-gic-v3.c` — GICv3 driver (suporta GIC-600)
- `drivers/firmware/psci.c` — PSCI client
- `drivers/clk/samsung/clk-exynos2100.c` — Clock tree

---

## Como Obter o DTB do Firmware Real (G998BXXSJHZC2)

```bash
# 1. Baixar AP tar.md5 do SamFW (ZTO)
# 2. Extrair
tar -xf AP_*.tar.md5

# 3. Extrair boot.img / dtbo.img
abootimg -x boot.img
# → zImage, initrd, dtb (appended ou separado)

# 4. Extrair DTB do zImage
./extract-dtb zImage -o dtbs/
dtc -I dtb -O dts dtbs/*.dtb > kernel.dts

# 5. Extrair dtbo.img (overlays)
# Usar ferramenta: https://github.com/PabloCastellano/extract-dtb
```

---

## Validação Cruzada (QEMU ↔ Hardware)

| Teste | QEMU `virt` | Exynos 2100 Real |
|-------|-------------|------------------|
| R8A (MMU) | PASS | Pendente (page tables diferentes) |
| R8B (EL3→EL2→EL1) | PASS | Requer TF-A chainload |
| R8C (GICv3 + Timer) | PASS (INTID 30) | **MCT (SPI 224) ou PPI 30** |
| R9 (Microkernel) | PASS | Requer UART + GIC + Timer drivers |

> **Meta R10**: Rodar R9 no hardware real via chainload U-Boot → payload EL2/EL1.

---

*Documento gerado a partir de `exynos2100.dts` público (kernel 5.4/6.x Samsung).  
Para o build exato `G998BXXSJHZC2`, extrair DTB do `boot.img` do AP tar.md5.*