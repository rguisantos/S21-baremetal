/*
 * start.S — ponto de entrada comum (cada módulo define module_main,
 * el2_stage e el1_stage em C).
 *
 * Fluxo: _start (no EL de reset) -> zera .bss -> stack -> module_main(el)
 *        module_main desce de nível com drop_from_* -> trampolines ->
 *        el2_stage/el1_stage já com SP do nível certo.
 */

.section .text.boot

.global _start
_start:
    /* SP = SP_ELx do nível atual (convenção "h": stack por nível) */
    msr     spsel, #1

    /* zera .bss (page tables e buffers dependem disso) */
    ldr     x0, =__bss_start
    ldr     x1, =__bss_end
1:  cmp     x0, x1
    b.hs    2f
    stp     xzr, xzr, [x0], #16
    b       1b
2:
    /* liga o stack do nível atual */
    ldr     x0, =__stack_top
    mov     sp, x0

    /* entrega o EL de entrada ao C */
    bl      get_current_el
    mov     x19, x0
    mov     x0, x19
    bl      module_main
3:  wfe
    b       3b

/* ---------------------------------------------------------------
 * trampolines: alvo do ERET — cada um arruma o SP do seu nível
 * e chama a fase C correspondente.
 * --------------------------------------------------------------- */
.section .text

.global el2_trampoline
el2_trampoline:
    ldr     x0, =__stack_top
    mov     sp, x0
    bl      el2_stage
1:  wfe
    b       1b

.global el1_trampoline
el1_trampoline:
    ldr     x0, =__stack_top
    mov     sp, x0
    bl      el1_stage
1:  wfe
    b       1b
