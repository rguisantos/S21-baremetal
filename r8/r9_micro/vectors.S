/*
 * vectors.S — R9: tabela de vetores com troca de contexto embutida
 *
 * Diferença central para o vectors.S do R8: aqui o handler C devolve o
 * frame* DA TAREFA QUE DEVE CONTINUAR — a mesma ou a outra. O stub então:
 *   1. troca SP_EL1 para a pilha do kernel daquela tarefa (frame nela);
 *   2. regrava ELR_EL1/SPSR_EL1/SP_EL0 a partir do frame ALVO
 *      (o ERET não restaura SP_EL0 — quem devolve é aqui, DDI0487 B1.9.1);
 *   3. restaura x0..x30 do frame e executa ERET.
 * Com isso, "salvar o contexto" = deixar o frame na pilha do kernel da
 * tarefa e anotar o SP no TCB; "trocar" = apontar SP p/ a outra pilha.
 *
 * Slots que disparam de verdade (DDI0487, tabela de 16 slots de 0x80):
 *   8  sync do EL0 (AArch64)  — AQUI chegam os SVC das tarefas (EC=0x15)
 *   9  IRQ  do EL0            — AQUI chega o tick (preempção)
 * O kernel roda de DAIF mascarado, então nenhum IRQ sobe com a CPU no
 * EL1; exceção do EL1 (slot 4) é bug do kernel — dump e para.
 *
 * Frame (288 = 0x120 bytes) — ver struct r9_frame no r9.h:
 *   x0..x30 @ 8*i (x29@232, x30@240), sp_el0@248, elr@256, spsr@264,
 *   esr@272, far@280.
 * Nota histórica: o push do R8 usava "stp x29,x30,[sp,#-0x130]!" e depois
 * sobrescrevia 0/8 com x0/x1 — os slots 232/240 ficavam sem gravar.
 * Aqui cada registrador cai UMA vez no seu slot, de forma explícita.
 */

.section .vectors, "ax"

.balign 0x800
.global vectors
vectors:
    /* 0-3: EL1 usando SP_EL0 — impossível no R9 (kernel sempre SPSel=1) */
    .balign 0x80
    b       r9_unexpected
    .balign 0x80
    b       r9_unexpected
    .balign 0x80
    b       r9_unexpected
    .balign 0x80
    b       r9_unexpected

    /* 4: sync no EL1 com SP_EL1 — bug do KERNEL: dump e park */
    .balign 0x80
    b       r9_kern_sync
    /* 5: IRQ no EL1 — não deve existir (kernel roda de DAIF mascarado) */
    .balign 0x80
    b       r9_unexpected
    /* 6: FIQ   7: SError */
    .balign 0x80
    b       r9_unexpected
    .balign 0x80
    b       r9_unexpected

    /* 8: sync de EL0 (AArch64) — os SVC das tarefas chegam aqui */
    .balign 0x80
    b       r9_el0_sync
    /* 9: IRQ de EL0 — o tick do timer preempta a tarefa aqui */
    .balign 0x80
    b       r9_el0_irq
    /* 10: FIQ de EL0   11: SError de EL0 */
    .balign 0x80
    b       r9_unexpected
    .balign 0x80
    b       r9_unexpected

    /* 12-15: EL menor em AArch32 — não existe neste kit */
    .balign 0x80
    b       r9_unexpected
    .balign 0x80
    b       r9_unexpected
    .balign 0x80
    b       r9_unexpected
    .balign 0x80
    b       r9_unexpected

/* ---------------------------------------------------------------
 * Stubs (fora da tabela — os slots só desviam).
 * --------------------------------------------------------------- */
.section .text

/* slot que nunca deveria disparar: pilha dedicada, mensagem, park */
r9_unexpected:
    msr     spsel, #1
    ldr     x0, =__exc_stack_top
    mov     sp, x0
    bl      r9_unexpected_c
1:  wfe
    b       1b

