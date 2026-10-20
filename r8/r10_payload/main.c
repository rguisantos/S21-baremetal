/* Initial R10 stage: one boot CPU, firmware-owned GIC, architected timer.
 * No automatic MMU/cache reconfiguration, MCT writes, PSCI probing or CPU_ON.
 * Hardware boot contract and live DTB resources still require validation. */
#include "r10.h"

void *g_fdt;
static u32 be32(const u8 *p)
{
    return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
}

void r10_el1_entry(void *fdt)
{
    g_fdt = fdt; /* x0 is restored from x19 immediately before ERET. */
    vbar_install();
    uart_init();
    /* Only header sanity here, not a claim of full DTB/resource validation.
     * Invalid/unmapped addresses trap through the fatal dispatcher. */
    if (!fdt || ((u64)fdt & 7)) park();
    u32 magic = be32(fdt), size = be32((const u8 *)fdt + 4);
    if (magic != 0xd00dfeed || size < 40 || size > 2 * 1024 * 1024) park();
    uart_puts("R10: single CPU, FDT received; MMU/MCT/SMP unchanged\n");
    if (gic_init()) { uart_puts("R10: GIC handoff rejected\n"); park(); }
    if (timer_init()) { uart_puts("R10: timer setup rejected\n"); park(); }
    asm volatile("msr daifclr, #2\n\tisb" ::: "memory");
    for (;;) asm volatile("wfi" ::: "memory");
}
