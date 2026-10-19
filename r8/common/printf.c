/* printf.c — printf minimalista para bare-metal (sem libc)
 * Suporta: %s %c %d %u %x %p %%  com modificadores 'l'/'ll',
 * largura e preenchimento com zero (ex.: %016lx).
 */

#include <stdarg.h>
#include "r8lib.h"

int putchar(int c)
{
    if (c == '\n')
        uart_putc('\r');
    uart_putc((char)c);
    return c;
}

int puts(const char *s)
{
    while (*s)
        putchar(*s++);
    putchar('\n');
    return 0;
}

static void pad(u64 v, unsigned base, int width, char fill)
{
    char buf[32];
    int i = 0;

    if (v == 0)
        buf[i++] = '0';
    while (v) {
        u32 d = (u32)(v % base);
        buf[i++] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
        v /= base;
    }
    while (i < width)
        buf[i++] = fill;
    while (i)
        putchar(buf[--i]);
}

static void snum(long v, int width, char fill)
{
    if (v < 0) {
        putchar('-');
        v = -v;
    }
    pad((u64)v, 10, width, fill);
}

int printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);

    for (; *fmt; fmt++) {
        int width = 0, longs = 0;
        char fill = ' ';

        if (*fmt != '%') {
            putchar(*fmt);
            continue;
        }
        fmt++;
        if (*fmt == '%') {
            putchar('%');
            continue;
        }
        int alt = 0;
        if (*fmt == '#') {          /* flag '#': prefixo 0x em hex */
            alt = 1;
            fmt++;
        }
        if (*fmt == '0') {
            fill = '0';
            fmt++;
        }
        while (*fmt >= '0' && *fmt <= '9')
            width = width * 10 + (*fmt++ - '0');
        while (*fmt == 'l') {
            longs++;
            fmt++;
        }

        switch (*fmt) {
        case 'c':
            putchar(va_arg(ap, int));
            break;
        case 's': {
            const char *s = va_arg(ap, const char *);
            if (!s)
                s = "(null)";
            while (*s)
                putchar(*s++);
            break;
        }
        case 'd':
            snum(longs ? va_arg(ap, long) : va_arg(ap, int), width, fill);
            break;
        case 'u':
            pad(longs ? va_arg(ap, unsigned long) : va_arg(ap, unsigned), 10, width, fill);
            break;
        case 'x':
            if (alt) { uart_putc('0'); uart_putc('x'); }
            pad(longs ? va_arg(ap, unsigned long) : va_arg(ap, unsigned), 16, width, fill);
            break;
        case 'p':
            uart_putc('0'); uart_putc('x');
            pad((u64)va_arg(ap, void *), 16, 0, '0');
            break;
        default:
            putchar('%');
            putchar(*fmt);
            break;
        }
    }
    va_end(ap);
    return 0;
}
