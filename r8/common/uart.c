/* uart.c — PL011 da máquina QEMU "virt" em modo polling */

#include "r8lib.h"

#define UART0_BASE   0x09000000UL

#define UART_DR      0x00    /* data register        */
#define UART_FR      0x18    /* flag register        */
#define UART_IBRD    0x24
#define UART_FBRD    0x28
#define UART_CR      0x30    /* control register     */
#define UART_IMSC    0x38
#define UART_ICR     0x44

#define FR_TXFF      (1u << 5)   /* transmit FIFO full  */
#define CR_UARTEN    (1u << 0)
#define CR_TXE       (1u << 8)
#define CR_RXE       (1u << 9)

static volatile u32 *reg(u32 off)
{
    return (volatile u32 *)(UART0_BASE + off);
}

void uart_init(void)
{
    *reg(UART_CR)   = 0;            /* desliga enquanto configura        */
    *reg(UART_ICR)  = 0x7FF;        /* limpa interrupções pendentes      */
    *reg(UART_IBRD) = 13;           /* 24 MHz / (16*115200) ≈ 13.02      */
    *reg(UART_FBRD) = 1;            /* fração 1/64 (relevante só no hw)  */
    *reg(UART_CR)   = CR_UARTEN | CR_TXE | CR_RXE;
}

void uart_putc(char c)
{
    while (*reg(UART_FR) & FR_TXFF)
        ;                           /* espera o FIFO de transmissão abrir */
    *reg(UART_DR) = (u8)c;
}
