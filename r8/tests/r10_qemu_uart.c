/* QEMU UART adapter only; production main/entry/GIC/timer/dispatcher unchanged. */
#include "../r10_payload/r10.h"
volatile u64 r10_qemu_observed_el;
void uart_puts(const char *s)
{
    r10_qemu_observed_el=MRS(CurrentEL);
    while (*s) uart_putc(*s++);
}
void uart_puthex(u64 value)
{
    uart_puts("0x");
    for (int shift=60;shift>=0;shift-=4) uart_putc("0123456789abcdef"[(value>>shift)&15]);
}
void secondary_cpu_entry(void) { park(); }
