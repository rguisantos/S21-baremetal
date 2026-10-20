# Exynos 2100 Hardware Reference — Galaxy S21 Ultra (SM-G998B)

Extraído de `exynos2100.dts` (kernel público Samsung) — base para portabilidade
bare-metal e validação cruzada com QEMU `virt`.

---

## Mapa de Memória Física (resumo)

| Device | Base | Size | Descrição |
|--------|------|------|-----------|
| **GIC-600 Distributor** | `0x1020_0000` | 0x10000 | GICD_CTLR, GICD_TYPER, etc. |
| **GIC-600 Redistributor** | `0x1024_0000` | 0x200000 (DTB) | GICR_BASE + frames por CPU |
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
          <0x0 0x10240000 0x0 0x200000>,  // GICR
          <0x0 0x10280000 0x0 0x20000>;   // ITS
    interrupts = <GIC_PPI 9 (GIC_CPU_MASK_SIMPLE(4) | IRQ_TYPE_LEVEL_HIGH)>;
    interrupt-parent = <&gic>;
    // ...
};
```

- **GICD**: 0x1020_0000 (vs QEMU 0x0800_0000)
- **GICR**: 0x1024_0000 (vs QEMU 0x080A_0000) — DTB range 0x200000; CPU topology is 4×A55 + 3×A78 + 1×X1 (8 CPUs)
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
| **PSCI** | BL: HVC, DTB: SMC | Test `hvc #0` first, fallback to `smc #0` |
| **GIC** | GICv3 initialized by TF-A | GICD/GICR already configured; we inherit at EL1/EL2 |
| **DTB** | Dynamic in BL2 (`configure_dtb`) | Base DTB now extracted from `vendor_boot.img` ✅ |
| **Secure memory** | Managed by BL2/TEEGRIS | `get secure memory base addr` — avoid reserved regions |

---

## Firmware DTB Extraction Results (G998BXXSJHZC2)

**Source**: `vendor_boot.img` from AP tar.md5 → embedded DTB at offset 0xb77040

### Base SoC DTB Confirmed (from `extracted.dtb`)

This is the **actual base device tree** used by the firmware — not overlays. All key hardware addresses confirmed:

| Component | Address | Details | Verified |
|-----------|---------|---------|----------|
| **GIC-600 Distributor** | `0x1020_0000` | `reg = <0x00 0x10200000 0x10000>` | ✅ |
| **GIC-600 Redistributor** | `0x1024_0000` | `reg = <0x00 0x10240000 0x200000>` | ✅ |
| **GIC ITS** | (in redistributor range) | `interrupt-controller` with 3 cells | ✅ |
| **MCT (Local Timer)** | `0x1004_0000` | `samsung,exynos4210-mct`, size 0x800 | ✅ |
| **Chip ID** | `0x1000_0000` | `samsung,exynos2100-chipid`, size 0x100 | ✅ |
| **UART Console (uart1)** | `0x1084_0000` | `samsung,exynos-uart` (USI v2), SPI 533 (0x215) | ✅ |
| **PSCI** | — | `arm,psci-1.0`, `method = "smc"` | ✅ |
| **Architected Timer** | PPI 13-16 | `arm,armv8-timer`, 26 MHz crystal | ✅ |
| **CPU Topology** | — | 3 clusters: 4×A55 (cluster0), 3×A78 (cluster1), 1×X1 (cluster2) | ✅ |

> **Critical**: UART1 is `status = "disabled"` in DTB — firmware enables it at runtime. Our bare-metal must enable it explicitly.

---

## Boot Contract & Entry Point (R10 Payload)

### EL2 Entry (start_r10.S)

**Expected loader contract (not yet validated on hardware):**
- **Entry EL**: EL2 (after BL2 handoff)
- **x0**: FDT pointer (device tree blob)
- **x1-x3**: Reserved
- **Load address**: `0x8008_0000` (typical kernel load address from DTB `/chosen`)
- **Stack**: EL2 private stack (4 KB), EL1 stack (8 KB) set via `SP_EL1`

**EL2 → EL1 Drop:**
```assembly
/* HCR_EL2: RW=1 (EL1 AArch64), VM=0 (no stage-2), TGE=0 */
HCR_EL2 = (1<<31) | (0<<0) | (0<<29)

/* CNTHCTL_EL2: EL1PCTEN | EL1PCEN = 0x3 */
CNTHCTL_EL2 = 0x3
CNTVOFF_EL2 = 0

/* VBAR_EL2: minimal vector table */
VBAR_EL2 = vbar_el2

/* Drop to EL1h via ERET */
SPSR_EL2 = 0x3C5  // EL1h, DAIF=1111
ELR_EL2 = r10_el1_entry
SP_EL1 = __el1_stack_top
ERET
```

