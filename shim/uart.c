/*
 * S21 Ultra Exynos 2100 USI v2 UART driver
 */
#include <stdint.h>
#include "uart.h"

#define UART_BASE		UART1_BASE

/* S3C2410 compatible register offsets */
#define S3C2410_ULCON		0x00
#define S3C2410_UCON		0x04
#define S3C2410_UFCON		0x08
#define S3C2410_UMCON		0x0C
#define S3C2410_UTRSTAT		0x10
#define S3C2410_UERSTAT		0x14
#define S3C2410_UFSTAT		0x18
#define S3C2410_UBRDIV		0x28

/* USI v2 registers */
#define USI_CON			0xC4
#define USI_OPTION		0xC8

/* USI_CON bits */
#define USI_SET_RESET		(1 << 0)
#define USI_RESET		(0 << 0)
#define USI_SW_CONF_MASK	(0x7 << 0)
#define USI_UART_SW_CONF	(1 << 0)
#define USI_HWACG_CLKREQ_ON	(1 << 1)
#define USI_HWACG_CLKSTOP_ON	(1 << 2)

/* ULCON bits */
#define ULCON_WLEN_8		(3 << 0)
#define ULCON_STOP_1		(0 << 2)
#define ULCON_PAR_NONE		(0 << 3)
#define ULCON_IRDA		(0 << 4)

/* UCON bits */
#define UCON_TX_IRQ		(1 << 0)
#define UCON_RX_IRQ		(1 << 1)
#define UCON_TX_DMA		(2 << 0)
#define UCON_RX_DMA		(2 << 1)
#define UCON_CLK_PCLK		(0 << 10)
#define UCON_CLK_UCLK		(1 << 10)

/* UFCON bits */
#define UFCON_FIFO_EN		(1 << 0)
#define UFCON_RX_FIFO_RST	(1 << 1)
#define UFCON_TX_FIFO_RST	(1 << 2)

/* UTRSTAT bits */
#define UTRSTAT_RX_READY	(1 << 0)
#define UTRSTAT_TX_EMPTY	(1 << 1)

static inline void uart_w(uint32_t reg, uint32_t val)
{
	*(volatile uint32_t *)(UART_BASE + reg) = val;
}

static inline uint32_t uart_r(uint32_t reg)
{
	return *(volatile uint32_t *)(UART_BASE + reg);
}

void uart_init(void)
{
	/* USI init sequence from Samsung kernel */
	uart_w(USI_CON, 1);		/* USI_SET_RESET */
	for (volatile int i = 0; i < 1000; i++);
	uart_w(USI_CON, 0);		/* USI_RESET */
	for (volatile int i = 0; i < 1000; i++);
	uart_w(USI_OPTION, 2);		/* USI_HWACG_CLKREQ_ON */
	
	/* Set UART mode */
	uint32_t val = uart_r(USI_CON);
	val &= ~7;
	val |= 1;			/* USI_UART_SW_CONF */
	uart_w(USI_CON, val);
	
	/* Reset FIFOs */
	uart_w(0x08, 0x07);		/* UFCON: enable + reset RX/TX */
	for (volatile int i = 0; i < 1000; i++);
	
	/* Line control: 8N1 */
	uart_w(0x00, 3);		/* ULCON: 8N1 */
	
	/* Control: PCLK, IRQ mode (polling for now) */
	uart_w(0x04, 0);		/* UCON */
	
	/* Modem control: no flow control */
	uart_w(0x0C, 0);		/* UMCON */
	
	/* Set baud: 115200 @ 26 MHz */
	/* BRD = 26000000 / (16 * 115200) = 14.1 -> IBRD=14, FBRD=6 */
	uart_w(0x28, 14);		/* UBRDIV */
	
	/* Enable FIFOs */
	uart_w(0x08, 1);		/* UFCON: enable */
	
	/* Enable UART, TX, RX */
	uart_w(0x04, 7);		/* UCON: UART|TX|RX enable */
}

void uart_putc(char c)
{
	/* Wait for TX not full */
	while (uart_r(0x10) & (1 << 2)) ; /* UTRSTAT TX_FULL */
	
	*(volatile uint32_t *)(UART_BASE + 0x20) = (uint32_t)c;
	
	if (c == '\n') {
		while (uart_r(0x10) & (1 << 2)) ;
		*(volatile uint32_t *)(UART_BASE + 0x20) = '\r';
	}
}

char uart_getc(void)
{
	if (!(uart_r(0x10) & (1 << 0)))	/* RX_READY */
		return 0;
	return (char)uart_r(0x24);	/* URXH */
}