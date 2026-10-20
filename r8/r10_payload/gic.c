/* gic.c — R10: GIC-600 driver for Exynos 2100 */

#include "r10.h"

static u32 gicd_read(u32 reg) { return mmio_read32(GICD_BASE + reg); }
static void gicd_write(u32 reg, u32 val) { mmio_write32(GICD_BASE + reg, val); }

static u32 gicr_read(u32 reg, u32 cpu) { 
    return mmio_read32(GICR_BASE + 0x20000 * cpu + reg); 
}
static void gicr_write(u32 reg, u32 val, u32 cpu) { 
    mmio_write32(GICR_BASE + 0x20000 * cpu + reg, val); 
}

void gic_init(void)
{
    u32 typer = gicd_read(0x0004);
    u32 cpu_count = ((typer >> 5) & 0x7) + 1;
    u32 spi_count = ((typer >> 0) & 0x1F) + 1;
    spi_count = spi_count * 32;
    
    uart_puts("GICD_TYPER: "); uart_puthex(typer); uart_putc('\n');
    uart_puts("CPU interfaces: "); uart_puthex(cpu_count); uart_putc('\n');
    uart_puts("SPI count: "); uart_puthex(spi_count); uart_putc('\n');
    
    /* Disable distributor */
    gicd_write(0x0000, 0);
    
    /* Configure GICD_CTLR */
    u32 ctlr = GICD_CTLR_EN_GRP0 | GICD_CTLR_EN_GRP1NS | GICD_CTLR_ARE_NS | GICD_CTLR_DS;
    gicd_write(0x0000, ctlr);
    
    /* Set all SPIs to Group 1 Non-secure, level-triggered, default priority */
    for (int i = 32; i < spi_count; i += 32) {
        gicd_write(0x0080 + i/32*4, 0xFFFFFFFF);      // IGROUPR: all Group 1
        gicd_write(0x0C00 + i/16*4, 0x55555555);      // ICFGR: level-triggered
        gicd_write(0x0D00 + i/32*4, 0x00000000);      // IGRPMODR: Group 1 NS
    }
    
    /* Set default priority for all SPIs */
    for (int i = 32; i < spi_count; i++) {
        gicd_write(0x0400 + i, 0xA0);  // Priority 0xA0 (mid)
    }
    
    /* Enable all SPIs */
    for (int i = 32; i < spi_count; i += 32) {
        gicd_write(0x0100 + i/32*4, 0xFFFFFFFF);  // ISENABLER
    }
    
    /* Initialize each CPU's redistributor */
    for (int cpu = 0; cpu < cpu_count; cpu++) {
        /* Wake up redistributor */
        u32 waker = gicr_read(0x0014, cpu);
        waker &= ~GICR_WAKER_PROCESSOR_SLEEP;
        gicr_write(0x0014, waker, cpu);
        
        /* Wait for children awake */
        int timeout = 100000;
        while ((gicr_read(0x0014, cpu) & GICR_WAKER_CHILDREN_ASLEEP) && timeout--)
            ;
        
        /* Enable Group 0 and Group 1 NS in redistributor */
        gicr_write(0x0000, 0x3, cpu);  // GICR_CTLR
        
        /* Set priority mask to allow all */
        mmio_write32(GICR_SGI_BASE + 0x0000 + 0x00, 0xFF);  // GICR_SGI_PMR
        
        /* Enable Group 1 NS in CPU interface */
        mmio_write32(GICR_SGI_BASE + 0x100 + 0x00, 0x1);  // GICR_SGI_CTLR
    }
    
    /* Set current CPU's PMR to allow all priorities */
    mmio_write32(GICR_SGI_BASE + 0x0000 + 0x00, 0xFF);
    
    /* Enable CPU interface */
    mmio_write32(GICR_SGI_BASE + 0x100 + 0x00, 0x1);
    
    uart_puts("GIC-600 initialized for ");
    uart_puthex(cpu_count);
    uart_puts(" CPUs\n");
}

void gic_enable_irq(u32 irq)
{
    if (irq < 32) {
        /* SGI/PPI - per CPU */
        u32 cpu = get_current_cpu();
        gicr_write(0x0100, 1 << irq, cpu);
    } else {
        /* SPI - distributor */
        gicd_write(0x0100 + (irq/32)*4, 1 << (irq%32));
    }
}

void gic_disable_irq(u32 irq)
{
    if (irq < 32) {
        u32 cpu = get_current_cpu();
        gicr_write(0x0180, 1 << irq, cpu);
    } else {
        gicd_write(0x0180 + (irq/32)*4, 1 << (irq%32));
    }
}

void gic_set_priority(u32 irq, u8 priority)
{
    if (irq < 32) {
        u32 cpu = get_current_cpu();
        gicr_write(0x0400 + irq, priority, cpu);
    } else {
        gicd_write(0x0400 + irq, priority);
    }
}

void gic_eoi(u32 irq)
{
    /* Write to EOIR register */
    if (irq < 32) {
        mmio_write32(GICR_SGI_BASE + 0x0010, irq);  // GICR_SGI_EOIR
    } else {
        mmio_write32(GICD_BASE + 0x0010, irq);  // GICD_EOIR
    }
}