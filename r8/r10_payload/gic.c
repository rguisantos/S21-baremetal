/* gic.c — R10: GIC-600 (GICv3) driver using ICC_* system registers
 *
 * Based on ARM GICv3 architecture specification and Samsung DTB:
 *   GICD: 0x1020_0000 (Distributor)
 *   GICR: 0x1024_0000 (Redistributor, 4 CPUs × 0x20000)
 *   ITS:  0x1028_0000 (Interrupt Translation Service)
 *
 * CPU topology from DTB:
 *   cluster0 (A55): CPU 0-3 (MPIDR Aff0 = 0x00, 0x01, 0x02, 0x03)
 *   cluster1 (A78): CPU 4-6 (MPIDR Aff0 = 0x04, 0x05, 0x06)
 *   cluster2 (X1):  CPU 7   (MPIDR Aff0 = 0x07)
 */

#include "r10.h"

/* GIC-600 Memory Map (from DTB) */
#define GICD_BASE         0x10200000UL
#define GICR_BASE         0x10240000UL
#define GICR_STRIDE       0x20000     // Per-CPU redistributor stride
#define GICR_SGI_BASE     0x10000     // SGI/PPI offset within redistributor

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
#define GICR_SETLPIR(base)    ((base) + 0x0040)
#define GICR_CLRLPIR(base)    ((base) + 0x0048)
#define GICR_PROPBASER(base)  ((base) + 0x0070)
#define GICR_PENDBASER(base)  ((base) + 0x0078)

/* GICR SGI/PPI (per-CPU) */
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
#define GICD_CTLR_E1NWF       (1 << 7)   // Enable Group 1 Not Wire-Frame

/* GICR_WAKER bits */
#define GICR_WAKER_PROCESSOR_SLEEP (1 << 1)
#define GICR_WAKER_CHILDREN_ASLEEP (1 << 2)

/* ICC_* System Register Access (GICv3) */
#define ICC_SRE_EL1_SRE     (1 << 0)   // System Register Enable
#define ICC_SRE_EL1_DIB     (1 << 1)   // Disable IRQ Bypass
#define ICC_SRE_EL1_DFB     (1 << 2)   // Disable FIQ Bypass

#define ICC_CTLR_EL1_EOImode   (1 << 0)   // EOI mode
#define ICC_CTLR_EL1_CBPR      (1 << 1)   // Common Binary Point
#define ICC_CTLR_EL1_PMHE      (1 << 6)   // Priority Mask Hint Enable

/* ICC_BPR1_EL1: Binary Point Register (Group 1) */
#define ICC_BPR1_EL1_MASK   0x7

/* ICC_PMR_EL1: Priority Mask Register */
#define ICC_PMR_EL1_MASK    0xFF

/* ICC_IAR1_EL1: Interrupt Acknowledge Register */
#define ICC_IAR1_EL1_INTID_MASK  0x00FFFFFF

/* ICC_EOIR1_EL1: End of Interrupt Register */

/* ICC_IGRPEN1_EL1: Interrupt Group 1 Enable */
#define ICC_IGRPEN1_EL1_GRP1NS  (1 << 0)
#define ICC_IGRPEN1_EL1_GRP1S   (1 << 1)

/* ICC_SGI1R_EL1: SGI Generation Register 1 */
#define ICC_SGI1R_EL1_AFF3_SHIFT  24
#define ICC_SGI1R_EL1_AFF2_SHIFT  16
#define ICC_SGI1R_EL1_AFF1_SHIFT  8
#define ICC_SGI1R_EL1_RS_SHIFT    0

/* GICR_TYPER bits */
#define GICR_TYPER_LAST      (1UL << 4)
#define GICR_TYPER_PROC_NUM  (0xFFFFUL << 8)

