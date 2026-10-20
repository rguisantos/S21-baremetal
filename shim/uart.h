#ifndef UART_H
#define UART_H

#include <stdint.h>

#define UART1_BASE		0x10840000UL

void uart_init(void);
void uart_putc(char c);
char uart_getc(void);

#endif