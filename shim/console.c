/*
 * Framebuffer console for S21 Ultra - UART fallback implementation
 */
#include <stdint.h>
#include "console.h"

static inline void uart_putc(char c)
{
	volatile uint32_t *utxh = (volatile uint32_t *)0x10840020;
	*utxh = (uint32_t)c;
	if (c == '\n') {
		while (!(*utxh & (1<<1))) ; /* TX empty */
		*utxh = '\r';
	}
}

void con_init(uint32_t phys)
{
	(void)phys;
}

void con_putc(char c)
{
	uart_putc(c);
}

void con_puts(const char *s)
{
	while (*s) {
		uart_putc(*s++);
	}
}

void con_hex(const char *label, uint64_t v)
{
	con_puts(label);
	uart_putc('0'); uart_putc('x');
	for (int i = 15; i >= 0; i--) {
		char c = "0123456789abcdef"[(v >> (i*4)) & 0xf];
		uart_putc(c);
	}
	uart_putc('\n');
}

void con_hex2(const char *l1, const char *prefix1, uint64_t v1, const char *prefix2, uint64_t v2)
{
	con_puts(l1);
	con_puts(prefix1);
	con_hex("", v1);
	con_puts(prefix2);
	con_hex("", v2);
}

void con_str(const char *l1, const char *l2)
{
	con_puts(l1);
	uart_putc(':'); uart_putc(' ');
	while (*l2) {
		uart_putc(*l2++);
	}
	uart_putc('\n');
}

void con_skip(void)
{
	uart_putc('\n');
}

void con_clear(uint32_t color)
{
	(void)color;
}