/* R10 owns its dispatcher; never link the didactic common/exc.c here. */
#include "r10.h"

/* Inspectable via debugger even when UART is unavailable. */
volatile struct r10_fault_record r10_last_fault;

void exc_unexpected_c(unsigned slot)
{
    r10_last_fault.kind = 0x100 + slot;
    park();
}

void exc_dispatch(struct exc_frame *frame, u64 kind)
{
    if (kind == KIND_IRQ) {
        u32 irq = gic_ack_irq();
        if (irq >= 1020 && irq <= 1023) return;
        if (irq == 30) {
            timer_handle_irq(); /* rearm first; EOI has exactly one owner */
            gic_eoi(irq);
            return;
        }
        if (irq < 32) gic_disable_irq(irq);
        gic_eoi(irq);
        /* Unexpected interrupt is fatal in this single-source stage. */
    }
    r10_last_fault.kind = kind;
    r10_last_fault.elr = frame->elr;
    r10_last_fault.esr = frame->esr;
    r10_last_fault.far = frame->far;
    uart_puts("R10 FATAL kind="); uart_puthex(kind);
    uart_puts(" ELR="); uart_puthex(frame->elr);
    uart_puts(" ESR="); uart_puthex(frame->esr);
    uart_puts(" FAR="); uart_puthex(frame->far); uart_putc('\n');
    park(); /* No skipped instruction and no ERET to a faulting context. */
}
