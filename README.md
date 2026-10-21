# Kit R8+R9 v8 — Bring-up bare-metal + microkernel no QEMU (completo)

Kit autossuficiente dos módulos R8 (bring-up AArch64 no QEMU `virt`) e R9
(microkernel: EL0, SVC, troca de contexto, preempção), com regressão
automatizada: **R8A / R8B / R8C / R9 — 4/4 PASS** no mesmo build
(`make regress`).

Ambiente 100% userspace: nada é instalado como root. O cross-toolchain e o
QEMU vêm extraídos de .debs Debian dentro de `tools/root`, com os .debs
originais em `tools/debs` (para re-bootstrap offline).

## Estrutura do pacote

    README.md            este arquivo
    r8/
      Makefile           build + run (r8a/r8b/r8c/r9) + regress
      common/            start.S, sys.S, vectors.S, uart.c, printf.c,
                         exc.c, util.c, r8lib.h, linker.ld
      r8a_mmu/mmu.c       Stage-1: MAIR, tabelas L0–L3, SCTLR_EL1.M, faults
      r8b_el/el.c         escada EL3→EL2→EL1 (SCR_EL3 + ERET) e muro EC=0x00
      r8c_gic/            VBAR 16 slots, ESR, GICv3, timer CNTP (INTID 30)
      r9_micro/           MICROKERNEL: EL0 + SVC + troca de contexto +
                          preempção por timer (r9.h, vectors.S, main.c,
                          sched.c, syscall.c, tasks.c, gic.c, timer.c)
      build/              ELF prontos + disassembly
      logs/               evidência de cada validação e da regressão
    scripts/
      bootstrap_tools.sh  reconstroi tools/ a partir dos .debs (sem root)
      parse_fdt.py         parser de DTB (forense de endereços)
      regress.sh           suíte: roda os 4 módulos e confere assinaturas PASS
    tools/
      debs/               .debs originais (QEMU 10.0.13, gcc-aarch64 14.2.0)
      root/               sysroot extraído (binários, libs e dados do QEMU)

## Requisitos

- Linux x86_64 com `make`, `dpkg`/`dpkg-deb` (o bootstrap usa `dpkg -x`).
- Nenhum pacote instalado como root; nada fora deste diretório.

## Como rodar

1. Extraia. Em `/home/z/my-project` nada mais a fazer (o Makefile usa
   `TOOLS := /home/z/my-project/tools/root`). Para outro caminho:

       make TOOLS=/caminho/do/kit/tools/root all
       make TOOLS=/caminho/do/kit/tools/root run_r9

2. Build completo + disassembly:

       cd r8 && make all

3. Rodar módulos (timeout externo recomendado; os módulos entram em park
   de propósito — exit 124 é esperado no harness):

       timeout 20 make run_r8a   # -M virt,virtualization=on
       timeout 20 make run_r8b   # -M virt,secure=on,virtualization=on
       timeout 35 make run_r8c   # -M virt,gic-version=3,virtualization=on
       timeout 35 make run_r9    # -M virt,gic-version=3,virtualization=on

4. Regressão completa (4 módulos, logs em r8/logs/regress_*.log):

       make regress

## Assinaturas de PASS

- **R8A PASS — traducao, alias e faults sob controle**
  L0 translation fault + Data Abort de permissão no L3 (WnR=1, DFSC=0x0f).
- **R8B PASS — a escada desce, mas nao sobe sem permissao**
  EL3 → SCR_EL3 → [EL2] → [EL1] via ERET; `msr scr_el3` no EL1 → muro EC=0x00.
- **R8C PASS — 5 ticks: preempcao real**
  GICD_TYPER real, GICD_CTLR readback 0x53, 5 IRQs do CNTP (INTID 30).
