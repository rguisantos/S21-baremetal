/* timer.c — R9: generic timer arquitetural como fonte de PREEMPÇÃO
 *
 * Igual ao R8C (validado): CNTP (non-secure physical timer) com
 * interrupção via PPI INTID 30. A diferença é o USO: no R8C o tick só
 * imprimia e voltava ao MESMO loop; no R9 o tick TROCA DE TAREFA.
 *
 * Registradores por-CPU (system registers, não MMIO):
 *   CNTFRQ_EL0   — frequência (só leitura)
 *   CNTPCT_EL0   — contador atual
 *   CNTP_CVAL_EL0— comparador de 64 bits
 *   CNTP_CTL_EL0 — enable / IMASK / ISTATUS
 */

#include "r9.h"

static u64 freq;

void timer_start(unsigned seconds)
{
    freq = MRS(cntfrq_el0);
    u64 now = MRS(cntpct_el0);
    MSR(cntp_cval_el0, now + freq * seconds);
    MSR(cntp_ctl_el0, 1);                    /* enable, imask=0 */
    printf("[TIME] CNTFRQ=%lu Hz  CVAL=now+%lus  CTL=1 (tick = quantum)\n",
           freq, (unsigned long)seconds);
}

void timer_rearm(void)
{
    /* rearma com base no CVAL anterior: sem drift acumulado */
    u64 cval = MRS(cntp_cval_el0);
    MSR(cntp_cval_el0, cval + freq);
}
