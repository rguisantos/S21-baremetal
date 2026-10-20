/* mct.c — R10: MCT (Multi-Core Timer) driver for Exynos 2100 */

#include "r10.h"

#define MCT_CHANNELS 4

static u64 mct_freq = 26000000;  // 26 MHz from DTB

void mct_init(void)
{
    /* Enable global counter */
    u32 gcon = mmio_read32(MCT_GLOBAL_CON);
    gcon |= MCT_GLOBAL_CON_EN;
    mmio_write32(MCT_GLOBAL_CON, gcon);
    
    /* Configure local timers for each channel */
    for (int i = 0; i < MCT_CHANNELS; i++) {
        /* Disable local timer first */
        mmio_write32(MCT_LOCAL_CON(i), 0);
        
        /* Set compare value for 1ms tick @ 26 MHz */
        u64 cmp = mct_freq / 1000;  // 1ms
        mmio_write32(MCT_LOCAL_CMP(i), (u32)cmp);
        mmio_write32(MCT_LOCAL_UPDATE(i), (u32)(cmp >> 32));
        
        /* Enable local timer with interrupt, auto-reload */
        u32 lcon = MCT_LOCAL_CON_EN | MCT_LOCAL_CON_INTEN | MCT_LOCAL_CON_AUTO;
        mmio_write32(MCT_LOCAL_CON(i), lcon);
        
        /* Enable interrupt in global */
        u32 intenb = mmio_read32(MCT_INT_ENB);
        intenb |= (1 << i);
        mmio_write32(MCT_INT_ENB, intenb);
    }
    
    /* Enable MCT interrupts in GIC (SPI 224-227) */
    gic_enable_irq(224);
    gic_enable_irq(225);
    gic_enable_irq(226);
    gic_enable_irq(227);
    
    uart_puts("MCT: Global counter enabled, 4 channels @ 1ms\n");
}

u64 mct_read_global(void)
{
    return ((u64)mmio_read32(MCT_GLOBAL_CNT + 4) << 32) | mmio_read32(MCT_GLOBAL_CNT);
}

u64 mct_read_local(int ch)
{
    return ((u64)mmio_read32(MCT_LOCAL_CNT(ch) + 4) << 32) | mmio_read32(MCT_LOCAL_CNT(ch));
}

void mct_udelay(u32 us)
{
    u64 start = mct_read_global();
    u64 ticks = (u64)us * mct_freq / 1000000;
    while ((mct_read_global() - start) < ticks)
        ;
}

void mct_mdelay(u32 ms)
{
    while (ms--) mct_udelay(1000);
}

/* MCT interrupt handler (called from exc_irq) */
void mct_handle_irq(u32 irq)
{
    u32 cstat = mmio_read32(MCT_INT_CSTAT);
    
    for (int i = 0; i < MCT_CHANNELS; i++) {
        if (cstat & (1 << i)) {
            /* Clear interrupt */
            mmio_write32(MCT_INT_CSTAT, 1 << i);
            
            /* Handle channel interrupt */
            if (i == 0) {
                /* Channel 0: system tick */
                // tick_handler();
            }
        }
    }
}