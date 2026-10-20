/* gic.c — R10 GICv3 driver intentionally fail-closed.
 *
 * The previous implementation enabled every SPI and accessed the GICv3 CPU
 * interface as MMIO through the redistributor frame. Both are unsafe.
 *
 * Keep these entry points inert until ICC_* system-register access, redistributor
 * discovery/affinity, security-state handoff, and IRQ dispatch are implemented
 * and reviewed against the exact Exynos 2100 firmware/device tree.
 */

#include "r10.h"

void gic_init(void)
{
    uart_puts("GIC init SKIPPED: GICv3 driver not yet validated.\n");
}

void gic_enable_irq(u32 irq)
{
    (void)irq;
}

void gic_disable_irq(u32 irq)
{
    (void)irq;
}

void gic_set_priority(u32 irq, u8 priority)
{
    (void)irq;
    (void)priority;
}

void gic_eoi(u32 irq)
{
    (void)irq;
}
