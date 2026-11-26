/* Ver fake_xnu.S. Offsets de boot_args conferidos com shim/loader.c (a128f07). */
#include <stdint.h>

#define UART 0x09000000UL

static void putc_(char c) { *(volatile uint32_t *)UART = (uint32_t)c; }
static void puts_(const char *s) { while (*s) putc_(*s++); }
static void hex(const char *k, uint64_t v)
{
	puts_(" "); puts_(k); puts_("=0x");
	for (int i = 60; i >= 0; i -= 4) putc_("0123456789abcdef"[(v >> i) & 0xf]);
}
static uint64_t r64(uint64_t a) { return *(volatile uint64_t *)a; }
static uint32_t r32(uint64_t a) { return *(volatile uint32_t *)a; }
static uint16_t r16(uint64_t a) { return *(volatile uint16_t *)a; }

void fake_main(uint64_t ba)
{
	uint64_t cur;
	__asm__ volatile("mrs %0, CurrentEL" : "=r"(cur));
	puts_("FAKEXNU");
	hex("el", cur >> 2);
	hex("ba", ba);
	hex("rev", r16(ba)); hex("ver", r16(ba + 2));
	uint64_t virt = r64(ba + 8), phys = r64(ba + 16);
	hex("virt", virt); hex("phys", phys); hex("mem", r64(ba + 24)); hex("top", r64(ba + 32));
	hex("fb", r64(ba + 40)); hex("disp", r64(ba + 48)); hex("stride", r64(ba + 56));
	hex("w", r64(ba + 64)); hex("h", r64(ba + 72)); hex("depth", r64(ba + 80));
	uint64_t dt = r64(ba + 96);
	hex("dt", dt); hex("dtlen", r32(ba + 104));
	uint64_t dt_pa = dt - virt + phys;
	hex("adt0", r64(dt_pa));
	hex("memact", r64(ba + 728));
	puts_(" cmd=");
	for (int i = 0; i < 64 && *(volatile char *)(ba + 108 + i); i++)
		putc_(*(volatile char *)(ba + 108 + i));
	puts_("\nFAKEXNU-END\n");
}
