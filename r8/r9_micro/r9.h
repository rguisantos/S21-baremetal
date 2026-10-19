/* r9.h — tipos e contratos do microkernel R9
 *
 * Kit R9 (novo módulo do mesmo projeto): duas tarefas no EL0, SVC com
 * validação, troca de contexto completo e preempção por timer.
 *
 * Contrato do frame (idêntico ao layout gravado pelo vectors.S):
 *   [  0..247] x0..x30     (x_i em 8*i — x29@232, x30@240)
 *   [248] sp_el0            SP do EL0 banked (a tarefa tem pilha própria)
 *   [256] elr_el1           PC de retorno (ERET lê daqui)
 *   [264] spsr_el1          PSTATE de retorno (ERET restaura daqui)
 *   [272] esr_el1  [280] far_el1   (preenchidos só no caminho sync)
 *
 * Decisão de projeto: cada tarefa tem DUAS pilhas —
 *   - pilha do EL0 (dela mesma, apontada por SP_EL0);
 *   - pilha do kernel (por tarefa!) que carrega o frame de exceção.
 * Como o kernel roda sempre com IRQ mascarado (DAIF=1 no EL1), nunca
 * há dois frames vivos na mesma pilha — "o contexto É a pilha".
 */

#ifndef R9_H
#define R9_H

#include "r8lib.h"          /* uart/printf/util/sys.S + MRS/MSR + tipos */

struct r9_frame {
    u64 x[31];       /* 0..247   — x_i em 8*i                        */
    u64 sp_el0;      /* 248                                                  */
    u64 elr;         /* 256                                                  */
    u64 spsr;        /* 264                                                  */
    u64 esr;         /* 272 — só no caminho sync                           */
    u64 far;         /* 280 — só no caminho sync                           */
};

/* imediato do SVC = número da chamada (ISS bits 15:0 do ESR) */
enum {
    SYS_WRITE   = 1,   /* x0=buf, x1=len — kernel VALIDA o ponteiro   */
    SYS_YIELD   = 2,   /* entrega a CPU por vontade própria          */
    SYS_EXIT    = 3,   /* tarefa termina                             */
    SYS_NPREEMPT = 4,  /* quantas vezes fui preemptada pelo timer     */
    SYS_PUTHEX  = 5,   /* kernel imprime um valor hex por mim (x0)    */
};

/* ---- sched.c ---- */
enum { TS_DEAD = 0, TS_READY = 1, TS_RUNNING = 2 };

struct tcb {
    char name;
    int  state;
    u64  ksp;             /* frame atual da tarefa (na pilha do kernel) */
    u64  preempt_count;    /* quantas vezes o tick a tirou da CPU         */
};

extern struct tcb tcbs[2];
extern struct tcb *current_task;

void              sched_init(void);   /* fabrica A e B (frames sintéticos) */
void              sched_dump(void);   /* prova os endereços na console    */
struct tcb       *sched_other(void);
struct r9_frame  *sched_switch_to(struct tcb *next, struct r9_frame *f,
                                  const char *why);

/* ---- syscall.c (entry points chamados pelo vectors.S) ---- */
struct r9_frame  *r9_syscall_entry(struct r9_frame *f);
struct r9_frame  *r9_irq_entry(struct r9_frame *f);
void              r9_unexpected_c(void) __attribute__((noreturn));
void              r9_kern_panic(u64 esr, u64 elr) __attribute__((noreturn));

/* ---- tasks.c (código de EL0) ---- */
void task_a(void);
void task_b(void);

/* ---- gic.c (R9: mesmo bring-up comprovado do R8C) ---- */
void gic_init(void);
u64  gic_ack(u32 *intid, int *from_g0);
void gic_eoi(u64 iar, int from_g0);

/* ---- timer.c (R9) ---- */
void timer_start(unsigned seconds);
void timer_rearm(void);

/* ---- vectors.S ---- */
void r9_dispatch(u64 ksp) __attribute__((noreturn));

/* ---- linker.ld ---- */
extern char __bss_end[];   /* fim da imagem carregada (janela do usuário) */

#endif /* R9_H */
