/* timer.c — R8C: generic timer arquitetural como fonte de interrupção
 *
 * Registradores por-CPU (system registers, não MMIO):
 *   CNTFRQ_EL0   — frequência do contador (só leitura)
 *   CNTPCT_EL0   — contador atual (só leitura)
 *   CNTP_CVAL_EL0— comparador de 64 bits (dispara quando CVAL <= CNT)
 *   CNTP_CTL_EL0 — IMASK / ISTATUS / enable
 * A interrupção sai como PPI INTID 30 no GIC.
 */

#include "r8lib.h"

static u64 freq;

void timer_start(unsigned seconds)
{
    freq = MRS(cntfrq_el0);
    u64 now = MRS(cntpct_el0);
    MSR(cntp_cval_el0, now + freq * seconds);
    MSR(cntp_ctl_el0, 1);                    /* enable, imask=0 */
    printf("[TIME] CNTFRQ=%lu Hz  CVAL=now+%lus  CTL=1\n", freq, (unsigned long)seconds);
}

void timer_rearm(void)
{
    /* rearma com base no CVAL anterior: sem drift acumulado */
    u64 cval = MRS(cntp_cval_el0);
    MSR(cntp_cval_el0, cval + freq);
}
