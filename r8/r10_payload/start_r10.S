/* start_r10.S — experimental EL2 entry; not a validated Samsung boot image. */
.section .text.boot, "ax"
.global _start_r10
.type _start_r10, %function
_start_r10:
    /* Entry contract if supported by loader: x0 = FDT pointer.
     * Install our own stack before any stack access.
     */
    mov x19, x0
    msr spsel, #1
    ldr x1, =__el2_stack_top
    mov sp, x1

    /* Clear BSS while running on our private EL2 stack. */
    ldr x1, =__bss_start
    ldr x2, =__bss_end
0:  cmp x1, x2
    b.hs 1f
    str xzr, [x1], #8
    b 0b
1:
    /* Never enable stage-2 translation without VTTBR/VTTCR tables.
     * Do not trap all EL1 exceptions to EL2.
     */
    mrs x1, hcr_el2
    bic x1, x1, #(1 << 0)
    bic x1, x1, #(1 << 29)
    orr x1, x1, #(1 << 31)
    msr hcr_el2, x1
    isb

    mov x1, #3
    msr cnthctl_el2, x1
    msr cntvoff_el2, xzr
    isb

    ldr x1, =vbar_el2
    msr vbar_el2, x1
    isb

    /* The old code passed an arbitrary x0 to ELR_EL2. Load entry explicitly. */
    ldr x0, =r10_el1_entry
    ldr x1, =__el1_stack_top
    msr sp_el1, x1
    bl el2_to_el1_drop
1:  wfe
    b 1b

.section .vectors.el2, "ax"
.balign 0x800
.global vbar_el2
vbar_el2:
    .rept 16
    b el2_unexpected
    .balign 0x80
    .endr

.section .text, "ax"
el2_unexpected:
    msr daifset, #0xf
1:  wfe
    b 1b

.global el2_to_el1_drop
.type el2_to_el1_drop, %function
el2_to_el1_drop:
    /* EL1h, mask debug/SError/IRQ/FIQ. */
    mov x1, #0x3c5
    msr spsr_el2, x1
    msr elr_el2, x0
    eret

/* Stack storage is reserved only by linker_r10.ld. */
