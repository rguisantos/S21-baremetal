#ifndef GIC_H
#define GIC_H

#include <stdint.h>

#define GICD_BASE		0x10200000UL
#define GICR_BASE		0x10240000UL

void gic_init(void);
void gic_cpu_interface_init(void);
void gic_enable_irq(uint32_t irq);
void gic_disable_irq(uint32_t irq);
void gic_set_priority(uint32_t irq, uint8_t pri);
uint32_t gic_ack_irq(void);
void gic_eoi(uint32_t irq);
void gic_send_sgi(uint32_t sgi_id, uint32_t target_mask, uint32_t aff1, uint32_t aff2, uint32_t aff3);

#endif