/* Single-CPU GICv3 handoff driver. Distributor/security/SPI configuration
 * belongs to firmware. See Samsung drivers/irqchip/irq-gic-v3.c for affinity
 * matching and the RD+SGI(+VLPI) frame walk. No logical-CPU/Aff0 indexing. */
#include "r10.h"

#define GICR_TYPER_LAST (1ULL << 4)
#define GICR_TYPER_VLPIS (1ULL << 1)
#define GICR_RWP (1U << 3)
#define GIC_POLL_LIMIT 100000U
static u64 boot_redist;
static u64 boot_affinity;

static u32 mpidr_affinity(u64 mpidr)
{
    return (u32)(mpidr & 0xffffff) | (u32)((mpidr >> 8) & 0xff000000);
}

/* All MMIO arguments are absolute addresses, including register macros. */
static u64 find_redist(u64 base, u64 size, u64 stride, u64 mpidr)
{
    if ((base & 0xffff) || size < 0x20000 || base + size < base)
        return 0;
    if (stride && (stride < 0x20000 || (stride & 0xffff)))
        return 0;
    u64 end = base + size;
    for (u64 rd = base; rd <= end - 0x20000;) {
        u32 arch = (mmio_read32(rd + 0xffe8) >> 4) & 0xf;
        if (arch != 3 && arch != 4) return 0;
        u64 typer = *(volatile u64 *)GICR_TYPER(rd);
        if ((u32)(typer >> 32) == mpidr_affinity(mpidr))
            return rd;
        if (typer & GICR_TYPER_LAST)
            break;
        u64 step = stride ? stride : ((typer & GICR_TYPER_VLPIS) ? 0x40000 : 0x20000);
        if (step > end - rd)
            break;
        rd += step;
    }
    return 0;
}

static int wait_clear(u64 address, u32 mask)
{
    for (u32 n = 0; n < GIC_POLL_LIMIT; ++n)
        if (!(mmio_read32(address) & mask)) return 0;
    return -1;
}

static u64 current_redist(void)
{
    return boot_affinity == (MRS(mpidr_el1) & 0xff00ffffffULL) ? boot_redist : 0;
}

int gic_init_region(u64 dist, u64 redist, u64 size, u64 stride)
{
    boot_redist = 0;
    /* This initial stage never modifies GICD_CTLR. Require inherited affinity
     * routing and Group 1 delivery. Bit 0 is EnableGrp1NS in the NS view when
     * DS=0; bit 1 is EnableGrp1 in the single-security-state view (DS=1). */
    if (!dist || (dist & 0xffff)) return -1;
    u32 ctlr = mmio_read32(dist);
    u32 enable = (ctlr & GICD_CTLR_DS) ? (1U << 1) : (1U << 0);
    if (!(ctlr & (1U << 4)) || !(ctlr & enable)) return -1;
    u64 mpidr = MRS(mpidr_el1);
    u64 rd = find_redist(redist, size, stride, mpidr);
    if (!rd) return -1;
    u32 waker = mmio_read32(GICR_WAKER(rd));
    mmio_write32(GICR_WAKER(rd), waker & ~GICR_WAKER_PROCESSOR_SLEEP);
    if (wait_clear(GICR_WAKER(rd), GICR_WAKER_CHILDREN_ASLEEP)) return -1;
    boot_affinity = mpidr & 0xff00ffffffULL;
    boot_redist = rd;
    if (gic_cpu_interface_init()) { boot_redist = 0; return -1; }
    return 0;
}

int gic_init(void)
{
    /* Firmware DTB range, not range / CPU-count as a fabricated stride.
     * Platform integration must still verify these against the live DTB. */
    return gic_init_region(GICD_BASE, GICR_BASE, 0x200000, 0);
}

int gic_cpu_interface_init(void)
{
    MSR(icc_sre_el1, MRS(icc_sre_el1) | ICC_SRE_EL1_SRE);
    ISB();
    if (!(MRS(icc_sre_el1) & ICC_SRE_EL1_SRE)) return -1;
    /* Mode 0: EOIR performs priority drop AND deactivation. Fail if firmware
     * makes this bit read-only as 1, rather than silently omitting DIR. */
    MSR(icc_ctlr_el1, MRS(icc_ctlr_el1) & ~((u64)ICC_CTLR_EL1_EOImode));
    ISB();
    if (MRS(icc_ctlr_el1) & ICC_CTLR_EL1_EOImode) return -1;
    MSR(icc_pmr_el1, 0xff);
    MSR(icc_bpr1_el1, 0);
    MSR(icc_igrpen1_el1, 1);
    ISB();
    return (MRS(icc_igrpen1_el1) & 1) ? 0 : -1;
}

/* Only private interrupts are supported by this stage. No SPI ownership,
 * routing or trigger policy is assumed. Firmware must assign Group 1 NS. */
int gic_enable_irq(u32 irq)
{
    u64 rd = current_redist();
    if (!rd || irq >= 32) return -1;
    if (!(mmio_read32(GICR_SGI_IGROUPR(rd)) & (1U << irq))) return -1;
    mmio_write32(GICR_SGI_ISENABLER(rd), 1U << irq);
    R10_DSB_SY();
    if (wait_clear(GICR_CTLR(rd), GICR_RWP)) return -1;
    return (mmio_read32(GICR_SGI_ISENABLER(rd)) & (1U << irq)) ? 0 : -1;
}

void gic_disable_irq(u32 irq)
{
    u64 rd = current_redist();
    if (!rd || irq >= 32) return;
    mmio_write32(GICR_SGI_ICENABLER(rd), 1U << irq);
    R10_DSB_SY();
    if (wait_clear(GICR_CTLR(rd), GICR_RWP)) park();
}

void gic_set_priority(u32 irq, u8 priority)
{
    u64 rd = current_redist();
    if (rd && irq < 32)
        *(volatile u8 *)(GICR_SGI_IPRIORITYR(rd) + irq) = priority;
}

u32 gic_ack_irq(void)
{
    u32 irq = MRS(icc_iar1_el1) & ICC_IAR1_EL1_INTID_MASK;
    ISB();
    return irq;
}

void gic_eoi(u32 irq)
{
    if (irq >= 1020) return; /* No EOI for special/spurious INTIDs. */
    MSR(icc_eoir1_el1, irq);
    ISB();
}

void gic_send_sgi(u32 id, u32 mask, u32 aff1, u32 aff2, u32 aff3)
{
    if (id > 15 || (mask & ~0xffffU)) return;
    u64 value = ((u64)(aff3 & 0xff) << 48) | ((u64)(aff2 & 0xff) << 32)
              | ((u64)id << 24) | ((u64)(aff1 & 0xff) << 16) | mask;
    R10_DSB_ISHST();
    MSR(icc_sgi1r_el1, value);
    ISB();
}
