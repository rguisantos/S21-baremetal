/* timer.c — R10: Architected timer driver (CNTP) */

#include "r10.h"

static u64 cntfrq = 26000000;  // 26 MHz from DTB

void timer_init(void)
{
    /* Read CNTFRQ_EL0 (set by firmware) */
    cntfrq = mrs_cntfrq_el0();
    if (cntfrq == 0) cntfrq = 26000000;  // Fallback
    
    uart_puts("Timer freq: "); uart_puthex(cntfrq); uart_puts(" Hz\n");
    
    /* Disable timer */
    msr_cntp_ctl_el0(0);
    
    /* Set compare value for 1ms tick */
    u64 cval = mrs_cntpct_el0() + (cntfrq / 1000);
    msr_cntp_cval_el0(cval);
    
    /* Enable timer: ENABLE=1, IMASK=0, ISTATUS=0 */
    msr_cntp_ctl_el0(1);
    
    /* Enable PPI 30 (CNTP) in GIC */
    gic_enable_irq(30);
    gic_set_priority(30, 0x80);
    
    uart_puts("Architected timer (CNTP) enabled @ 1ms\n");
}

u64 timer_read_cnt(void)
{
    return mrs_cntpct_el0();
}

u64 timer_read_freq(void)
{
    return cntfrq;
}

void timer_set_next(u64 ticks)
{
    u64 cval = mrs_cntpct_el0() + ticks;
    msr_cntp_cval_el0(cval);
}

void timer_disable(void)
{
    msr_cntp_ctl_el0(0);
    gic_disable_irq(30);
}

/* Timer interrupt handler (called from exc_irq for IRQ 30) */
void timer_handle_irq(void)
{
    /* Acknowledge by setting next compare */
    u64 cval = mrs_cntpct_el0() + (cntfrq / 1000);
    msr_cntp_cval_el0(cval);
    
    /* Signal EOI to GIC */
    gic_eoi(30);
    
    /* Call scheduler tick if needed */
    // sched_tick();
}

void timer_udelay(u32 us)
{
    u64 start = timer_read_cnt();
    u64 ticks = (u64)us * cntfrq / 1000000;
    while ((timer_read_cnt() - start) < ticks)
        ;
}

void timer_mdelay(u32 ms)
{
    while (ms--) timer_udelay(1000);
}