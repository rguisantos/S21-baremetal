/* main.c — R10: EL1 diagnostic-only entry.
 *
 * Interrupt controllers, hardware timers and PSCI remain deliberately disabled
 * until their register model and firmware handoff are verified on this device.
 */

#include "r10.h"

/* Global: FDT pointer passed from EL2 (currently not parsed). */
void *g_fdt = NULL;

/* EL1 entry point from EL2 drop */
void r10_el1_entry(void)
{
    MSR(spsel, 1);  // SP_EL1

    vbar_install();

    uart_init();
    uart_puts("\n\n=== R10: Exynos 2100 Bare-Metal Diagnostic ===\n");
    uart_puts("Build: " __DATE__ " " __TIME__ "\n");

    uart_puts("EL1 entry. CurrentEL: ");
    uart_puthex(get_current_el());
    uart_putc('\n');

    uart_puts("Initializing identity MMU...\n");
    mmu_init();
    uart_puts("MMU enabled.\n");

    /*
     * SAFETY GATE:
     * Do not initialize GIC, MCT, architected timer, or call PSCI yet.
     *
     * The current GIC implementation used incorrect MMIO for the GICv3 CPU
     * interface and enabled every SPI. IRQ dispatch also parks instead of
     * acknowledging/servicing interrupts. MCT register/IRQ assumptions and
     * the PSCI conduit have not been verified against the matching firmware.
     */
    uart_puts("Interrupts/timers/PSCI: DISABLED pending hardware audit.\n");

    uart_puts("\n--- Read-only hardware probe ---\n");
    uart_puts("GICD base: "); uart_puthex(GICD_BASE); uart_putc('\n');
    uart_puts("GICR base: "); uart_puthex(GICR_BASE); uart_putc('\n');
    uart_puts("MCT base:  "); uart_puthex(MCT_BASE); uart_putc('\n');
    uart_puts("UART base: "); uart_puthex(UART1_BASE); uart_putc('\n');
    uart_puts("ChipID address: "); uart_puthex(CHIPID_BASE);
    uart_puts(" value: "); uart_puthex(mmio_read32(CHIPID_BASE)); uart_putc('\n');

    uart_puts("\n--- UART Echo Test (if console setup is correct) ---\n");
    uart_puts("Type characters; q exits. No hardware PASS is claimed.\n");

    while (1) {
        char c = uart_getc();
        if (c) {
            uart_putc(c);
            if (c == 'q') break;
        }
    }

    uart_puts("\nR10 diagnostic loop exited; no hardware validation implied.\n");
    park();
}

/* Minimal exception handlers. IRQ dispatch is intentionally not enabled. */
void exc_sync(u64 *frame, u64 kind) { (void)frame; (void)kind; uart_puts("SYNC exception\n"); park(); }
void exc_irq(u64 *frame, u64 kind) { (void)frame; (void)kind; uart_puts("Unexpected IRQ while IRQ path is disabled\n"); park(); }
void exc_fiq(u64 *frame, u64 kind) { (void)frame; (void)kind; uart_puts("FIQ exception\n"); park(); }
void exc_serror(u64 *frame, u64 kind) { (void)frame; (void)kind; uart_puts("SError exception\n"); park(); }