- **R9 PASS — EL0 + SVC + troca de contexto + preempcao**
  Tarefa A (3 YIELDs voluntários) e B (3 preempções SEM cooperar) no EL0,
  com pilhas próprias (SPs diferentes provados no console); SVC #1 com
  validação de ponteiro (NULL → -14, MMIO da UART → -14); o tick do timer
  troca de tarefa de verdade (não só imprime).

## Verdades físicas registradas nos fontes (com fontes citadas)

- `SCR_EL3`: NS=bit0, RW=bit10, EEL2=bit18, RES1=bits 4,5 (QEMU cpu.h,
  TF-A arch.h, DDI0487). Reset do QEMU virt lê 0x30 (só os RES1).
- `virtualization=on` é obrigatório no `-M virt`: sem ele o `-cpu max`
  nasce sem EL2 e qualquer ERET para EL2 é ilegal.
- GICv3 no virt: **GICD=0x08000000** (v2 E v3), ITS=0x08080000 (armadilha
  documentada), GICR=0x080A0000. Sem EL3, DS=1: só bits 0,1 gravam no CTLR.
- INTID 30 = PPI do CNTP; `cnthctl_el2` precisa de EL1PCEN|EL1PCTEN.
- **[v8]** ERET **não** restaura SP_EL0 — o retorno de EL0 exige gravar
  `msr sp_el0` à mão a partir do frame (DDI0487 B1.9.1).
- **[v8]** Exceção vinda de EL menor força SPSel=1: o handler roda no
  SP_EL1 — por isso cada tarefa tem uma PILHA DE KERNEL própria e o frame
  de exceção mora nela ("o contexto é a pilha").
- **[v8]** O frame do R8 tinha bug latente: x29/x30 eram restaurados de
  slots nunca gravados (232/240) — sobrevivia por sorte estrutural. Corrigido
  no common/vectors.S; revalidado com regressão 4/4.
- **[v8]** Sem MMU, a "janela do usuário" [0x40080000, __bss_end) é
  CONVENÇÃO do kernel (validação de ponteiro no SVC). Com page tables por
  tarefa (próximo passo) a mesma validação passa a ser física.

## Reproduzir o ambiente do zero

    ./scripts/bootstrap_tools.sh   # baixa/extraí QEMU + gcc em tools/ (userspace)

## Ordem didática recomendada

1. `r8a` — o mapa: MAIR, tabelas, MMU on, ler faults.
2. `r8b` — o privilégio: escada EL3→EL2→EL1 e por que ela não sobe.
3. `r8c` — o tempo: vetores, GICv3 e interrupção de verdade.
4. `r9`   — o sistema: EL0 + SVC + troca de contexto + preempção.

Fronteira atual: o próximo passo natural é isolamento por MMU (page tables
por tarefa, janela virando lei física), EL0 com páginas de usuário e
talvez SMP via PSCI — ou a portabilidade para bancada real
(RK3568/DAYU200: BSP, U-Boot chainloading, serial física).
## Exynos 2100 (Galaxy S21 Ultra SM-G998B) — Verdades físicas do firmware real

O kernel público do Exynos 2100 (`exynos2100.dtsi`) expõe o mapa de hardware
real — **diferente do QEMU `virt`**:

| Componente | QEMU `virt` | Exynos 2100 Real | Fonte |
|------------|-------------|------------------|-------|
| GICD (Distributor) | 0x08000000 | **0x10200000** | `exynos2100.dtsi` `gic` node |
| GICR (Redistributor) | 0x080A0000 | **0x10240000** | `exynos2100.dtsi` `gic` node |
| MCT (Local Timer) | — | **0x10040000** | `exynos2100.dtsi` `mct` node |
| Chip ID | — | **0x10000000** | `exynos2100.dtsi` `chipid` node |
| Oscilador de ref. | — | **26 MHz** | `exynos2100.dtsi` `clocks` |
| initrd (kernel) | — | **0x84000000** | boot header padrão |
| UART Console | PL011 @ 0x09000000 | **uart@10840000** | `exynos2100.dtsi` `uart1` |
| UART compat | `arm,pl011` | **`samsung,exynos-uart`** (USI v2) | `exynos2100.dtsi` |
| UART IRQ (SPI) | INTID 33 (PL011) | **INTID 0x215 = 533** | `exynos2100.dtsi` `interrupts` |

