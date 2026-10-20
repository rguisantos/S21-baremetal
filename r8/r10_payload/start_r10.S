/* start_r10.S — R10 experimental EL2 entry and secondary bring-up.
 *
 * Assumptions requiring platform validation:
 * - a controlled loader enters the primary at EL2 with MMU/D-cache off;
 * - the dormant secondary path still assumes Aff0 is a logical index;
 * - PSCI/topology are not enabled by the single-CPU main;
 * - the linker symbols below are identity-addressable before MMU setup.
 */
.section .text.boot, "ax"
.global _start_r10
.type _start_r10, %function
_start_r10:
    msr daifset, #0xf
    /* Loader contract: EL2, identity addressing, EL2 and EL1 MMU/D-cache
     * off. Reject incompatible state before any BSS/stack memory writes.
     * Loader still owns cleaning the image to PoC and I-cache coherency. */
    mrs x1, CurrentEL
    cmp x1, #8
    b.ne el2_unexpected
    mrs x1, sctlr_el2
    tst x1, #1
    b.ne el2_unexpected
    tst x1, #4
    b.ne el2_unexpected
    mrs x1, sctlr_el1
    tst x1, #1
    b.ne el2_unexpected
    tst x1, #4
    b.ne el2_unexpected
    mov x19, x0                  /* physical FDT from the loader */

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

.global _secondary_start_r10
_secondary_start_r10:
    /* Dormant SMP path. CPU_ON must use this distinct entry, never the
     * primary BSS-clearing entry. Aff0 topology remains unvalidated. */
    msr daifset, #0xf
    mrs x1, CurrentEL
    cmp x1, #8
    b.ne el2_unexpected
    mrs x20, mpidr_el1
    and x20, x20, #0xff
    cmp x20, #8
    b.hs el2_unexpected
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
    bic x1, x1, #(1 << 3)       /* FMO = 0: do not route FIQ to EL2 */
    bic x1, x1, #(1 << 4)       /* IMO = 0: IRQ handler lives at EL1 */
    bic x1, x1, #(1 << 5)       /* AMO = 0: abort handler lives at EL1 */
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
    mov x0, x19                  /* hand FDT to r10_el1_entry(void *) */
    eret
/* Stack storage is reserved only by linker_r10.ld. */
