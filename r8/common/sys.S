/*
 * sys.S — helpers de system registers compartilhados pelos módulos R8
 */

.section .text

/* ---------------------------------------------------------------
 * get_pc — endereço da própria instrução (útil p/ provar VA de exec.)
 * --------------------------------------------------------------- */
.global get_pc
get_pc:
    adr     x0, get_pc
    ret

/* ---------------------------------------------------------------
 * drop_from_el3_to_el2 — x0 = PC alvo
 * O ritual do ERET "sintetizado": montar SPSR/ELR e retornar
 * para um exception level MENOR (não existe "call" descendente).
 * SPSR_EL3 = 0x3C9  ->  EL2h (SP_EL2) + DAIF mascarados
 *
 * SCR_EL3 gravado antes do ERET (numeração da DDI0487 — o próprio
 * QEMU define SCR_RW=1<<10, SCR_NS=1<<0, SCR_EEL2=1<<18 em cpu.h,
 * e o TF-A grava os mesmos bits):
 *   RES1 (bits 4,5) ->  "reserved, should be one" (TF-A: SCR_RES1_BITS).
 *                      É por isso que o reset do QEMU mostra 0x30.
 *   RW   (bit 10)   ->  inferiores em AArch64. Sem ele, o SPSR pede
 *                      AArch64 e o retorno é ILEGAL (PSTATE.IL=1).
 *   NS   (bit  0)   ->  alvo no mundo NÃO-SEGURO, onde vive um OS.
 *   EEL2 (bit 18)   ->  liga o EL2 no estado SEGURO (FEAT_SEL2). P/ o
 *                      EL2 não-seguro não é exigido (QEMU: arm_is_
 *                      el2_enabled_secstate), mas EL3 tutela o EL2 —
 *                      firmware real grava 1 do mesmo jeito.
 * --------------------------------------------------------------- */
.global drop_from_el3_to_el2
drop_from_el3_to_el2:
    mrs     x1, scr_el3
    orr     x1, x1, #0x30               /* RES1 (bits 4,5) — sempre 1 */
    orr     x1, x1, #(1 << 10)          /* RW  (bit 10): AArch64 embaixo */
    orr     x1, x1, #(1 << 0)           /* NS  (bit 0):  nao-seguro */
    orr     x1, x1, #(1 << 18)          /* EEL2 (bit 18): EL2 sob tutela do EL3 */
    msr     scr_el3, x1
    mov     x1, #0x3c9
    msr     spsr_el3, x1
    msr     elr_el3, x0
    isb
    eret

/* ---------------------------------------------------------------
 * drop_from_el2_to_el1 — x0 = PC alvo
 * SPSR_EL2 = 0x3C5  ->  EL1h (SP_EL1) + DAIF mascarados
 * HCR_EL2.RW = 1 (bit 31!) -> EL1 opera em AArch64.
 *   Sem isto, o ERET p/ EL1h é um retorno ILEGAL (EC=0x0E): o PSTATE
 *   pede AArch64, mas o hypervisor diz que o EL1 fala AArch32.
 *   O retorno ilegal entrega PC mas seta PSTATE.IL=1: a primeira
 *   instrução no alvo trapa de volta no EL2 — hang silencioso.
 *   (não confundir com SCR_EL3.RW, que é o bit 10)
 * --------------------------------------------------------------- */
.global drop_from_el2_to_el1
drop_from_el2_to_el1:
    mrs     x1, hcr_el2
    orr     x1, x1, #0x80000000         /* RW (bit 31): EL1 em AArch64 */
    msr     hcr_el2, x1
    mov     x1, #0x3c5
    msr     spsr_el2, x1
    msr     elr_el2, x0
    isb
    eret