> **IMPORTANTE**: Não copiar endereços do QEMU para o hardware real. O
> GIC-600 no Exynos vive em 0x1020_0000 (base física), não em 0x0800_0000.
> O timer local é MCT (Memory Controller Timer), não o architected timer
> PPI do QEMU. A UART é Samsung USI v2, não PL011.

### Firmware Extraído (G998BXXSJHZC2)

| Artefato | Tamanho | Conteúdo |
|----------|---------|----------|
| `boot.img` | 64 MB | Ramdisk + overlay DTB (sem kernel binary) |
| `dtbo.img` | 8 MB | Overlays de placa (bateria, câmeras, sensores, PMIC) |
| `ramdisk` | 1.5 MB | init, fstab.exynos2100, SELinux policy |
| `kernel.config` | 203 KB | Linux 5.4.242, clang 11.0.1 |

**Kernel config confirmado**:
```
CONFIG_SOC_EXYNOS2100=y
CONFIG_ARM_GIC_V3=y / CONFIG_ARM_GIC_V3_ITS=y
CONFIG_CLKSRC_EXYNOS_MCT=m
CONFIG_USI_V2=m
CONFIG_ARM_PSCI_FW=y
```

### BL Firmware (Bootloader) — `BL_G998BXXSJHZC2_...tar.md5` (10.4 MB)

| Componente | Arquivo | Descoberta chave |
|------------|---------|------------------|
| **TF-A / BL2** | `sboot.bin` | v1.5 (Athens/Exynos2100), PSCI **HVC**, GICv3, EL3 monitor, libfdt completo |
| **TEEGRIS** | `tzar.img` + `tzsw.img` | v4/v3.7, Secure OS (OP-TEE based) |
| **Harx** | `harx.bin` | Hypervisor, BL31 setup, S2MPU |
| **AVB** | `vbmeta.img` | Partitions: recovery, dtbo, boot1, vendor_boot, system, vendor, ... |

> **Sem U-Boot** — Samsung usa cadeia proprietária BL2 → Kernel. Ponto de chainload: após BL2, antes do kernel (EL2/EL1).
> **Base DTB** — Extraído do `vendor_boot.img` do AP (offset 0xb77040, 390 KB). Confirma todos os endereços.
> **PSCI** — DTB diz SMC, BL strings dizem HVC. Testar ambos.

### DTB Base Confirmado (vendor_boot.img)

| Componente | Endereço | Detalhes |
|------------|----------|----------|
| **GICD** | 0x1020_0000 | `arm,gic-v3`, redist 0x1024_0000 |
| **MCT** | 0x1004_0000 | `samsung,exynos4210-mct` |
| **ChipID** | 0x1000_0000 | `samsung,exynos2100-chipid` |
| **UART1 (console)** | 0x1084_0000 | `samsung,exynos-uart` (USI v2), **SPI 533**, `status=disabled` |
| **PSCI** | — | `arm,psci-1.0`, method=smc |
| **Timer arch** | PPI 13-16 | `arm,armv8-timer`, 26 MHz |
| **CPU Topology** | 3 clusters | 4×A55 (0-3), 3×A78 (4-6), 1×X1 (7) |

### Árvores de kernel públicas para referência

- **Universal Exynos 2100**: https://github.com/exynos2100/android_kernel_samsung_universal2100
- **Comunidade Exynos Republic**: https://github.com/exynos-republic/android_kernel_samsung_universal2100
- **Samsung Open Source**: https://opensource.samsung.com/ (buscar por `G998BXXSJHZC2`)

### ProtonPlus Kernel (v6.1.0-KSU)

From extracted `vendor_boot.img` DTB (2026-01-25):

