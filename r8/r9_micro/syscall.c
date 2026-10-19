/* syscall.c — R9: camada de syscalls (kernel) e tratamento de IRQ
 *
 * SVC do EL0 chega no slot 8 com EC=0x15 e o imediato da instrução nos
 * bits 15:0 do ISS (DDI0487). Convenção deste kit:
 *   svc #1 write(buf, len)  svc #2 yield()  svc #3 exit()
 *   svc #4 npreempt()       svc #5 puthex(v)
 * Retorno em x0 (0 ok, negativo = -errno).
 *
 * VALIDAÇÃO DE PARÂMETROS (o pedido do R9): o EL0 não pode ditar
 * endereço nenhum ao kernel. A janela do usuário é a imagem carregada
 * [0x40080000, __bss_end) — de onde vêm os literais e as pilhas das
 * tarefas. Sem MMU ligada isso é CONVENÇÃO (o kernel confere e rejeita);
 * com page tables por tarefa (R10) virará física: acesso fora da janela
 * faulta no hardware antes de qualquer checagem do kernel.
 *
 * O IRQ do tick (slot 9) faz o ciclo comprovado do R8C (ACK -> rearma ->
 * EOI) e além disso DECIDE TROCAR DE TAREFA — a diferença do R8C é que
 * aqui a interrupção muda quem roda, não só imprime.
 */

#include "r9.h"

_Static_assert(sizeof(struct r9_frame) == 0x120, "frame: 288 bytes");
_Static_assert(__builtin_offsetof(struct r9_frame, sp_el0) == 248, "off sp_el0");
_Static_assert(__builtin_offsetof(struct r9_frame, elr) == 256, "off elr");
_Static_assert(__builtin_offsetof(struct r9_frame, spsr) == 264, "off spsr");
_Static_assert(__builtin_offsetof(struct r9_frame, esr) == 272, "off esr");
_Static_assert(__builtin_offsetof(struct r9_frame, far) == 280, "off far");

#define USER_WIN_BASE 0x40080000UL   /* base da imagem (linker.ld)  */
#define USER_WIN_MAX  128UL          /* cap de bytes por write()     */

/* janela do usuário: ponteiro + comprimento dentro da imagem carregada,
 * sem wrap de soma e sem estourar o fim */
static int user_ok(const char *buf, u64 len)
{
    u64 b = (u64)buf;
    u64 win_end = (u64)__bss_end;

    if (!buf)
        return 0;                       /* NULL: nem começa          */
    if (len > USER_WIN_MAX)
        return 0;                       /* cap: não valida romances  */
    if (b < USER_WIN_BASE || b >= win_end)
        return 0;                       /* fora da janela             */
    if (len > win_end - b)
        return 0;                       /* estouraria o fim          */
    return 1;
}

static long do_write(struct r9_frame *f)
{
    const char *buf = (const char *)f->x[0];
    u64 len = f->x[1];

    if (!user_ok(buf, len))
        return -14;                     /* EFAULT: ponteiro inválido  */
    for (u64 i = 0; i < len; i++)
        putchar((int)(u8)buf[i]);       /* kernel escreve POR ela     */
    return (long)len;
}

/* tarefa morreu (EXIT ou exceção grave no EL0): resta ver se sobra
 * alguém para rodar — se não, o ciclo fechou e o módulo termina.
 * (o frame f é abandonado: a pilha do kernel da tarefa morta fica lá,
 * intocada, com o frame para sempre — isso é um "leak" de 288 bytes
 * por tarefa morta, o preço honesto da simplicidade.) */
static struct r9_frame *task_die(struct r9_frame *f, const char *why)
{
    struct tcb *o = sched_other();

    (void)f;                            /* frame abandonado onde está   */

    printf("[R9] %c: %s\n", current_task->name, why);
    current_task->state = TS_DEAD;

    if (o->state != TS_DEAD) {
        printf("[R9] %c -> %c (exit)\n", current_task->name, o->name);
        o->state  = TS_RUNNING;
        current_task = o;
        return (struct r9_frame *)o->ksp;
    }

    printf("\n[R9] as duas tarefas terminaram — ciclo do microkernel fechado\n");
    printf("=== R9 PASS — EL0 + SVC + troca de contexto + preempcao ===\n\n");
    shutdown();                         /* noreturn (park se PSCI falhar) */
    park();                             /* ;                                                          */
}

/* slot 8: sync do EL0 */
struct r9_frame *r9_syscall_entry(struct r9_frame *f)
{
    u32 esr = (u32)f->esr;
    u32 ec  = (esr >> 26) & 0x3f;
    u32 imm = esr & 0xffff;

    if (ec != 0x15) {
        /* não foi SVC: instrução indefinida ou trap ilegal DENTRO da
         * tarefa — no R8B isso era o "muro"; aqui o kernel mata a tarefa
         * e a vizinha continua. */
        printf("[R9] %c: excecao sem SVC no EL0: EC=%#x  ESR=%#x  FAR=%p\n",
               current_task->name, ec, esr, (void *)f->far);
        return task_die(f, "abortada por excecao no EL0");
    }

    switch (imm) {
    case SYS_WRITE:
        f->x[0] = (u64)do_write(f);
        return f;                       /* mesma tarefa continua      */

    case SYS_YIELD: {
        struct tcb *o = sched_other();
        if (o->state != TS_DEAD)
            return sched_switch_to(o, f, "yield");
        return f;                       /* sozinha: segue rodando    */
    }

    case SYS_EXIT:
        return task_die(f, "EXIT recebido");

    case SYS_NPREEMPT:
        f->x[0] = current_task->preempt_count;
        return f;

    case SYS_PUTHEX:
        printf("[R9] %c: %#lx\n", current_task->name, f->x[0]);
        return f;

    default:
        f->x[0] = (u64)-22;             /* EINVAL: syscall inexistente */
        printf("[R9] %c: SVC %u desconhecido (ret -22)\n",
               current_task->name, imm);
        return f;
    }
}

/* slot 9: IRQ do EL0 — o tick decide quem roda em seguida */
struct r9_frame *r9_irq_entry(struct r9_frame *f)
{
    u32 intid;
    int from_g0;
    struct r9_frame *ret = f;

    u64 iar = gic_ack(&intid, &from_g0);

    if (intid == 30) {                  /* CNTP: o tick de 1 s         */
        timer_rearm();                  /* rearma ANTES do EOI (R8C)  */
        current_task->preempt_count++;
        struct tcb *o = sched_other();
        if (o->state != TS_DEAD)
            ret = sched_switch_to(o, f, "tick");
    } else if (intid != 0x3ff) {
        printf("[R9] IRQ inesperado: INTID %u\n", intid);
    }

    gic_eoi(iar, from_g0);
    return ret;
}

/* slots que não deviam disparar nunca */
void r9_unexpected_c(void)
{
    printf("\n[R9!!] excecao em slot que nao devia disparar — parando\n");
    park();
}

/* slot 4: bug do kernel (exceção do próprio EL1) */
void r9_kern_panic(u64 esr, u64 elr)
{
    printf("\n[R9!!] excecao DENTRO do kernel: ESR=%#x  ELR=%p — parando\n",
           (u32)esr, (void *)elr);
    park();
}
