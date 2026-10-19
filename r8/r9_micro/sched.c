/* sched.c — R9: TCBs, pilhas e a fabricação de tarefas
 *
 * "Criar uma tarefa" aqui é montar um frame SINTÉTICO no topo da pilha
 * do kernel dela, como se ela tivesse sido interrompida antes de nascer:
 *   elr  = endereço de entrada (o ERET "retorna" para o começo da tarefa)
 *   spsr = 0x0 -> EL0t com DAIF abertos (o timer PODE preemptar)
 *   sp_el0 = topo da pilha própria dela
 *   x0..x30 = 0
 * O dispatcher não sabe distinguir frame fabricado de frame real — e essa
 * uniformidade é o coração do design ("o contexto é a pilha").
 *
 * Scheduler: duas tarefas, round-robin puro — "a outra". Preempção e
 * YIELD usam o mesmo caminho: anotar ksp no TCB, apontar SP p/ a outra.
 */

#include "r9.h"

struct tcb tcbs[2];
struct tcb *current_task;

/* pilhas por tarefa (estáticas -> .bss -> dentro da janela do usuário) */
static u8 kstack_a[0x1000] __attribute__((aligned(16)));
static u8 kstack_b[0x1000] __attribute__((aligned(16)));
static u8 ustack_a[0x2000] __attribute__((aligned(16)));
static u8 ustack_b[0x2000] __attribute__((aligned(16)));

static struct r9_frame *fabricate(struct tcb *t, u64 entry, u64 ktop, u64 utop)
{
    /* o frame mora no TOPO da pilha do kernel (cresce p/ baixo) */
    struct r9_frame *f = (struct r9_frame *)(ktop - sizeof(struct r9_frame));

    memset(f, 0, sizeof(*f));
    f->sp_el0 = utop;
    f->elr    = entry;
    f->spsr   = 0x0;        /* EL0t, DAIF abertos: IRQs funcionam no EL0 */
    t->ksp    = (u64)f;
    t->state  = TS_READY;
    return f;
}

void sched_init(void)
{
    memset(tcbs, 0, sizeof(tcbs));
    tcbs[0].name = 'A';
    tcbs[1].name = 'B';
    fabricate(&tcbs[0], (u64)task_a, (u64)kstack_a + sizeof(kstack_a),
               (u64)ustack_a + sizeof(ustack_a));
    fabricate(&tcbs[1], (u64)task_b, (u64)kstack_b + sizeof(kstack_b),
               (u64)ustack_b + sizeof(ustack_b));
}

void sched_dump(void)
{
    for (int i = 0; i < 2; i++) {
        struct r9_frame *f = (struct r9_frame *)tcbs[i].ksp;
        printf("[R9] tarefa %c fabricada: entry=%p  frame@%p  sp_el0=%p  "
               "spsr=%#lx\n",
               tcbs[i].name, (void *)f->elr, (void *)tcbs[i].ksp,
               (void *)f->sp_el0, f->spsr);
    }
}

struct tcb *sched_other(void)
{
    return current_task == &tcbs[0] ? &tcbs[1] : &tcbs[0];
}

/* anota o frame da tarefa atual e devolve o frame da PRÓXIMA */
struct r9_frame *sched_switch_to(struct tcb *next, struct r9_frame *f,
                                 const char *why)
{
    printf("[R9] %c -> %c (%s)\n", current_task->name, next->name, why);
    current_task->ksp   = (u64)f;
    current_task->state = TS_READY;
    next->state         = TS_RUNNING;
    current_task        = next;
    return (struct r9_frame *)next->ksp;
}
