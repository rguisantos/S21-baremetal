/* Execute production gic.c against bounded MMIO and mocked system registers. */
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define R10_H
 typedef uint8_t u8;
 typedef uint32_t u32;
 typedef uint64_t u64;
#include "../r10_payload/gic_regs.h"
static u64 mpidr = 0x0300020100ULL;
static u64 sre, ctlr_cpu, group, eoi, sgi;
static unsigned eoi_count, dist_writes;
static int eoimode_locked, asleep;
static uintptr_t dbase;
static u64 model_mrs(const char *reg)
{
    if (!strcmp(reg, "mpidr_el1")) return mpidr;
    if (!strcmp(reg, "icc_sre_el1")) return sre;
    if (!strcmp(reg, "icc_ctlr_el1")) return ctlr_cpu;
    if (!strcmp(reg, "icc_igrpen1_el1")) return group;
    if (!strcmp(reg, "icc_iar1_el1")) return 30;
    abort();
}
static void model_msr(const char *reg, u64 value)
{
    if (!strcmp(reg, "icc_sre_el1")) sre = value;
    else if (!strcmp(reg, "icc_ctlr_el1")) ctlr_cpu = eoimode_locked ? value | 2 : value;
    else if (!strcmp(reg, "icc_igrpen1_el1")) group = value;
    else if (!strcmp(reg, "icc_eoir1_el1")) { eoi = value; ++eoi_count; }
    else if (!strcmp(reg, "icc_sgi1r_el1")) sgi = value;
    else assert(!strcmp(reg, "icc_pmr_el1") || !strcmp(reg, "icc_bpr1_el1"));
}
#define MRS(reg) model_mrs(#reg)
#define MSR(reg, value) model_msr(#reg, value)
#define ISB() ((void)0)
#define R10_DSB_SY() ((void)0)
#define R10_DSB_ISHST() ((void)0)
static u32 mmio_read32(u64 addr) { assert(!(addr & 3)); return *(u32 *)(uintptr_t)addr; }
static void mmio_write32(u64 addr, u32 value)
{
    assert(!(addr & 3));
    if (addr >= dbase && addr < dbase + 0x10000) ++dist_writes;
    if ((addr & 0xffff) == 0x14 && asleep) value |= 4;
    *(u32 *)(uintptr_t)addr = value;
}
static void park(void) { abort(); }
int gic_cpu_interface_init(void);
#include "../r10_payload/gic.c"
int main(void)
{
    void *dist, *region;
    assert(!posix_memalign(&dist, 0x10000, 0x10000));
    assert(!posix_memalign(&region, 0x10000, 0x60000));
    memset(dist, 0, 0x10000); memset(region, 0, 0x60000);
    dbase = (uintptr_t)dist;
    u64 base = (uintptr_t)region, rd = base + 0x40000;
    /* A VLPI-capable first RD occupies four frames; matching Aff3/Aff2/Aff1
     * is on the second RD, not at Aff0 * a guessed stride. */
    *(u32 *)(base + 0xffe8) = 3U << 4;
    *(u32 *)(rd + 0xffe8) = 3U << 4;
    *(u64 *)GICR_TYPER(base) = GICR_TYPER_VLPIS;
    *(u64 *)GICR_TYPER(rd) = ((u64)mpidr_affinity(mpidr) << 32) | GICR_TYPER_LAST;
    assert(find_redist(base, 0x60000, 0, mpidr) == rd);
    assert(!find_redist(base, 0x20000, 0, mpidr));
    assert(!find_redist(base, 0x60000, 0x10000, mpidr));
    assert(!find_redist(base, 0x60000, 0, mpidr + 1));
    assert(!find_redist(UINT64_MAX - 0xffff, 0x20000, 0, mpidr));
    *(u32 *)dist = 0x52; /* DS + ARE + Group 1 enable */
    *(u32 *)GICR_SGI_IGROUPR(rd) = 1U << 30;
    assert(gic_init_region(dbase, base, 0x60000, 0) == 0);
    assert(boot_redist == rd && dist_writes == 0);
    memset((void *)GICR_SGI_IPRIORITYR(rd), 0x55, 32);
    gic_set_priority(30, 0x80);
    u8 *prio = (u8 *)GICR_SGI_IPRIORITYR(rd);
    assert(prio[29] == 0x55 && prio[30] == 0x80 && prio[31] == 0x55);
    assert(!gic_enable_irq(30));
    assert(*(u32 *)GICR_SGI_ISENABLER(rd) == (1U << 30));
    assert(gic_enable_irq(31) == -1 && gic_enable_irq(533) == -1);
    gic_eoi(1023); assert(eoi_count == 0);
    gic_eoi(30); assert(eoi == 30 && eoi_count == 1);
    gic_send_sgi(3, 0x10, 1, 2, 4);
    assert(sgi == ((4ULL << 48) | (2ULL << 32) | (3ULL << 24) | (1ULL << 16) | 0x10));
    *(u32 *)GICR_CTLR(rd) = GICR_RWP;
    assert(gic_enable_irq(30) == -1); /* bounded RWP timeout */
    *(u32 *)GICR_CTLR(rd) = 0;
    *(u32 *)GICR_WAKER(rd) = 6; asleep = 1;
    assert(gic_init_region(dbase, base, 0x60000, 0) == -1);
    asleep = 0; *(u32 *)GICR_WAKER(rd) = 0;
    eoimode_locked = 1;
    assert(gic_init_region(dbase, base, 0x60000, 0) == -1);
    assert(!boot_redist);
    assert(dist_writes == 0);
    free(dist); free(region);
    puts("GIC MODEL PASS");
}
