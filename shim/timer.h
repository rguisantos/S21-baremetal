#ifndef TIMER_H
#define TIMER_H

#include <stdint.h>

void timer_init(void);
uint64_t timer_read_cnt(void);
uint64_t timer_read_freq(void);
void timer_handle_irq(void);
void timer_udelay(uint32_t us);
void timer_mdelay(uint32_t ms);

#endif