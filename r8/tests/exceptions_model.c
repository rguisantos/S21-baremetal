/* Verify dispatch policy and exact EOI ownership using the production source. */
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include "../r10_payload/r10.h"
static jmp_buf stopped;
static u32 interrupt, eois, ticks, disables;
void uart_puts(const char *s) { (void)s; }
void uart_puthex(u64 v) { (void)v; }
void uart_putc(char c) { (void)c; }
void park(void) { longjmp(stopped, 1); }
u32 gic_ack_irq(void) { return interrupt; }
void gic_eoi(u32 irq) { assert(irq == interrupt); ++eois; }
void gic_disable_irq(u32 irq) { assert(irq == interrupt); ++disables; }
void timer_handle_irq(void) { ++ticks; assert(!eois); }
#include "../r10_payload/exceptions.c"
int main(void)
{
    struct exc_frame frame = {.elr = 0x123400, .esr = 0x96000004, .far = 0xdead0000};
    interrupt = 1023;
    exc_dispatch(&frame, KIND_IRQ);
    assert(!eois && !ticks && !disables);
    interrupt = 30;
    exc_dispatch(&frame, KIND_IRQ);
    assert(eois == 1 && ticks == 1 && !disables);
    eois = ticks = 0;
    if (!setjmp(stopped)) {
        exc_dispatch(&frame, KIND_SYNC);
        assert(!"sync must never return");
    }
    assert(frame.elr == 0x123400 && r10_last_fault.elr == frame.elr);
    assert(r10_last_fault.esr == frame.esr && r10_last_fault.far == frame.far);
    assert(!eois && !ticks);
    interrupt = 31;
    if (!setjmp(stopped)) {
        exc_dispatch(&frame, KIND_IRQ);
        assert(!"unexpected IRQ must stop");
    }
    assert(disables == 1 && eois == 1 && !ticks);
    puts("EXCEPTION MODEL PASS");
}