| Component | Address | Details |
|-----------|---------|---------|
| **GIC-600** | `0x1020_0000` / `0x1024_0000` | `arm,gic-v3`, 3 cells |
| **UART1** | `0x1084_0000` | `samsung,exynos-uart`, SPI 533, disabled |
| **MCT Timer** | `0x1004_0000` | `samsung,exynos4210-mct`, 12 channels |
| **CPU Topology** | 3 clusters | 4×A55, 3×A78, 1×X1 |
| **Clock Ctrl** | `0x1A33_0000` | Samsung clock controller |
| **Initrd** | `0x8400_0000` | 2MB |

**Boot Args:** `clocksource=arch_sys_counter nr_cpus=8 androidboot.hardware=exynos2100`

> **Note**: ProtonPlus `Image` is Windows PE (UEFI), not Linux kernel. `vendor_boot.img` contains valid Exynos 2100 DTB.

### Live Device Diagnostic Dump (SM-G998B, G998BXXSJHZC2)

From `coleta/` directory — live device diagnostic dump:

| Property | Value |
|----------|-------|
| **Model** | SM-G998B (Galaxy S21 Ultra) |
| **Bootloader** | G998BXXSJHZC2 |
| **Kernel** | 5.4.242-30958140-abG998BXXSJHZC2 |
| **Android** | 15 (AP3A.240905.015.A2) |
| **Build Date** | Mon Mar 9 19:20:30 KST 2026 |
| **CSC** | ZTO (Brazil) |
| **Bootloader Locked** | Yes (ro.boot.flash.locked=1) |
| **VBMeta** | AVB 1.1, locked, SHA256 |

### Hardware Verified (from live device /proc/interrupts)

| Component | Address | IRQ | Details |
|-----------|---------|-----|---------|
| **GIC-600** | 0x1020_0000 / 0x1024_0000 | - | arm,gic-v3, 3 cells |
| **UART1** | 0x1084_0000 | SPI 565 | samsung,exynos-uart (USI v2) |
| **MCT** | 0x1004_0000 | SPI 975-986 | samsung,exynos4210-mct |
| **DECON** (Display) | 0x19f0_0000 | SPI 280-295 | exynos-decon |
| **UFS** | - | SPI 302 | ufshcd |
| **PCIe** | - | SPI 389 | exynos-pcie |
| **PMIC** (s2mps23) | - | 34, 417-457 | s2mps23-irq |
| **PMIC** (max77705) | - | 493-505 | max77705 |
| **MFC** (Video) | - | 486-487 | exynos-mfc |
| **Touch** | - | 461-462 | qbt_finger |

### Memory (from /proc/meminfo)
| Metric | Value |
|--------|-------|
| **MemTotal** | 10,829,472 kB (~10.3 GB) |
| **CMA Total** | 249,856 kB (244 MB) |
| **Swap Total** | 8,388,604 kB (8 GB) |

### Boot Args (from `/proc/cmdline`)
```
clocksource=arch_sys_counter nr_cpus=8 androidboot.hardware=exynos2100
log_buf_len=256K irqaffinity=0 loop.max_part=7
rcupdate.rcu_expedited=1 s3c2410_wdt.tmr_atboot=1
s3c2410_wdt.tmr_margin=80 printk.devkmsg=on
cgroup.memory=nokmem swiotlb=noforce
```

### Partition Layout (from /dev/block/by-name)
| Name | Block Device | Purpose |
|------|-------------|---------|
| **boot** | sda13 | Kernel + ramdisk + DTB |
| **dtbo** | sda11 | DTB overlays |
| **vendor_boot** | sda14 | Vendor boot (DTB + ramdisk) |
| **recovery** | sda15 | Recovery kernel |
| **vbmeta** | sda23 | AVB metadata |
| **super** | sda28 | Dynamic partitions |
| **userdata** | sda34 | User data (225 GB) |
| **efs** | sda1 | Encrypted file system |
