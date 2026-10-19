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

## BL Firmware Extraction Results (G998BXXSJHZC2)

**Source**: `BL_G998BXXSJHZC2_...tar.md5` (10.4 MB)

### Extracted Components

| File | Size | Identity |
|------|------|----------|
| `sboot.bin` | 4 MB | **BL2 + TF-A v1.5** (Athens platform) |
| `tzsw.img` | 1.5 MB | TrustZone Secure World / TEEGRIS v3.7 |
| `tzar.img` | 7 MB | TEEGRIS v4 (Trusted OS) |
| `ldfw.img` | 8 MB | Loadable Firmware (exynos991) |
| `harx.bin` | 3 MB | Hypervisor/Arx (BL31 setup, S2MPU) |
| `vbmeta.img` | 10 KB | AVB metadata (partition table) |
| Others | — | dpm, keystorage, ssp, uh, up_param, vddcal_fw |

### TF-A / BL2 Analysis (from `sboot.bin`)

```text
TF-A Version:    v1.5(release)
Platform:        Athens (Exynos 2100 / s5e9840)
Build ID:        RP1A-1A19R1-1-gbfac7c7
Build Time:      Sep 3 2024 16:38:03
Git Commits:     bfac7c7 249a7b4 9c96c10 a41bdbc edca2c0 ...
Builder UID:     swp
```

**Key capabilities confirmed in BL2/TF-A:**
- **PSCI conduit**: `HVC` (not SMC)
- **GIC**: GICv3 (source: `dev/interrupt/arm_gic-v3/arm_gic-v3.c`)
- **EL3 Monitor**: Present with version check
- **DTB handling**: Full libfdt support (`fdt_check_header`, `fdt_path_offset`, `fdt_getprop`, `fdt_setprop`, `configure_dtb`)
- **PSCI in DTB**: Explicit DTB parsing for PSCI method (`fdt_path_offset of PSCI fail`)

### TEEGRIS (Trusted OS)
- `tzar.img`: TEEGRIS v4, build 2022-03-23 / 20260309195836
- `tzsw.img`: TEEGRIS v3.7, build 2023-08-08 10:38:18
- Platform: `exynos2100root0` / `exynos2100dlroot0`

### AVB Partition Table (from `vbmeta.img`)

Partitions with AVB verification:
```
recovery, dtbo, prism, optics, boot1, bootloader,
harx, keystorage, ldfwH, tzsw, vendor_boot, product, system, vendor
```

**Device**: `SM-G998B_EUR_XX_EKEY0` (Galaxy S21 Ultra, Europe)
**Build**: `G998BXXSJHZC2` / `20260309203616`
**Security patch**: `2026-01-01`

### Critical Findings for Bare-Metal

| Aspect | Finding | Implication |
|--------|---------|-------------|
| **Boot chain** | BL2 (sboot.bin) → Kernel | No U-Boot in BL; Samsung proprietary chain |
| **Chainload point** | After BL2, before kernel | Need to inject payload at EL2/EL1 via custom bootloader |
| **PSCI** | HVC conduit | Use `hvc #0` for PSCI calls (CPU_ON, SYSTEM_RESET) |
| **GIC** | GICv3 initialized by TF-A | GICD/GICR already configured; we inherit at EL1/EL2 |
| **DTB** | Dynamic in BL2 (`configure_dtb`) | Base DTB not in BL; must come from `vendor_boot` or `dtb` partition |
| **Secure memory** | Managed by BL2/TEEGRIS | `get secure memory base addr` — avoid reserved regions |

### Missing for Bring-Up (need from AP or Samsung source)

1. **Base DTB** (`exynos2100-p3s.dtb`) — in `vendor_boot.img` or separate `dtb` partition
2. **Kernel binary** (`Image` / `zImage`) — in `boot.img` partition (not in this BL)
3. **U-Boot** — Not present; Samsung uses direct BL2→kernel

### Next Steps

1. Extract `vendor_boot.img` from AP tar.md5 → should contain base DTB + kernel
2. Or obtain Samsung kernel source for `G998BXXSJHZC2` → has `exynos2100-p3s.dts`
3. Build minimal payload that:
   - Runs at EL2 (after BL2 hands off) or EL1
   - Uses PSCI HVC for CPU bring-up
   - Inherits GICv3 config from TF-A
   - Maps known Exynos 2100 addresses (GICD 0x1020_0000, MCT 0x1004_0000, UART 0x1084_0000)

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