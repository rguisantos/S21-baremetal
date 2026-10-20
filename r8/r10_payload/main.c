/* main.c — R10: EL1 main entry, hardware initialization */

#include "r10.h"

extern char _start[], _end[];
extern char __bss_start[], __bss_end[];

/* Global: FDT pointer passed from EL2 */
void *g_fdt = NULL;

/* EL1 entry point from EL2 drop */
void r10_el1_entry(void)
{
    /* Set up EL1 stack (already done via SP_EL1 in EL2) */
    MSR(spsel, 1);  // SP_EL1
    
    /* Install EL1 vector table */
    vbar_install();
    
    /* Initialize hardware */
    uart_init();
    uart_puts("\n\n=== R10: Exynos 2100 Bare-Metal Payload ===\n");
    uart_puts("Build: " __DATE__ " " __TIME__ "\n");
    
    uart_puts("EL1 entry confirmed. CurrentEL: ");
    uart_puthex(get_current_el());
    uart_putc('\n');
    
    /* Initialize MMU with identity mapping */
    uart_puts("Initializing MMU...\n");
    mmu_init();
    uart_puts("MMU enabled.\n");
    
    /* Initialize GIC-600 */
    uart_puts("Initializing GIC-600...\n");
    gic_init();
    uart_puts("GIC-600 initialized.\n");
    
    /* Initialize MCT timer */
    uart_puts("Initializing MCT timer...\n");
    mct_init();
    uart_puts("MCT timer initialized.\n");
    
    /* Initialize architected timer */
    uart_puts("Initializing architected timer...\n");
    timer_init();
    uart_puts("Architected timer initialized.\n");
    
    /* Test PSCI */
    uart_puts("Testing PSCI (SMC)...\n");
    s64 ret = psci_call(PSCI_VERSION, 0, 0, 0);
    uart_puts("PSCI_VERSION: ");
    uart_puthex(ret);
    uart_putc('\n');
    
    /* Print system info */
    uart_puts("\n--- System Info ---\n");
    uart_puts("GICD: "); uart_puthex(GICD_BASE); uart_puts(" (CTLR: "); uart_puthex(mmio_read32(GICD_CTLR)); uart_puts(")\n");
    uart_puts("GICR: "); uart_puthex(GICR_BASE); uart_puts("\n");
    uart_puts("MCT:  "); uart_puthex(MCT_BASE); uart_puts("\n");
    uart_puts("UART: "); uart_puthex(UART1_BASE); uart_puts("\n");
    uart_puts("ChipID: "); uart_puthex(CHIPID_BASE); uart_puts(" = "); uart_puthex(mmio_read32(CHIPID_BASE)); uart_putc('\n');
    
    /* Test UART echo */
    uart_puts("\n--- UART Echo Test ---\n");
    uart_puts("Type characters (echo):\n");
    
    while (1) {
        char c = uart_getc();
        if (c) {
            uart_putc(c);
            if (c == 'q') break;
        }
    }
    
    uart_puts("\n=== R10 PASS ===\n");
    shutdown();
}

/* Minimal exception handlers for EL1 */
void exc_sync(u64 *frame, u64 kind) { uart_puts("SYNC exception\n"); park(); }
void exc_irq(u64 *frame, u64 kind) { uart_puts("IRQ exception\n"); park(); }
void exc_fiq(u64 *frame, u64 kind) { uart_puts("FIQ exception\n"); park(); }
void exc_serror(u64 *frame, u64 kind) { uart_puts("SError exception\n"); park(); }