/* bug dentro do kernel: entrega ESR/ELR ao C e para */
r9_kern_sync:
    mrs     x0, esr_el1
    mrs     x1, elr_el1
    bl      r9_kern_panic
1:  wfe
    b       1b

/* ---- gravar frame: cada registrador UMA vez no seu slot ---- */
.macro R9_FRAME_SAVE
    sub     sp, sp, #0x120
    stp     x29, x30, [sp, #232]     /* x[29], x[30] — os slots de verdade */
    stp     x27, x28, [sp, #216]
    stp     x25, x26, [sp, #200]
    stp     x23, x24, [sp, #184]
    stp     x21, x22, [sp, #168]
    stp     x19, x20, [sp, #152]
    stp     x17, x18, [sp, #136]
    stp     x15, x16, [sp, #120]
    stp     x13, x14, [sp, #104]
    stp     x11, x12, [sp, #88]
    stp     x9,  x10, [sp, #72]
    stp     x7,  x8,  [sp, #56]
    stp     x5,  x6,  [sp, #40]
    stp     x3,  x4,  [sp, #24]
    stp     x1,  x2,  [sp, #8]
    str     x0,      [sp, #0]
    mrs     x1, sp_el0               /* x1 já está salvo no slot 8        */
    str     x1, [sp, #248]
    mrs     x1, elr_el1
    str     x1, [sp, #256]
    mrs     x1, spsr_el1
    str     x1, [sp, #264]
.endm

/* ---- retomar frame: sp aponta para o frame ALVO (mesma ou OUTRA
 *      tarefa — a troca aconteceu no "mov sp, x0" antes daqui) ---- */
.macro R9_FRAME_RESTORE
    ldr     x1, [sp, #256]
    msr     elr_el1, x1              /* ERET lê ELR/SPSR dos registradores */
    ldr     x1, [sp, #264]
    msr     spsr_el1, x1
    ldr     x1, [sp, #248]
    msr     sp_el0, x1               /* ERET NÃO devolve SP_EL0 — aqui    */
    ldr     x0,      [sp, #0]
    ldp     x1,  x2,  [sp, #8]
    ldp     x3,  x4,  [sp, #24]
    ldp     x5,  x6,  [sp, #40]
    ldp     x7,  x8,  [sp, #56]
    ldp     x9,  x10, [sp, #72]
    ldp     x11, x12, [sp, #88]
    ldp     x13, x14, [sp, #104]
    ldp     x15, x16, [sp, #120]
    ldp     x17, x18, [sp, #136]
    ldp     x19, x20, [sp, #152]
    ldp     x21, x22, [sp, #168]
    ldp     x23, x24, [sp, #184]
    ldp     x25, x26, [sp, #200]
    ldp     x27, x28, [sp, #216]
    ldp     x29, x30, [sp, #232]
    add     sp, sp, #0x120
    eret
.endm

/* 8: SYNC do EL0 — decodifica ESR/FAR, chama o kernel C, retoma o
 *     frame que o kernel escolher (trocar de tarefa é só trocar SP). */
r9_el0_sync:
    R9_FRAME_SAVE
    mrs     x1, esr_el1
    str     x1, [sp, #272]
    mrs     x1, far_el1
    str     x1, [sp, #280]
    mov     x0, sp                   /* frame*                            */
    bl      r9_syscall_entry
    mov     sp, x0                   /* pilha da tarefa que vai rodar     */
    R9_FRAME_RESTORE

/* 9: IRQ do EL0 — ACK/EOI + decisão de preempção no C. */
r9_el0_irq:
    R9_FRAME_SAVE
    mov     x0, sp
    bl      r9_irq_entry
    mov     sp, x0
    R9_FRAME_RESTORE

/* r9_dispatch(ksp) — primeiro voo: entra no frame fabricado de uma
 * tarefa e nunca retorna (o kernel só volta como exception handler).
 * main() chama UMA vez; a partir daqui a CPU vive no EL0 até morar. */
.global r9_dispatch
r9_dispatch:
    mov     sp, x0
    R9_FRAME_RESTORE
