/* Host MMIO model: tests actual UART C code without touching hardware. */
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#define R10_H
 typedef uint32_t u32;
 typedef uint64_t u64;
 static uint32_t regs[64];
 static unsigned reads;
#define UART1_BASE ((unsigned long)regs)
static u32 mmio_read32(unsigned long addr) { ++reads; return *(volatile u32 *)addr; }
#include "../r10_payload/uart.c"
int main(void)
{
    char buf[2] = {'x', 'y'};
    uart_init();
#ifndef R10_UART_FIRMWARE_CONFIGURED
    uart_puts("disabled\n");
    uart_puthex(UINT64_MAX);
    assert(uart_getc() == 0);
    assert(uart_readline(buf, sizeof(buf)) == 0 && buf[0] == 0);
    assert(reads == 0);
    for (unsigned i = 0; i < 64; ++i) assert(regs[i] == 0);
#else
    uart_putc('A'); assert(regs[0x20 / 4] == 'A');
    uart_putc('\n'); assert(regs[0x20 / 4] == '\n');
    regs[0x18 / 4] = 1u << 24;
    uart_putc('B'); assert(regs[0x20 / 4] == '\n');
    regs[0x18 / 4] = 0;
    uart_puthex(UINT64_MAX); assert(regs[0x20 / 4] == 'f');
    regs[0x24 / 4] = 'Z';
    assert(uart_getc() == 0);
    regs[0x10 / 4] = 1;
    assert(uart_getc() == 'Z');
    assert(uart_readline(buf, 1) == 0 && buf[0] == 0 && buf[1] == 'y');
#endif
    assert(uart_readline(NULL, 4) == 0);
    assert(uart_readline(buf, 0) == 0);
    puts("UART PASS");
}
