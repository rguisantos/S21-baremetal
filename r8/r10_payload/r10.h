/* r10.h — R10: Real hardware payload for Exynos 2100 (Galaxy S21 Ultra)
 *
 * Runs at EL2 after BL2 handoff, drops to EL1, initializes hardware.
 * Uses confirmed addresses from vendor_boot.img DTB (G998BXXSJHZC2).
 */

#ifndef R10_H
#define R10_H

#include "r8lib.h"

typedef long s64;

#ifndef NULL
#define NULL ((void *)0)
#endif

#define ISB() asm volatile("isb" ::: "memory")

/* ================================================================
 * Exynos 2100 Hardware Addresses (from firmware DTB)
 * ================================================================ */

#define GICD_BASE         0x10200000UL  // GIC Distributor
#define GICR_BASE         0x10240000UL  // GIC Redistributor
#define GICR_STRIDE       0x20000       // Per-CPU redistributor stride
#define GICR_SGI_BASE     0x10000       // SGI/PPI offset within redistributor
#define MCT_BASE          0x10040000UL  // Multi-Core Timer
#define CHIPID_BASE       0x10000000UL  // Chip ID
#define UART1_BASE        0x10840000UL  // USI v2 UART (console)

/* GICD Registers */
#define GICD_CTLR         (GICD_BASE + 0x0000)
#define GICD_TYPER        (GICD_BASE + 0x0004)
#define GICD_IIDR         (GICD_BASE + 0x0008)
#define GICD_STATUSR      (GICD_BASE + 0x0010)
#define GICD_SETSPI_NSR   (GICD_BASE + 0x0040)
#define GICD_CLRSPI_NSR   (GICD_BASE + 0x0048)
#define GICD_IGROUPR      (GICD_BASE + 0x0080)
#define GICD_ISENABLER    (GICD_BASE + 0x0100)
#define GICD_ICENABLER    (GICD_BASE + 0x0180)
#define GICD_ISPENDR      (GICD_BASE + 0x0200)
#define GICD_ICPENDR      (GICD_BASE + 0x0280)
#define GICD_ISACTIVER    (GICD_BASE + 0x0300)
#define GICD_ICACTIVER    (GICD_BASE + 0x0380)
#define GICD_IPRIORITYR   (GICD_BASE + 0x0400)
#define GICD_ICFGR        (GICD_BASE + 0x0C00)
#define GICD_IGRPMODR     (GICD_BASE + 0x0D00)
#define GICD_SGIR         (GICD_BASE + 0x0F00)

/* GICR (Redistributor) Registers per CPU */
#define GICR_CTLR(base)       ((base) + 0x0000)
#define GICR_IIDR(base)       ((base) + 0x0004)
#define GICR_TYPER(base)      ((base) + 0x0008)
#define GICR_STATUSR(base)    ((base) + 0x0010)
#define GICR_WAKER(base)      ((base) + 0x0014)
#define GICR_MPIDR(base)      ((base) + 0x0020)
#define GICR_PROPBASER(base)  ((base) + 0x0070)
#define GICR_PENDBASER(base)  ((base) + 0x0078)

/* GICR SGI/PPI (per-CPU) */
#define GICR_SGI_BASE         0x10000
#define GICR_SGI_CTLR(base)      ((base) + GICR_SGI_BASE + 0x0000)
#define GICR_SGI_IIDR(base)      ((base) + GICR_SGI_BASE + 0x0004)
#define GICR_SGI_STATUSR(base)   ((base) + GICR_SGI_BASE + 0x0010)
#define GICR_SGI_IGROUPR(base)   ((base) + GICR_SGI_BASE + 0x0080)
#define GICR_SGI_ISENABLER(base) ((base) + GICR_SGI_BASE + 0x0100)
#define GICR_SGI_ICENABLER(base) ((base) + GICR_SGI_BASE + 0x0180)
#define GICR_SGI_ISPENDR(base)   ((base) + GICR_SGI_BASE + 0x0200)
#define GICR_SGI_ICPENDR(base)   ((base) + GICR_SGI_BASE + 0x0280)
#define GICR_SGI_ISACTIVER(base) ((base) + GICR_SGI_BASE + 0x0300)
#define GICR_SGI_ICACTIVER(base) ((base) + GICR_SGI_BASE + 0x0380)
#define GICR_SGI_IPRIORITYR(base) ((base) + GICR_SGI_BASE + 0x0400)
#define GICR_SGI_ICFGR(base)     ((base) + GICR_SGI_BASE + 0x0C00)
#define GICR_SGI_IGRPMODR(base)  ((base) + GICR_SGI_BASE + 0x0D00)

