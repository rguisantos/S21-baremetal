/* main.c — R9: bring-up do microkernel
 *
 * Camada a camada (tudo já comprovado nos módulos R8, agora junto):
 *   boot no EL2 (virt sem secure=on) -> gic_init -> ERET p/ EL1h
 *   VBAR_EL1 (tabela nova, com troca de contexto), ICC do EL1,
 *   timer de 1 s (fonte da preempção), fabricação das duas tarefas,
 *   e o dispatch: o kernel "retorna" p/ dentro da tarefa A e daquele
 *   momento só volta ao EL1 como exception handler (SVC, tick, ou morte).
 *
 * Rodar com:  -M virt,gic-version=3,virtualization=on
 */

#include "r9.h"

void module_main(unsigned entry_el)
{
    uart_init();
    printf("\n");
    puts("=== R9 — microkernel: EL0, SVC, troca de contexto, preempcao ===");
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
    gic_init();               /* GIC configurado no EL2 (R8C comprovado) */
    puts("[EL2] ERET -> EL1h: SPSR_EL2=0x3c5 — o kernel vive no EL1");
    drop_from_el2_to_el1((u64)el1_trampoline);
    park();
}

void el1_stage(void)
{
    printf("[EL1] kernel: CurrentEL=%u  VBAR_EL1=%p\n",
           get_current_el(), vectors);
    vbar_install();

    /* CPU interface do EL1: prioridade máxima de corte + enable G1 */
    MSR(icc_pmr_el1,     0xff);
    MSR(icc_igrpen1_el1, 1);

    /* o quantum: tick de 1 s — quem decide o uso dele é o handler */
    timer_start(1);

    /* as duas tarefas do mundo, fabricadas em frames sintéticos */
    sched_init();
    sched_dump();

    /* NOTA: o kernel NUNCA desmascara DAIF aqui. O EL1 inteiro roda com
     * IRQs mascarados (SPSR 0x3c5 herdado do drop); quem roda com DAIF
     * aberto é o EL0 (SPSR=0x0 do frame). Logo todo IRQ do timer chega
     * pelo slot 9 (de EL0) — nunca dentro do kernel — e o handler não
     * precisa se proteger de aninhamento. */

    printf("[R9] dispatch inicial: kernel -> A (ERET p/ dentro do EL0)\n");
    current_task = &tcbs[0];
    tcbs[0].state = TS_RUNNING;
    r9_dispatch(tcbs[0].ksp);        /* nunca retorna */

    park();                          /* inalcançável */
}