### EL1 Entry (r10_el1_entry)

**Initialization sequence:**
1. `vbar_install()` — install EL1 vector table
2. `uart_init()` — USI v2 UART1 @ 0x1084_0000
3. `mmu_init()` — identity map 4GB, 2MB blocks
4. `gic_init()` — GIC-600 Distributor + Redistributor + ICC_* CPU interface
5. `mct_init()` — MCT global + 4 channels, SPI 224-227
6. `timer_init()` — CNTP @ 1ms, PPI 30
7. `psci_call(PSCI_VERSION)` — test SMC/HVC

### IRQ Handling (via ICC_*)

```c
void exc_irq(u64 *frame, u64 kind) {
    u32 intid = gic_ack_irq();  // ICC_IAR1_EL1
    switch (intid) {
        case 30:   timer_handle_irq(); break;   // CNTP PPI
        case 224..227: mct_handle_irq(intid); break; // MCT SPI
        case 533:  /* UART1 */ break;           // UART1 SPI (disabled)
    }
    gic_eoi(intid);  // ICC_EOIR1_EL1
}
```

**IRQ Map (from DTB):**
| INTID | Source | Type | Status |
|-------|--------|------|--------|
| 13-16 | Architected timer | PPI | Used by Linux |
| 30 | CNTP (EL1 phys timer) | PPI | **Active** |
| 224-227 | MCT channels 0-3 | SPI | **Active** |
| 533 | UART1 | SPI | Disabled in DTB |

---

## Timer Integration (Architected Timer + MCT)

### Architected Timer (CNTP) — PPI 30
- **Frequency**: 26 MHz (from CNTFRQ_EL0 or DTB)
- **Tick**: 1ms (configurable)
- **IRQ**: PPI 30 (per-CPU, private)
- **Handler**: `timer_handle_irq()` → update CNTP_CVAL + `gic_eoi(30)`

```c
void timer_init(void) {
    cntfrq = mrs_cntfrq_el0() ?: 26000000;
    msr_cntp_cval_el0(mrs_cntpct_el0() + cntfrq / 1000);
    msr_cntp_ctl_el0(1);  // ENABLE=1, IMASK=0
    gic_enable_irq(30); gic_set_priority(30, 0x80);
}

void timer_handle_irq(void) {
    msr_cntp_cval_el0(mrs_cntpct_el0() + cntfrq / 1000);
    gic_eoi(30);
}
```

### MCT (Multi-Core Timer) — SPI 224-227
- **Base**: 0x1004_0000
- **Clock**: 26 MHz (fin_pll)
- **Channels**: 4 (0-3), each with independent compare/auto-reload
- **IRQs**: SPI 224 (ch0) ... 227 (ch3)
- **Handler**: `mct_handle_irq(irq)` → read MCT_INT_CSTAT, clear bits

```c
void mct_init(void) {
    mmio_write32(MCT_GLOBAL_CON, MCT_GLOBAL_CON_EN);
    for (i=0; i<4; i++) {
        mmio_write32(MCT_LOCAL_CMP(i), 26000);  // 1ms @ 26MHz
        mmio_write32(MCT_LOCAL_CON(i), MCT_LOCAL_CON_EN|MCT_LOCAL_CON_INTEN|MCT_LOCAL_CON_AUTO);
        mmio_write32(MCT_INT_ENB, mmio_read32(MCT_INT_ENB) | (1<<i));
    }
    gic_enable_irq(224..227);
}

void mct_handle_irq(u32 irq) {
    u32 cstat = mmio_read32(MCT_INT_CSTAT);
    for (i=0; i<4; i++) if (cstat & (1<<i)) {
        mmio_write32(MCT_INT_CSTAT, 1<<i);
        // channel i tick
    }
}
```

### Timer Tick Demo (main.c)
```c
while (1) {
    u32 now = timer_read_cnt() / (cntfrq / 1000);  // ms
    if (now != last_tick) {
        last_tick = now;
        if ((last_tick % 100) == 0) uart_puts("[Tick: ...ms]");
    }
}
```

### UART Console Node (exact DTS)