/* GICD_CTLR bits */
#define GICD_CTLR_EN_GRP0     (1 << 0)
#define GICD_CTLR_EN_GRP1NS   (1 << 1)
#define GICD_CTLR_EN_GRP1S    (1 << 2)
#define GICD_CTLR_ARE_NS      (1 << 4)   // Affinity Routing Enable (NS)
#define GICD_CTLR_ARE_S       (1 << 5)   // Affinity Routing Enable (S)
#define GICD_CTLR_DS          (1 << 6)   // Disable Security
#define GICD_CTLR_E1NWF       (1 << 7)

/* GICR_WAKER bits */
#define GICR_WAKER_PROCESSOR_SLEEP (1 << 1)
#define GICR_WAKER_CHILDREN_ASLEEP (1 << 2)

/* ICC_* System Register bits (GICv3 CPU interface) */
#define ICC_SRE_EL1_SRE     (1 << 0)
#define ICC_SRE_EL1_DIB     (1 << 1)
#define ICC_SRE_EL1_DFB     (1 << 2)

#define ICC_CTLR_EL1_EOImode   (1 << 0)
#define ICC_CTLR_EL1_CBPR      (1 << 1)
#define ICC_CTLR_EL1_PMHE      (1 << 6)

#define ICC_BPR1_EL1_MASK   0x7
#define ICC_PMR_EL1_MASK    0xFF
#define ICC_IAR1_EL1_INTID_MASK  0x00FFFFFF

#define ICC_IGRPEN1_EL1_GRP1NS  (1 << 0)
#define ICC_IGRPEN1_EL1_GRP1S   (1 << 1)

/* ICC_SGI1R_EL1 fields */
#define ICC_SGI1R_EL1_AFF3_SHIFT  24
#define ICC_SGI1R_EL1_AFF2_SHIFT  16
#define ICC_SGI1R_EL1_AFF1_SHIFT  8
#define ICC_SGI1R_EL1_RS_SHIFT    0

/* MCT (Multi-Core Timer) registers */
#define MCT_GLOBAL_CON    (MCT_BASE + 0x00)
#define MCT_GLOBAL_CNT    (MCT_BASE + 0x08)
#define MCT_INT_ENB       (MCT_BASE + 0x10)
#define MCT_INT_CSTAT     (MCT_BASE + 0x14)
#define MCT_LOCAL_CON(n)  (MCT_BASE + 0x100 + (n) * 0x100)
#define MCT_LOCAL_CNT(n)  (MCT_BASE + 0x108 + (n) * 0x100)
#define MCT_LOCAL_CMP(n)  (MCT_BASE + 0x110 + (n) * 0x100)
#define MCT_LOCAL_UPDATE(n) (MCT_BASE + 0x118 + (n) * 0x100)

#define MCT_GLOBAL_CON_EN      (1 << 0)
#define MCT_GLOBAL_CON_CLKSEL  (1 << 1)
#define MCT_LOCAL_CON_EN       (1 << 0)
#define MCT_LOCAL_CON_INTEN    (1 << 1)
#define MCT_LOCAL_CON_AUTO     (1 << 2)

/* USI v2 UART (Samsung Exynos UART) registers */
#define USI_UART_RX_FIFO      (UART1_BASE + 0x24)   // URXH
#define USI_UART_TX_FIFO      (UART1_BASE + 0x20)   // UTXH
#define USI_UART_CTRL         (UART1_BASE + 0x04)   // UCON
#define USI_UART_STATUS       (UART1_BASE + 0x10)   // UTRSTAT
#define USI_UART_BAUD         (UART1_BASE + 0x28)   // UBRDIV
#define USI_UART_LINE_CTRL    (UART1_BASE + 0x00)   // ULCON
#define USI_UART_FIFO_CTRL    (UART1_BASE + 0x08)   // UFCON
#define USI_UART_MODEM_CTRL   (UART1_BASE + 0x0C)   // UMCON
#define USI_UART_ERR_STATUS   (UART1_BASE + 0x14)   // UERSTAT
#define USI_UART_FIFO_STATUS  (UART1_BASE + 0x18)   // UFSTAT

/* USI v2 control registers (offset from UART base) */
#define USI_CON         0xC4
#define USI_OPTION      0xC8

