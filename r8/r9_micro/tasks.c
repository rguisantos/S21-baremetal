/* tasks.c — R9: o código que roda no EL0 (o "usuário" do microkernel)
 *
 * Regra de honestidade pedagógica: a tarefa só fala com o mundo via
 * SVC. Nada de printf/uart direto — apesar de estarmos na mesma imagem
 * (sem MMU não há isolamento físico), a disciplina mostra o modelo:
 * quem pede é o usuário; quem escreve é o kernel, depois de validar.
 *
 * Tarefa A ("educada"): prova os dois lados do SVC — aceito e rejeitado
 *   - escreve linhas normais (ponteiro válido);
 *   - tenta NULL e tenta apontar p/ a UART física (MMIO): o kernel deve
 *     REJEITAR os dois (EFAULT), e a tarefa confere o retorno;
 *   - YIELD voluntário três vezes (troca por vontade própria).
 * Tarefa B ("teimosa"): nunca chama YIELD — gira chamando SYS_NPREEMPT
 *   até o timer a tirar da CPU 3 vezes. O contexto volta inteiro
 *   (x0-x30, SP, ELR, SPSR) porque o frame guardou tudo.
 * No fim as duas chamam EXIT; quando ambas morrem, o kernel encerra.
 */

#include "r9.h"

/* wrappers SVC: número da chamada vai no IMEDIATO da instrução
 * (ISS bits 15:0), parâmetros em x0/x1, retorno em x0. */
static long sys_write(const char *b, unsigned long n)
{
    register long x0 __asm__("x0") = (long)b;
    register long x1 __asm__("x1") = (long)n;
    __asm__ volatile("svc #1" : "+r"(x0) : "r"(x1) : "memory");
    return x0;
}

static long sys_yield(void)
{
    register long x0 __asm__("x0") = 0;
    __asm__ volatile("svc #2" : "+r"(x0) :: "memory");
    return x0;
}

static long sys_exit(void)
{
    register long x0 __asm__("x0") = 0;
    __asm__ volatile("svc #3" : "+r"(x0) :: "memory");
    return x0;
}

static long sys_npreempt(void)
{
    register long x0 __asm__("x0") = 0;
    __asm__ volatile("svc #4" : "+r"(x0) :: "memory");
    return x0;
}

static long sys_puthex(u64 v)
{
    register long x0 __asm__("x0") = (long)v;
    __asm__ volatile("svc #5" : "+r"(x0) :: "memory");
    return x0;
}

/* tamanho da própria string: aritmética sobre a PRÓPRIA memória —
 * nada privilegiado nisso (strlen de usuário é igual no Linux) */
static int slen(const char *s)
{
    int n = 0;
    while (s[n])
        n++;
    return n;
}

#define SAY(s) sys_write(s, (unsigned long)slen(s))

/* o SP do EL0 é legível no próprio EL0 — prova de que cada tarefa
 * tem pilha PRÓPRIA (o kernel imprime o valor de graça via SVC #5) */
static u64 user_sp(void)
{
    u64 sp;
    __asm__ volatile("mov %0, sp" : "=r"(sp));
    return sp;
}

void task_a(void)
{
    sys_puthex(user_sp());
    SAY("A: nasci no EL0 — esta linha saiu por SVC #1 (kernel validou o ponteiro)\n");

    if (sys_write((const char *)0, 1) < 0)
        SAY("A: NULL rejeitado pelo kernel (ret -14) — EFAULT e' lei\n");
    else
        SAY("A: PROBLEMA: kernel aceitou NULL!\n");

    if (sys_write((const char *)0x09000000UL, 4) < 0)
        SAY("A: apontar pra UART fisica (MMIO) rejeitado: fora da janela do usuario\n");
    else
        SAY("A: PROBLEMA: kernel aceitou ponteiro de MMIO!\n");

    SAY("A: sem MMU a janela e' convencao do kernel; com page tables (R10) sera' fisica\n");

    SAY("A: rodada 1 de 3 — YIELD voluntario\n");
    sys_yield();
    SAY("A: rodada 2 de 3 — YIELD voluntario\n");
    sys_yield();
    SAY("A: rodada 3 de 3 — YIELD voluntario\n");
    sys_yield();

    SAY("A: terminei — EXIT\n");
    sys_exit();
}

void task_b(void)
{
    static const char *marcos[] = {
        "B: preemptada 1a vez — o tick trocou de contexto sem eu pedir\n",
        "B: preemptada 2a vez — meu contexto voltou inteiro (x0-x30, SP, ELR, SPSR)\n",
        "B: preemptada 3a vez — chega, vou terminar enquanto o kernel observa\n",
    };

    sys_puthex(user_sp());
    SAY("B: nasci no EL0 — vou girar SEM yield: so o timer me tira daqui\n");

    unsigned seen = 0;
    for (;;) {
        long n = sys_npreempt();
        if (n > 0 && (unsigned)n > seen && (unsigned)n <= 3) {
            seen = (unsigned)n;
            sys_write(marcos[seen - 1], (unsigned long)slen(marcos[seen - 1]));
            if (seen == 3)
                break;
        }
    }

    SAY("B: fim da sessao: 3 preempcoes sem nunca cooperar — EXIT\n");
    sys_exit();
}