static inline u64 mrs_icc_sre_el1(void)  { return MRS(icc_sre_el1); }
static inline void msr_icc_sre_el1(u64 v) { MSR(icc_sre_el1, v); }
static inline u64 mrs_icc_ctlr_el1(void) { return MRS(icc_ctlr_el1); }
static inline void msr_icc_ctlr_el1(u64 v) { MSR(icc_ctlr_el1, v); }
static inline u64 mrs_icc_pmr_el1(void)  { return MRS(icc_pmr_el1); }
static inline void msr_icc_pmr_el1(u64 v) { MSR(icc_pmr_el1, v); }
static inline u64 mrs_icc_bpr1_el1(void) { return MRS(icc_bpr1_el1); }
static inline void msr_icc_bpr1_el1(u64 v) { MSR(icc_bpr1_el1, v); }
static inline u64 mrs_icc_iar1_el1(void) { return MRS(icc_iar1_el1); }
static inline void msr_icc_eoir1_el1(u64 v) { MSR(icc_eoir1_el1, v); }
static inline u64 mrs_icc_igrpen1_el1(void) { return MRS(icc_igrpen1_el1); }
static inline void msr_icc_igrpen1_el1(u64 v) { MSR(icc_igrpen1_el1, v); }
static inline void msr_icc_sgi1r_el1(u64 v) { MSR(icc_sgi1r_el1, v); }
static inline u64 mrs_icc_igrpen0_el1(void) { return MRS(icc_igrpen0_el1); }
static inline void msr_icc_igrpen0_el1(u64 v) { MSR(icc_igrpen0_el1, v); }

static inline u32 gicd_read(u32 reg) { return mmio_read32(GICD_BASE + reg); }
static inline void gicd_write(u32 reg, u32 val) { mmio_write32(GICD_BASE + reg, val); }

static u64 get_redist_base(u32 cpu_id)
{
    return GICR_BASE + (u64)cpu_id * GICR_STRIDE;
}

static inline u32 gicr_read(u64 base, u32 reg) { return mmio_read32(base + reg); }
static inline void gicr_write(u64 base, u32 reg, u32 val) { mmio_write32(base + reg, val); }

/* Initialize GIC-600 Distributor */
void gic_init(void)
{
    u32 typer = gicd_read(GICD_TYPER);
    u32 cpu_count = ((typer >> 5) & 0x7) + 1;
    u32 spi_count = ((typer & 0x1F) + 1) * 32;
    
    uart_puts("GIC-600: TYPER="); uart_puthex(typer); uart_putc('\n');
    uart_puts("GIC-600: CPU interfaces="); uart_puthex(cpu_count); uart_puts(" SPIs="); uart_puthex(spi_count); uart_putc('\n');

    /* 1. Disable distributor */
    gicd_write(GICD_CTLR, 0);
    
    /* 2. Configure GICD_CTLR: ARE_NS + DS + Enable Group 0 + Group 1 NS */
    u32 ctlr = GICD_CTLR_ARE_NS | GICD_CTLR_DS | GICD_CTLR_EN_GRP0 | GICD_CTLR_EN_GRP1NS;
    gicd_write(GICD_CTLR, ctlr);
    
    /* 3. All SPIs -> Group 1 Non-secure, level-triggered */
    for (int i = 32; i < spi_count; i += 32) {
        gicd_write(GICD_IGROUPR + i/32*4, 0xFFFFFFFF);     // IGROUPR: Group 1
        gicd_write(GICD_ICFGR + i/16*4, 0x55555555);       // ICFGR: level-triggered
        gicd_write(GICD_IGRPMODR + i/32*4, 0x00000000);    // IGRPMODR: Group 1 NS
    }
    
    /* 4. Default priority for all SPIs */
    for (int i = 32; i < spi_count; i++) {
        gicd_write(GICD_IPRIORITYR + i, 0xA0);  // Priority 0xA0 (mid)
    }
    
    /* 5. Enable distributor */
    gicd_write(GICD_CTLR, ctlr | GICD_CTLR_EN_GRP0 | GICD_CTLR_EN_GRP1NS);
    
    /* 6. Initialize each CPU's redistributor */
    for (int cpu = 0; cpu < cpu_count; cpu++) {
        u64 rbase = get_redist_base(cpu);
        
        /* Wake up redistributor */
        u32 waker = gicr_read(rbase, GICR_WAKER(rbase));
        waker &= ~GICR_WAKER_PROCESSOR_SLEEP;
        gicr_write(rbase, GICR_WAKER(rbase), waker);
        
        /* Wait for children awake */
        int timeout = 100000;
        while ((gicr_read(rbase, GICR_WAKER(rbase)) & GICR_WAKER_CHILDREN_ASLEEP) && timeout--)
            ;
        
        /* Enable Group 0 and Group 1 NS in redistributor */
        gicr_write(rbase, GICR_CTLR(rbase), 0x3);  // GICR_CTLR
    }
    
    /* 7. Initialize CPU interface via ICC_* system registers */
    gic_cpu_interface_init();
    
    uart_puts("GIC-600 initialized\n");
}

