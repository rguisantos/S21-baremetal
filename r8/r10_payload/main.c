/* main.c — R10: EL1 main entry, hardware initialization */

#include "r10.h"
#include "percpu.h"

extern char _start[], _end[];
extern char __bss_start[], __bss_end[];
extern char __el1_stack_top[], __exc_stack_top[];

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
    
    /* Initialize per-CPU early */
    percpu_init_early();
    
    /* Initialize MMU with identity mapping */
    uart_puts("Initializing MMU...\n");
    mmu_init();
    uart_puts("MMU enabled.\n");
    
    /* Initialize GIC-600 */
    uart_puts("Initializing GIC-600...\n");
    gic_init();
    uart_puts("GIC-600 initialized.\n");
    
    /* Initialize per-CPU late (primary CPU) */
    percpu_init_cpu(get_current_cpu(), get_current_mpidr(), 
                    (u64)__el1_stack_top, (u64)__exc_stack_top);
    percpu_init_late();
    
    /* Initialize IPI handlers */
    ipi_init();
    
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
    
    /* SMP bringup */
    uart_puts("Initializing SMP...\n");
    int online = smp_init();
    uart_puts("SMP: "); uart_puthex(online); uart_puts(" CPUs online\n");
    
    /* Print system info */
    uart_puts("\n--- System Info ---\n");
    uart_puts("GICD: "); uart_puthex(GICD_BASE); uart_puts(" (CTLR: "); uart_puthex(mmio_read32(GICD_CTLR)); uart_puts(")\n");
    uart_puts("GICR: "); uart_puthex(GICR_BASE); uart_puts("\n");
    uart_puts("MCT:  "); uart_puthex(MCT_BASE); uart_puts("\n");
    uart_puts("UART: "); uart_puthex(UART1_BASE); uart_puts("\n");
    uart_puts("ChipID: "); uart_puthex(CHIPID_BASE); uart_puts(" = "); uart_puthex(mmio_read32(CHIPID_BASE)); uart_putc('\n');
    
    /* Test UART echo with timer tick */
    uart_puts("\n--- UART Echo + Timer Test ---\n");
    uart_puts("Type characters (echo). Timer ticks every 1ms:\n");
    
    u32 last_tick = 0;
    while (1) {
        char c = uart_getc();
        if (c) {
            uart_putc(c);
            if (c == 'q') break;
        }
        
        /* Print timer tick every 100ms */
        u32 now = (u32)(timer_read_cnt() / (timer_read_freq() / 1000));
        if (now != last_tick) {
            last_tick = now;
            if ((last_tick % 100) == 0) {
                uart_puts("\n[Tick: "); uart_puthex(last_tick); uart_puts("ms]");
            }
        }
    }
    
    uart_puts("\n=== R10 PASS ===\n");
    shutdown();
}

/* Exception handlers for EL1 */
void exc_sync(u64 *frame, u64 kind) { uart_puts("SYNC exception\n"); park(); }
void exc_fiq(u64 *frame, u64 kind) { uart_puts("FIQ exception\n"); park(); }
void exc_serror(u64 *frame, u64 kind) { uart_puts("SError exception\n"); park(); }

/* IRQ handler - dispatches to appropriate handler based on INTID */
void exc_irq(u64 *frame, u64 kind)
{
    (void)frame; (void)kind;
    
    /* Acknowledge interrupt from GIC CPU interface */
    u32 intid = gic_ack_irq();
    
    /* Dispatch based on INTID */
    switch (intid) {
        case 30:        // CNTP (architected timer PPI)
            timer_handle_irq();
            break;
        case 224:
        case 225:
        case 226:
        case 227:       // MCT SPI 224-227
            mct_handle_irq(intid);
            break;
        case 0 ... 15:  // SGI 0-15
            ipi_handler(intid);
            break;
        case 533:       // UART1 SPI (not enabled yet)
            // uart_handle_irq();
            break;
        default:
            uart_puts("Unhandled IRQ: "); uart_puthex(intid); uart_putc('\n');
            break;
    }
    
    /* End of Interrupt */
    gic_eoi(intid);
}