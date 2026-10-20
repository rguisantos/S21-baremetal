/* start_r10.S — R10 experimental EL2 entry and secondary bring-up.
 *
 * Assumptions requiring platform validation:
 * - firmware enters this payload at EL2 on every CPU;
 * - Aff0 is the logical CPU index 0..7;
 * - PSCI CPU_ON targets the matching MPIDR;
 * - the linker symbols below are identity-addressable before MMU setup.
 */
.section .text.boot, "ax"
.global _start_r10
.type _start_r10, %function
_start_r10:
    msr daifset, #0xf
    mov x19, x0                  /* preserve entry argument */
    mrs x20, mpidr_el1
    and x20, x20, #0xff          /* Aff0: platform-specific CPU index */

    cbnz x20, secondary_entry

    /* Primary CPU only: private EL2 stack and BSS initialization. */
    msr spsel, #1
    ldr x1, =__el2_stack_top
    mov sp, x1

    ldr x1, =__bss_start
    ldr x2, =__bss_end
0:  cmp x1, x2
    b.hs 1f
    str xzr, [x1], #8
    b 0b
1:
    bl configure_el2
    ldr x0, =r10_el1_entry
    ldr x1, =__el1_stack_top
    msr sp_el1, x1
    b el2_to_el1_drop

secondary_entry:
    /* Never clear shared BSS on a secondary. Use a private EL2 stack. */
    msr spsel, #1
    ldr x1, =__sec_el2_stacks
    mov x2, #4096
    madd x1, x20, x2, x1
    add x1, x1, x2
    mov sp, x1

    bl configure_el2

    /* Dedicated EL1 stack: __sec_cpu_stacks[cpu], 16 KiB per CPU. */
    ldr x1, =__sec_cpu_stacks
    mov x2, #16384
    madd x1, x20, x2, x1
    add x1, x1, x2
    msr sp_el1, x1

    ldr x0, =secondary_cpu_entry
    mov x1, #0x3c5              /* EL1h; mask D/A/I/F */
    msr spsr_el2, x1
    msr elr_el2, x0
    eret

/* Configure only architectural EL2 state; platform boot contract still
 * needs confirmation before hardware execution. */
.type configure_el2, %function
configure_el2:
    mrs x1, hcr_el2
    bic x1, x1, #(1 << 0)       /* VM = 0 */
    bic x1, x1, #(1 << 29)      /* TGE = 0 */
    orr x1, x1, #(1 << 31)      /* RW = 1: EL1 AArch64 */
    msr hcr_el2, x1
    mov x1, #3
    msr cnthctl_el2, x1
    msr cntvoff_el2, xzr
    ldr x1, =vbar_el2
    msr vbar_el2, x1
    isb
    ret

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
2:  wfe
    b 2b

.global el2_to_el1_drop
.type el2_to_el1_drop, %function
el2_to_el1_drop:
    mov x1, #0x3c5
    msr spsr_el2, x1
    msr elr_el2, x0
    eret
/* Stack storage is reserved only by linker_r10.ld. */