/* Per-CPU interface init via ICC_* system registers */
void gic_cpu_interface_init(void)
{
    /* 1. Enable system register access (ICC_SRE_EL1.SRE = 1) */
    u64 sre = mrs_icc_sre_el1();
    sre |= ICC_SRE_EL1_SRE;
    msr_icc_sre_el1(sre);
    ISB();
    
    /* 2. Configure CPU interface control */
    u64 ctlr = mrs_icc_ctlr_el1();
    ctlr |= ICC_CTLR_EL1_EOImode | ICC_CTLR_EL1_CBPR;
    msr_icc_ctlr_el1(ctlr);
    
    /* 3. Set priority mask to allow all (0xFF = lowest priority) */
    msr_icc_pmr_el1(0xFF);
    
    /* 4. Set binary point register (Group 1) */
    msr_icc_bpr1_el1(0x3);  // 8 priority bits, no preemption
    
    /* 5. Enable Group 1 Non-secure interrupts */
    u64 igrpen1 = mrs_icc_igrpen1_el1();
    igrpen1 |= ICC_IGRPEN1_EL1_GRP1NS;
    msr_icc_igrpen1_el1(igrpen1);
    
    /* 6. Enable Group 0 interrupts */
    u64 igrpen0 = mrs_icc_igrpen0_el1();
    igrpen0 |= 1;
    msr_icc_igrpen0_el1(igrpen0);
    
    uart_puts("GIC CPU interface initialized (ICC_*)\n");
}

/* Enable IRQ via Distributor + CPU interface */
void gic_enable_irq(u32 irq)
{
    if (irq < 32) {
        /* SGI/PPI - per CPU via redistributor SGI */
        u32 cpu = get_current_cpu();
        u64 rbase = get_redist_base(cpu);
        gicr_write(rbase, GICR_SGI_ISENABLER(rbase), 1 << irq);
    } else {
        /* SPI - via Distributor */
        gicd_write(GICD_ISENABLER + (irq/32)*4, 1 << (irq%32));
    }
}

/* Disable IRQ */
void gic_disable_irq(u32 irq)
{
    if (irq < 32) {
        u32 cpu = get_current_cpu();
        u64 rbase = get_redist_base(cpu);
        gicr_write(rbase, GICR_SGI_ICENABLER(rbase), 1 << irq);
    } else {
        gicd_write(GICD_ICENABLER + (irq/32)*4, 1 << (irq%32));
    }
}

/* Set IRQ priority */
void gic_set_priority(u32 irq, u8 priority)
{
    if (irq < 32) {
        u32 cpu = get_current_cpu();
        u64 rbase = get_redist_base(cpu);
        gicr_write(rbase, GICR_SGI_IPRIORITYR(rbase) + irq, priority);
    } else {
        gicd_write(GICD_IPRIORITYR + irq, priority);
    }
}

/* Acknowledge interrupt - returns INTID */
u32 gic_ack_irq(void)
{
    return mrs_icc_iar1_el1() & ICC_IAR1_EL1_INTID_MASK;
}

/* End of Interrupt */
void gic_eoi(u32 irq)
{
    msr_icc_eoir1_el1(irq);
}

/* Send SGI to target CPUs */
void gic_send_sgi(u32 sgi_id, u32 target_mask, u32 aff1, u32 aff2, u32 aff3)
{
    /* ICC_SGI1R_EL1: TargetList[15:0], Aff1[23:16], INTID[27:24],
     * Aff2[39:32], IRM[40], RS[47:44], Aff3[55:48]. */
    if (sgi_id > 15 || (target_mask & ~0xffffU)) return;
    u64 sgi1r = ((u64)(aff3 & 0xff) << 48)
              | ((u64)(aff2 & 0xff) << 32)
              | ((u64)(sgi_id & 0xf) << 24)
              | ((u64)(aff1 & 0xff) << 16)
              | (u64)(target_mask & 0xffffU);
    asm volatile("dsb ishst" ::: "memory");
    msr_icc_sgi1r_el1(sgi1r);
    ISB();
}