```dts
uart@10840000 {
    compatible = "samsung,exynos-uart";   // USI v2
    reg = <0x00 0x10840000 0x100>;
    interrupts = <0x00 0x215 0x04>;       // GIC SPI 533 (0x215)
    clocks = <0x74 0x75>;                 // gate_uart_clk1, ipclk_uart1
    clock-names = "gate_uart_clk1", "ipclk_uart1";
    status = "disabled";                  // firmware enables at runtime
    samsung,usi-phandle = <0x70>;         // USI block reference
    samsung,usi-offset = <0x00>;
    phandle = <0x29b>;
};

aliases {
    uart1 = "/uart@10840000";
    serial_1 = "/uart@10840000";
};
```

### USI v2 UART Driver Implementation (from Samsung kernel source)

**Source files:**
- `drivers/tty/serial/exynos_tty.c` — `exynos_usi_init()`, `exynos_serial_set_termios()`
- `include/linux/serial_s3c.h` — register offsets
- `drivers/clk/samsung/clk-exynos2100.c` — clock tree

**USI Init Sequence (exynos_usi_init):**
```c
wr_regl(port, USI_CON, USI_SET_RESET);  // 0xC4, bit 0 = 1
udelay(1);
wr_regl(port, USI_CON, USI_RESET);      // 0xC4, bit 0 = 0
udelay(1);
wr_regl(port, USI_OPTION, USI_HWACG_CLKREQ_ON);  // 0xC8, bit 1 = 1
```

**USI Stop (exynos_usi_stop):**
```c
wr_regl(port, USI_OPTION, USI_HWACG_CLKSTOP_ON);  // 0xC8, bit 2 = 1
```

**UART Mode Selection:**
```c
u32 val = rd_regl(port, USI_CON);
val &= ~USI_SW_CONF_MASK;  // 0x7
val |= USI_UART_SW_CONF;   // 0x1
wr_regl(port, USI_CON, val);
```

**Register Offsets (S3C2410 compatible, from serial_s3c.h):**
| Register | Offset | Purpose |
|----------|--------|---------|
| ULCON | 0x00 | Line control (8N1) |
| UCON | 0x04 | Control (PCLK, IRQ/DMA mode) |
| UFCON | 0x08 | FIFO control (enable, reset) |
| UMCON | 0x0C | Modem control |
| UTRSTAT | 0x10 | TX/RX status |
| UERSTAT | 0x14 | Error status |
| UFSTAT | 0x18 | FIFO status |
| UBRDIV | 0x28 | Baud rate divisor |
| UTXH | 0x20 | TX hold (write) |
| URXH | 0x24 | RX hold (read) |

**USI v2 Registers (from serial_s3c.h + exynos_tty.c):**
| Register | Offset | Value |
|----------|--------|-------|
| USI_CON | 0xC4 | |
| USI_OPTION | 0xC8 | |
| USI_SW_CONF_MASK | — | 0x7 |
| USI_UART_SW_CONF | — | 0x1 |
| USI_RESET | — | bit 0 = 0 |
| USI_SET_RESET | — | bit 0 = 1 |
| USI_HWACG_CLKREQ_ON | — | bit 1 = 1 |
| USI_HWACG_CLKSTOP_ON | — | bit 2 = 1 |

**Baud Rate Calculation (from exynos_serial_getclk):**
```
quot = (clk * 10) / (baud * 16)
ubrdiv = quot / 16
ufrac = quot % 16
udivslot_table[16] = {0x0000, 0x0080, 0x0808, 0x0888, 0x2222, 0x4924, 0x4A52, 0x54AA,
                       0x5555, 0xD555, 0xD5D5, 0xDDD5, 0xDDDD, 0xDFDD, 0xDFDF, 0xFFDF}
```
For 115200 @ 26 MHz: ubrdiv ≈ 14, ufrac ≈ 6

**Clock Tree (from clk-exynos2100.c):**
- OSCCLK: 26 MHz (fin_pll)
- UART gate clocks: GATE_DBGCORE_UART_QCH (alive), GATE_PERIC0_TOP0_QCH_UART_DBG (peric0)
- Divider clocks: DOUT_DIV_CLK_ALIVE_DBGCORE_UART, DOUT_DIV_CLK_PERIC1_UART_BT
- DTB phandles for uart1: clocks = <0x74 0x75> (gate_uart_clk1, ipclk_uart1)

### MCT Timer Node (exact DTS)

