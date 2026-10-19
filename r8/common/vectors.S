/*
 * vectors.S — tabela de exceções AArch64 (EL1) + trampolines de frame
 *
 * Layout da tabela (16 slots de 0x80 bytes, total 0x800, alinhamento
 * 2 KB — cada slot tem espaço para 32 instruções):
 *
 *   linha = contexto no momento da exceção, coluna = tipo
 *   ---------------------------------------------------------------
 *    0- 3: EL atual, usando SP_EL0     | Sync | IRQ | FIQ | SError
 *    4- 7: EL atual, usando SP_ELx     | Sync | IRQ | FIQ | SError
 *    8-11: EL menor, AArch64           | ...
 *   12-15: EL menor, AArch32           | ...
 *
 * Nos demos sempre rodamos com SPSel=1 (SP_ELx), então os slots que
 * realmente disparam são 4-7. Os outros desviam para exc_unexpected
 * (imprime e para — nunca deveriam disparar).
 */

.section .vectors, "ax"

.balign 0x800
.global vectors
vectors:
    /* 0-3: EL atual com SP_EL0 — não usado (SP insano) */
    .balign 0x80
    b       exc_unexpected
    .balign 0x80
    b       exc_unexpected
    .balign 0x80
    b       exc_unexpected
    .balign 0x80
    b       exc_unexpected

    /* 4: Sync  — EL atual, SP_ELx  (o caminho real dos demos) */
    .balign 0x80
    b       exc_sync
    /* 5: IRQ */
    .balign 0x80
    b       exc_irq
    /* 6: FIQ */
    .balign 0x80
    b       exc_fiq
    /* 7: SError */
    .balign 0x80
    b       exc_serror

    /* 8-11: EL menor, AArch64 — não usado (não há EL0 no demo) */
    .balign 0x80
    b       exc_unexpected
    .balign 0x80
    b       exc_unexpected
    .balign 0x80
    b       exc_unexpected
    .balign 0x80
    b       exc_unexpected

    /* 12-15: EL menor, AArch32 — não usado */
    .balign 0x80
    b       exc_unexpected
    .balign 0x80
    b       exc_unexpected
    .balign 0x80
    b       exc_unexpected
    .balign 0x80
    b       exc_unexpected

/* ---------------------------------------------------------------
 * Trampolines fora da tabela (não cabem em 32 instruções por slot):
 * salvam um frame COMPLETO em SP_ELx e chamam exc_dispatch(frame,kind).
 *
 * Frame (304 bytes, offsets):
 *   [  0..247] x0..x30      (x_i em 8*i)
 *   [248] ELR_EL1   [256] SPSR_EL1
 *   [264] ESR_EL1   [272] FAR_EL1
 *   [280] SP original        (SP + 304 na entrada)
 * --------------------------------------------------------------- */

.section .text

/* caminho inesperado: troca para pilha dedicada e para */
exc_unexpected:
    msr     spsel, #1
    ldr     x0, =__exc_stack_top
    mov     sp, x0
    bl      exc_unexpected_c
1:  wfe
    b       1b

.macro FRAME_ENTER kind
    /* [FIX R9] O push original abria com "stp x29,x30,[sp,#-0x130]!" —
     * gravando x29@0/x30@8 — e depois "str x0,[sp,#0]" + "stp x1,x2,
     * [sp,#8]" SOBRESCREVIAM esses dois slots. O epílogo restaura
     * x29/x30 de [sp,#232]/[#240]... que NUNCA eram gravados: os R8
     * sobreviviam porque o próximo "bl" rescreve x30 antes de qualquer
     * "ret" e x29 não carregava estado vivo naqueles pontos exatos.
     * Com SVC a cada iteração (R9) isso morderia. Agora cada registrador
     * cai UMA vez no seu slot, como o struct exc_frame sempre definiu. */
    sub     sp, sp, #0x130
    stp     x29, x30, [sp, #232]
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

    mrs     x1, elr_el1
    str     x1, [sp, #248]
    mrs     x1, spsr_el1
    str     x1, [sp, #256]
    mrs     x1, esr_el1
    str     x1, [sp, #264]
    mrs     x1, far_el1
    str     x1, [sp, #272]
    add     x1, sp, #0x130
    str     x1, [sp, #280]

    mov     x1, #\kind
    mov     x0, sp
    bl      exc_dispatch

    /* handler pode ter mexido no frame — devolve ELR/SPSR ao hardware */
    ldr     x1, [sp, #248]
    msr     elr_el1, x1
    ldr     x1, [sp, #256]
    msr     spsr_el1, x1

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
    add     sp, sp, #0x130
    eret
.endm

exc_sync:    FRAME_ENTER 0
exc_irq:     FRAME_ENTER 1
exc_fiq:     FRAME_ENTER 2
exc_serror:  FRAME_ENTER 3
