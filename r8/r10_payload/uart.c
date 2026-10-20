/* uart.c — R10 Samsung Exynos UART register-layout implementation.
 *
 * Register offsets follow the Samsung serial driver; UFSTAT.TXFULL uses the Exynos/S5PV210-style mask
 * (include/linux/serial_s3c.h, drivers/tty/serial/samsung_tty.c). This replaces
 * the previous PL011-like register map, which did not match that driver.
 *
 * Still unverified for the exact boot handoff: UART1 clock rate/gating,
 * pinmux state, whether this firmware leaves the port enabled, and the exact
 * USI v2 integration. Do not treat this source change as hardware validation.
 */

#include "r10.h"

#define S3C_ULCON       (UART1_BASE + 0x00)
#define S3C_UCON        (UART1_BASE + 0x04)
#define S3C_UFCON       (UART1_BASE + 0x08)
#define S3C_UMCON       (UART1_BASE + 0x0C)
#define S3C_UTRSTAT     (UART1_BASE + 0x10)
#define S3C_UERSTAT     (UART1_BASE + 0x14)
#define S3C_UFSTAT      (UART1_BASE + 0x18)
#define S3C_UMSTAT      (UART1_BASE + 0x1C)
#define S3C_UTXH        (UART1_BASE + 0x20)
#define S3C_URXH        (UART1_BASE + 0x24)
#define S3C_UBRDIV      (UART1_BASE + 0x28)
#define S3C_UFRACVAL    (UART1_BASE + 0x2C)

#define UTRSTAT_RXDR    (1u << 0)
#define UFSTAT_TXFULL   (1u << 24) /* Exynos/S5PV210-style UFSTAT */
#define UCON_RX_POLL    (1u << 0)
#define UCON_TX_POLL    (1u << 2)
#define UFCON_ENABLE    (1u << 0)
#define UFCON_RESET_RX  (1u << 1)
#define UFCON_RESET_TX  (1u << 2)

#define UART_POLL_LIMIT 1000000u

static int uart_initialized;

static inline void uart_write_byte(unsigned long addr, unsigned char value)
{
    *(volatile unsigned char *)addr = value;
}

static inline unsigned char uart_read_byte(unsigned long addr)
{
    return *(volatile unsigned char *)addr;
}

static int uart_wait_tx_space(void)
{
    for (u32 n = 0; n < UART_POLL_LIMIT; ++n) {
        if ((mmio_read32(S3C_UFSTAT) & UFSTAT_TXFULL) == 0)
            return 1;
    }
    return 0;
}

void uart_init(void)
{
    if (uart_initialized)
        return;

    /* No guessed clock, baud divisor, pinmux or USI reset. Opt in only
     * when a loader has configured and verified this exact UART instance.
     * Default builds perform no UART MMIO (the firmware DTB disables it).
     */
#ifdef R10_UART_FIRMWARE_CONFIGURED
    uart_initialized = 1;
#endif
}

void uart_putc(char c)
{
    if (!uart_initialized)
        uart_init();
    if (!uart_initialized)
        return;

    if (c == '\n') {
        if (uart_wait_tx_space())
            uart_write_byte(S3C_UTXH, '\r');
    }

    if (uart_wait_tx_space())
        uart_write_byte(S3C_UTXH, (unsigned char)c);
}

char uart_getc(void)
{
    if (!uart_initialized)
        uart_init();
    if (!uart_initialized)
        return 0;

    if ((mmio_read32(S3C_UTRSTAT) & UTRSTAT_RXDR) == 0)
        return 0;

    return (char)uart_read_byte(S3C_URXH);
}

void uart_puts(const char *s)
{
    while (*s)
        uart_putc(*s++);
}

void uart_puthex(u64 value)
{
    static const char hex[] = "0123456789abcdef";
    char buf[19];
    buf[0] = '0';
    buf[1] = 'x';
    for (int i = 0; i < 16; ++i)
        buf[2 + i] = hex[(value >> ((15 - i) * 4)) & 0xF];
    buf[18] = '\0';
    uart_puts(buf);
}

int uart_readline(char *buf, int max)
{
    uart_init();
    if (!buf || max <= 0)
        return 0;

    if (!uart_initialized) {
        buf[0] = '\0';
        return 0;
    }

    int i = 0;
    while (i < max - 1) {
        char c = uart_getc();
        if (!c)
            continue;

        if (c == '\r' || c == '\n') {
            uart_putc('\n');
            break;
        }

        if (c == 0x7F || c == '\b') {
            if (i > 0) {
                --i;
                uart_puts("\b \b");
            }
        } else {
            buf[i++] = c;
            uart_putc(c);
        }
    }
    buf[i] = '\0';
    return i;
}
