#ifndef CONSOLE_H
#define CONSOLE_H

#include <stdint.h>

#define CON_W 80
#define CON_H 25

void con_init(uint32_t fb_phys);
void con_putc(char c);
void con_puts(const char *s);
void con_hex(const char *label, uint64_t v);
void con_hex2(const char *l1, const char *prefix1, uint64_t v1, const char *prefix2, uint64_t v2);
void con_str(const char *l1, const char *l2);
void con_skip(void);
void con_clear(uint32_t color);

#define COL_RED    0xffff0000
#define COL_GREEN  0xff00ff00
#define COL_BLUE   0xff0000ff
#define COL_WHITE  0xffffffff
#define COL_BLACK  0xff000000

#endif