/* main.c — R8C: exceções + GICv3 + generic timer
 *
 * Demonstra preempção de verdade: o loop principal (texto protegido
 * por DAIF) é interrompido a cada segundo pelo handler de IRQ, que
 * faz o ciclo completo ACK -> tratar -> rearma -> EOI.
 *
 * Rodar com:  -M virt,gic-version=3,virtualization=on
 *   (virtualization=on da o EL2: e no EL2 que se programa
 *    CNTHCTL_EL2/ICC_SRE_EL2 antes do drop para o EL1)
 */

#include "r8lib.h"

/* binutils 2.44 não conhece os NOMES ICC_EOR*_EL1 — usamos os encodings
 * numéricos (equivalentes): ICC_EOR1_EL1 = s3_0_c12_c12_1,
 *                           ICC_EOR0_EL1 = s3_0_c12_c8_1 */
#define MSR_EOR1(v) asm volatile("msr s3_0_c12_c12_1, %0" :: "r"((u64)(v)) : "memory")
#define MSR_EOR0(v) asm volatile("msr s3_0_c12_c8_1,  %0" :: "r"((u64)(v)) : "memory")

void gic_init(void);
void timer_start(unsigned seconds);
void timer_rearm(void);

static volatile unsigned ticks;

/* versão FORTE do hook — sobrepõe a default de exc.c */
void irq_hook(struct exc_frame *f)
{
    (void)f;
    u64 iar = MRS(icc_iar1_el1);              /* ACK (Group 1)      */
    u32 intid = (u32)(iar & 0xffffff);
    int from_g0 = 0;

    if (intid == 0x3ff) {                     /* spurious no G1?    */
        iar = MRS(icc_iar0_el1);              /* tenta Group 0      */
        intid = (u32)(iar & 0xffffff);
        from_g0 = 1;
    }

    if (intid == 30) {
        ticks++;
        printf("   [TICK %u] IRQ do timer preemptou o loop\n", ticks);
        timer_rearm();                        /* ANTES do EOI: o    */
    } else if (intid != 0x3ff) {              /* nivel tem que cair */
        printf("[IRQ] INTID inesperado: %u\n", intid);
    }

    if (intid != 0x3ff) {                      /* EOI so' com INTID real */
        if (from_g0)
            MSR_EOR0(iar);                     /* EOI no grupo certo */
        else
            MSR_EOR1(iar);
    }
}

void module_main(unsigned entry_el)
{
    uart_init();
    printf("\n");
    puts("=== R8C — Excecoes + GICv3 + generic timer ===");
    printf("entry: CurrentEL = EL%u\n", entry_el);

    if (entry_el == 3) {
        drop_from_el3_to_el2((u64)el2_trampoline);
    } else if (entry_el == 2) {
        el2_stage();
    } else if (entry_el == 1) {
        el1_stage();
    } else {
        park();
    }
    park();
}

void el2_stage(void)
{
    gic_init();                    /* GIC configurado no EL2        */
    puts("[EL2] ERET -> EL1h: SPSR_EL2=0x3c5");
    drop_from_el2_to_el1((u64)el1_trampoline);
    park();
}

void el1_stage(void)
{
    printf("[EL1] CurrentEL=%u. VBAR_EL1=%p\n", get_current_el(), vectors);
    vbar_install();

    /* CPU interface do EL1: prioridade máxima de corte + enable G1 */
    MSR(icc_pmr_el1,     0xff);
    MSR(icc_igrpen1_el1, 1);

    timer_start(1);                /* 1 segundo                     */

    /* desmascara IRQ e FIQ no PSTATE (DAIF) */
    asm volatile("msr daifclr, #3");
    puts("[EL1] IRQs desmascarados — loop principal ate 5 ticks\n");

    volatile unsigned long spin = 0;
    while (ticks < 5) {
        spin++;
        if ((spin & 0x3ffffff) == 0) {
            asm volatile("msr daifset, #2");      /* mascara IRQ  */
            printf("[LOOP] girando: spin=%lu  ticks=%u\n", spin, ticks);
            asm volatile("msr daifclr, #2");      /* desmascara   */
        }
    }

    asm volatile("msr daifset, #2");           /* silencia IRQs       */
    MSR(cntp_ctl_el0, 0);                      /* desliga o comparador */
    printf("\n=== R8C PASS — %u ticks, %lu spins: preempcao real ===\n\n",
           ticks, spin);
    shutdown();
}
