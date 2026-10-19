/* uart.c — R10: USI v2 UART driver for Exynos 2100 */

#include "r10.h"

static int uart_initialized = 0;

void uart_init(void)
{
    if (uart_initialized) return;
    
    /* Disable UART first */
    mmio_write32(USI_UART_CTRL, 0);
    
    /* Configure baud rate: 115200 @ 26 MHz
     * USI UART uses fractional baud rate generator
     * BRD = UART_CLK / (16 * baud)
     * For 26 MHz: 26000000 / (16 * 115200) = 14.1
     * Integer part: 14, Fractional: 0.1 * 64 = 6.4 ≈ 6
     */
    u32 ibrd = 14;
    u32 fbrd = 6;
    mmio_write32(USI_UART_BAUD, (ibrd << 16) | (fbrd & 0x3F));
    
    /* Line control: 8N1, no parity, FIFOs enabled */
    u32 lcr = USI_LINE_CTRL_WLEN_8 | USI_LINE_CTRL_STOP_1 | USI_LINE_CTRL_PAR_NONE;
    mmio_write32(USI_UART_LINE_CTRL, lcr);
    
    /* FIFO control: enable, clear RX/TX */
    mmio_write32(USI_UART_FIFO_CTRL, 0x07);  // Enable FIFOs, clear RX, clear TX
    
    /* Enable UART, TX, RX */
    mmio_write32(USI_UART_CTRL, USI_CTRL_UART_EN | USI_CTRL_TX_EN | USI_CTRL_RX_EN);
    
    /* Enable clock gating if needed (handled by firmware ideally) */
    /* Note: DTB has clocks = <gate_uart_clk1, ipclk_uart1>
     * We assume firmware has enabled them, or we'd need CLK driver */
    
    uart_initialized = 1;
}

void uart_putc(char c)
{
    if (!uart_initialized) uart_init();
    
    /* Wait for TX FIFO not full */
    while (mmio_read32(USI_UART_STATUS) & USI_STATUS_TX_FULL)
        ;
    
    mmio_write32(USI_UART_TX_FIFO, c);
    
    /* If CR, also send LF */
    if (c == '\n') {
        while (mmio_read32(USI_UART_STATUS) & USI_STATUS_TX_FULL)
            ;
        mmio_write32(USI_UART_TX_FIFO, '\r');
    }
}

char uart_getc(void)
{
    if (!uart_initialized) uart_init();
    
    /* Check RX FIFO not empty */
    if (mmio_read32(USI_UART_STATUS) & USI_STATUS_RX_EMPTY)
        return 0;
    
    return (char)mmio_read32(USI_UART_RX_FIFO);
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

int uart_readline(char *buf, int max)
{
    int i = 0;
    while (i < max - 1) {
        char c = uart_getc();
        if (!c) continue;
        if (c == '\r' || c == '\n') {
            uart_putc('\n');
            break;
        }
        if (c == 0x7F || c == '\b') {  // backspace
            if (i > 0) {
                i--;
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