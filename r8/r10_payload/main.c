/* main.c — R10: fail-closed entry stub.
 *
 * The EL2->EL1 handoff, load address, UART register map, GICv3 state, MCT
 * registers, and PSCI conduit are not yet validated for the exact SM-G998B
 * firmware. Do not touch peripheral MMIO or enable interrupts from this entry.
 *
 * This deliberately produces no UART output. It is a safety placeholder, not
 * a hardware test and not evidence that the payload is safe to boot on-device.
 */

#include "r10.h"

void *g_fdt = NULL;

void r10_el1_entry(void)
{
    /*
     * No MMIO, MMU transition, timer setup, GIC setup, or PSCI call here.
     * A future bring-up entry must first validate the firmware handoff and
     * serial console using the matching device tree and Samsung kernel source.
     */
    park();
}

/* Exception handlers remain fail-closed; no interrupt source is enabled here. */
void exc_sync(u64 *frame, u64 kind)
{
    (void)frame;
    (void)kind;
    park();
}

void exc_irq(u64 *frame, u64 kind)
{
    (void)frame;
    (void)kind;
    park();
}

void exc_fiq(u64 *frame, u64 kind)
{
    (void)frame;
    (void)kind;
    park();
}

void exc_serror(u64 *frame, u64 kind)
{
    (void)frame;
    (void)kind;
    park();
}