#define USI_CTRL_TX_EN        (1 << 0)
#define USI_CTRL_RX_EN        (1 << 1)
#define USI_CTRL_UART_EN      (1 << 2)
#define USI_STATUS_TX_EMPTY   (1 << 1)
#define USI_STATUS_RX_FULL    (1 << 0)
#define USI_LINE_CTRL_WLEN_8  (3 << 0)
#define USI_LINE_CTRL_STOP_1  (0 << 2)
#define USI_LINE_CTRL_PAR_NONE (0 << 3)

/* PSCI function IDs (SMCCC) */
#define PSCI_VERSION          0x84000000
#define PSCI_CPU_ON           0x84000003
#define PSCI_CPU_OFF          0x84000004
#define PSCI_CPU_SUSPEND      0x84000007
#define PSCI_SYSTEM_RESET     0x84000009
#define PSCI_SYSTEM_OFF       0x84000008
#define PSCI_MIG_INFO_TYPE    0x8400000A

/* PSCI return codes */
#define PSCI_SUCCESS          0
#define PSCI_NOT_SUPPORTED    -1
#define PSCI_INVALID_PARAM    -2
#define PSCI_DENIED           -3
#define PSCI_ALREADY_ON       -4
#define PSCI_ON_PENDING       -5
#define PSCI_INTERNAL_FAIL    -6
#define PSCI_NOT_PRESENT      -7
#define PSCI_DISABLED         -8
#define PSCI_INVALID_ADDRESS  -9

/* Exception levels */
#define EL3 3
#define EL2 2
#define EL1 1
#define EL0 0

/* Memory layout (identity mapped) */
#define DRAM_BASE             0x80000000UL
#define DRAM_SIZE             0x80000000UL  // 2 GB (adjust per device)
#define PAYLOAD_LOAD_ADDR     0x80080000UL  // Typical kernel load address

/* Page table constants */
#define PAGE_SHIFT            12
#define PAGE_SIZE             (1 << PAGE_SHIFT)
#define BLOCK_SHIFT           21
#define BLOCK_SIZE            (1 << BLOCK_SHIFT)  // 2 MB

/* MAIR attributes */
#define MAIR_DEVICE_nGnRnE    0x00  // AttrIdx 0: Device-nGnRnE
#define MAIR_NORMAL_NC        0x44  // AttrIdx 1: Normal Non-Cacheable
#define MAIR_NORMAL_WB        0xFF  // AttrIdx 2: Normal Write-Back

/* TCR_EL1 for 48-bit VA, 4KB pages, 2-level (L0+L1) */
#define TCR_EL1_T0SZ(x)       ((64 - (x)) << 0)
#define TCR_EL1_T1SZ(x)       ((64 - (x)) << 16)
#define TCR_EL1_IRGN0_WB      (1 << 8)
#define TCR_EL1_ORGN0_WB      (1 << 10)
#define TCR_EL1_SH0_INNER     (3 << 12)
#define TCR_EL1_TG0_4K        (0 << 14)
#define TCR_EL1_IRGN1_WB      (1 << 24)
#define TCR_EL1_ORGN1_WB      (1 << 26)
#define TCR_EL1_SH1_INNER     (3 << 28)
#define TCR_EL1_TG1_4K        (2 << 30) /* TG1=10b: 4 KiB */

/* SCTLR_EL1 */
#define SCTLR_M               (1 << 0)   // MMU enable
#define SCTLR_C               (1 << 2)   // Cache enable
#define SCTLR_I               (1 << 12)  // I-cache enable
#define SCTLR_SA0             (1 << 4)   // Stack alignment EL0
#define SCTLR_SA              (1 << 3)   // Stack alignment EL1

/* Function prototypes */
void r10_entry(void);
void el2_to_el1_drop(void);
void mmu_init(void);
void gic_init(void);
void gic_cpu_interface_init(void);
void gic_enable_irq(u32 irq);
void gic_disable_irq(u32 irq);
void gic_set_priority(u32 irq, u8 priority);
u32 gic_ack_irq(void);
void gic_eoi(u32 irq);
void gic_send_sgi(u32 sgi_id, u32 target_mask, u32 aff1, u32 aff2, u32 aff3);
void uart_init(void);
void mct_init(void);
void timer_init(void);
s64 psci_call(u64 fn, u64 arg0, u64 arg1, u64 arg2);
void uart_putc(char c);
void uart_puts(const char *s);
void uart_puthex(u64 v);
char uart_getc(void);

#endif /* R10_H */