/* Runs the actual EL2 entry, GIC driver, timer and R10 dispatcher on QEMU.
 * A synthetic loader owns distributor/Group assignment for this test only. */
#include "../r10_payload/r10.h"
extern char r10_test_fdt[];
u64 r10_test_bss;
void secondary_cpu_entry(void) { park(); }
void uart_puts(const char *s) { while (*s) uart_putc(*s++); }
void uart_puthex(u64 value) { printf("%p", value); }

void r10_el1_entry(void *fdt)
{
    uart_init();
    if (fdt != (void *)r10_test_fdt || r10_test_bss || get_current_el() != 1) {
        puts("R10 BOOT FAIL"); park();
    }
    puts("R10 BOOT PASS: FDT, BSS, EL1");
    vbar_install();
    /* Emulate a firmware-owned GICv3 distributor at QEMU addresses. */
    mmio_write32(0x08000000, 0x12);
    asm volatile("dsb sy\n\tisb" ::: "memory");
    mmio_write32(0x080a0000 + 0x10000 + 0x80, 1U << 30);
    if (gic_init_region(0x08000000, 0x080a0000, 0x20000, 0) || timer_init()) {
        puts("R10 GIC/TIMER FAIL"); park();
    }
    asm volatile("msr daifclr, #2\n\tisb" ::: "memory");
    while (r10_timer_ticks < 5) asm volatile("wfi" ::: "memory");
    asm volatile("msr daifset, #2\n\tisb" ::: "memory");
    puts("R10 TIMER PASS: five IRQs through production dispatcher");
    asm volatile(".inst 0x00000000"); /* must park, never skip this fault */
    puts("R10 FAULT FAIL: resumed after undefined instruction");
    park();
}
