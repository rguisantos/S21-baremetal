/* uart.c — R10: Samsung USI v2 UART driver for Exynos 2100
 *
 * Based on Samsung kernel source:
 *   drivers/tty/serial/exynos_tty.c (exynos_usi_init, exynos_serial_set_termios)
 *   include/linux/serial_s3c.h (register offsets)
 *   drivers/clk/samsung/clk-exynos2100.c (clock tree)
 *
 * Hardware: uart1@10840000 (USI v2, SPI 533)
 * DTB phandles: clocks = <gate_uart_clk1, ipclk_uart1>
 *               samsung,usi-phandle = <0x70>, samsung,usi-offset = <0x00>
 */

#include "r10.h"

#define UART_BASE       UART1_BASE

/* S3C2410-compatible register offsets (from serial_s3c.h) */
#define S3C2410_ULCON   0x00
#define S3C2410_UCON    0x04
#define S3C2410_UFCON   0x08
#define S3C2410_UMCON   0x0C
#define S3C2410_UTRSTAT 0x10
#define S3C2410_UERSTAT 0x14
#define S3C2410_UFSTAT  0x18
#define S3C2410_UBRDIV  0x28

/* USI v2 registers (from serial_s3c.h + exynos_tty.c) */
#define USI_CON         0xC4
#define USI_OPTION      0xC8
#define USI_SW_CONF_MASK  (0x7 << 0)
#define USI_UART_SW_CONF  (1 << 0)
#define USI_RESET         (0 << 0)
#define USI_SET_RESET     (1 << 0)
#define USI_HWACG_CLKREQ_ON  (1 << 1)
#define USI_HWACG_CLKSTOP_ON (1 << 2)

/* ULCON bits */
#define ULCON_WLEN_8    (3 << 0)
#define ULCON_STOP_1    (0 << 2)
#define ULCON_PAR_NONE  (0 << 3)
#define ULCON_IRDA      (0 << 4)

/* UCON bits (S3C2410) */
#define UCON_TX_IRQ     (1 << 0)
#define UCON_RX_IRQ     (1 << 1)
#define UCON_TX_DMA     (2 << 0)
#define UCON_RX_DMA     (2 << 1)
#define UCON_TX_MODE(x) ((x) << 0)
#define UCON_RX_MODE(x) ((x) << 1)
#define UCON_CLK_PCLK   (0 << 10)
#define UCON_CLK_UCLK   (1 << 10)

/* UFCON bits */
#define UFCON_FIFO_EN   (1 << 0)
#define UFCON_RX_FIFO_RST (1 << 1)
#define UFCON_TX_FIFO_RST (1 << 2)

/* UTRSTAT bits */
#define UTRSTAT_RX_READY  (1 << 0)
#define UTRSTAT_TX_EMPTY  (1 << 1)
#define UTRSTAT_TX_FULL   (1 << 2)

static int uart_initialized = 0;
static u32 uart_clk_rate = 26000000;  // OSCCLK 26 MHz (fallback)

static inline void uart_w(u32 reg, u32 val)
{
    mmio_write32(UART_BASE + reg, val);
}

static inline u32 uart_r(u32 reg)
{
    return mmio_read32(UART_BASE + reg);
}

static void usi_init(void)
{
    /* USI init sequence from exynos_usi_init() */
    uart_w(USI_CON, USI_SET_RESET);
    for (volatile int i = 0; i < 1000; i++);  // ~1 us at 26 MHz
    uart_w(USI_CON, USI_RESET);
    for (volatile int i = 0; i < 1000; i++);
    uart_w(USI_OPTION, USI_HWACG_CLKREQ_ON);
}

static void usi_set_uart_mode(void)
{
    /* Configure USI_SW_CONF for UART mode */
    u32 val = uart_r(USI_CON);
    val &= ~USI_SW_CONF_MASK;
    val |= USI_UART_SW_CONF;
    uart_w(USI_CON, val);
}

/* Baud rate calculation from exynos_serial_getclk() */
static u32 uart_calc_ubrdiv(u32 clk, u32 baud)
{
    u64 quot = ((u64)clk * 10) / (baud * 16);
    return (u32)((quot + 5) / 10);  // Round
}

/* Fractional divisor table (udivslot_table from exynos_tty.c) */
static const u16 udivslot_table[16] = {
    0x0000, 0x0080, 0x0808, 0x0888,
    0x2222, 0x4924, 0x4A52, 0x54AA,
    0x5555, 0xD555, 0xD5D5, 0xDDD5,
    0xDDDD, 0xDFDD, 0xDFDF, 0xFFDF
};

static void uart_set_baud(u32 baud)
{
    u32 quot = uart_calc_ubrdiv(uart_clk_rate, baud);
    u32 ubrdiv = quot / 16;
    u32 ufrac = quot % 16;
    
    uart_w(S3C2410_UBRDIV, ubrdiv);
    /* Note: UFRACVAL register location varies; omitted for simplicity */
    (void)udivslot_table;  // Suppress unused warning
}

void uart_init(void)
{
    if (uart_initialized) return;

    /* 1. USI block initialization */
    usi_init();
    usi_set_uart_mode();

    /* 2. Reset FIFOs */
    uart_w(S3C2410_UFCON, UFCON_FIFO_EN | UFCON_RX_FIFO_RST | UFCON_TX_FIFO_RST);
    for (volatile int i = 0; i < 1000; i++);

    /* 3. Line control: 8N1, no IRDA */
    uart_w(S3C2410_ULCON, ULCON_WLEN_8 | ULCON_STOP_1 | ULCON_PAR_NONE | ULCON_IRDA);

    /* 4. Control: PCLK, IRQ mode (we'll poll, not use IRQs) */
    uart_w(S3C2410_UCON, UCON_CLK_PCLK | UCON_TX_MODE(0) | UCON_RX_MODE(0));

    /* 5. Modem control: no flow control */
    uart_w(S3C2410_UMCON, 0);

    /* 6. Set baud rate: 115200 @ 26 MHz */
    uart_set_baud(115200);

    /* 7. Enable FIFOs */
    uart_w(S3C2410_UFCON, UFCON_FIFO_EN);

    uart_initialized = 1;
}

void uart_putc(char c)
{
    if (!uart_initialized) uart_init();

    /* Wait for TX FIFO not full */
    while (!(uart_r(S3C2410_UTRSTAT) & UTRSTAT_TX_EMPTY))
        ;

    uart_w(S3C2410_UTRSTAT, 0);  // Clear status (some variants need this)
    mmio_write32(UART_BASE + 0x20, c);  // UTXH offset 0x20

    if (c == '\n') {
        while (!(uart_r(S3C2410_UTRSTAT) & UTRSTAT_TX_EMPTY))
            ;
        mmio_write32(UART_BASE + 0x20, '\r');
    }
}

char uart_getc(void)
{
    if (!uart_initialized) uart_init();

    /* Check RX ready */
    if (!(uart_r(S3C2410_UTRSTAT) & UTRSTAT_RX_READY))
        return 0;

    return (char)mmio_read32(UART_BASE + 0x24);  // URXH offset 0x24
}

void uart_puts(const char *s)
{
    while (*s) uart_putc(*s++);
}

void uart_puthex(u64 v)
{
    const char *hex = "0123456789abcdef";
    char buf[18];
    buf[0] = '0'; buf[1] = 'x';
    for (int i = 15; i >= 0; i--) {
        buf[17-i] = hex[(v >> (i*4)) & 0xF];
    }
    buf[18] = '\0';
    uart_puts(buf);
}