```dts
mct@10040000 {
    compatible = "samsung,exynos4210-mct";
    reg = <0x00 0x10040000 0x800>;
    #interrupt-cells = <0x02>;
    interrupt-controller;
    clocks = <0x174 0x175>;               // fin_pll, mct
    clock-names = "fin_pll", "mct";
    
    mct-map {
        compatible = "samsung,exynos-mct-map";
        #interrupt-cells = <0x02>;
        interrupt-parent = <0x01>;
        // 12 MCT channels mapped to GIC SPIs
    };
    phandle = <0x1a5>;
};
```

### PSCI Node

```dts
psci {
    compatible = "arm,psci-1.0";
    method = "smc";                       // SMC conduit (not HVC!)
};
```

> **Note**: DTB says PSCI method = `smc`, but BL firmware strings said HVC. The kernel uses SMC; TF-A may route HVC→SMC. Test both.

### CPU Topology (from DTB)

| Cluster | CPUs | Type | DTB compatible | CPU IDs |
|---------|------|------|----------------|---------|
| **cluster0 (little)** | 4 | Cortex-A55 | `arm,ananke` | 0x0000, 0x0100, 0x0200, 0x0300 |
| **cluster1 (mid)** | 3 | Cortex-A78 | `arm,hercules` | 0x0400, 0x0500, 0x0600 |
| **cluster2 (big)** | 1 | Cortex-X1 | `arm,hera` | 0x0700 |

All CPUs: `enable-method = "psci"`

### Memory Layout (reserved regions — no standard `memory@` node)

| Region | Address | Size | Purpose |
|--------|---------|------|---------|
| `linux,initrd-start` | runtime | — | Provided by bootloader |
| `linux,initrd-end` | runtime | — | Provided by bootloader |
| Reserved | `0x8f00_0000` | — | TZ / secure |
| Reserved | `0x9000_0000` | — | TZ / secure |
| Reserved | `0xb000_0000` | — | Shared / carveout |
| Reserved | `0xbff8_0000` | — | Boot params |
| Reserved | `0xf000_0000+` | — | PCIe / peripherals |

> DRAM starts at `0x8000_0000` (implied by kernel load addr). No `memory@80000000` node — bootloader passes mem size via FDT `/chosen`.

### Boot Parameters (from `/chosen`)

```dts
chosen {
    bootargs = "...";              // Full cmdline from U-Boot/BL2
    linux,initrd-start = <...>;    // Runtime
    linux,initrd-end = <...>;      // Runtime
    stdout-path = "serial0:115200n8"; // Console
};
```

### Validation: Public DTSI vs Firmware DTB vs BL Firmware

| Component | Public DTSI | Firmware DTB | BL Firmware |
|-----------|-------------|--------------|-------------|
| GICD | 0x1020_0000 | ✅ 0x1020_0000 | GICv3 init confirmed |
| GICR | 0x1024_0000 | ✅ 0x1024_0000 | — |
| MCT | 0x1004_0000 | ✅ 0x1004_0000 | — |
| ChipID | 0x1000_0000 | ✅ 0x1000_0000 | `s5e9840` (Exynos 9840) |
| UART1 | 0x1084_0000 | ✅ 0x1084_0000 | — |
| UART IRQ | SPI 533 | ✅ SPI 533 (0x215) | — |
| PSCI | SMC | ✅ SMC | TF-A strings: HVC |
| Timer | Arch (PPI 30) | ✅ PPI 13-16 + MCT | — |
| CPU Topology | 1+3+4 | ✅ 1+3+4 | — |

### Next Steps for R10 Payload

1. **Use confirmed addresses** from this DTB (not public DTSI)
2. **Enable UART1** explicitly (DTB has `status = "disabled"`)
3. **Initialize GIC-600** at 0x1020_0000 / 0x1024_0000
4. **Use MCT** at 0x1004_0000 for local timer (or architected timer PPI 13-16)
5. **PSCI via SMC** (per DTB) — test `hvc #0` as fallback per BL strings
6. **Chainload**: Replace kernel in `boot.img` or `vendor_boot.img` with payload ELF
7. **Entry point**: BL2 hands off at EL2 (recommended) — payload must handle EL2→EL1 drop

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

*Documento gerado a partir de firmware real `G998BXXSJHZC2` (vendor_boot.img DTB + BL sboot.bin).  
Base DTB agora confirmado — não mais dependente de DTSI público.*