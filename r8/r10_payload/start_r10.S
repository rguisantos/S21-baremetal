/* start_r10.S — R10: EL2 entry point, drop to EL1 */

.section .text.boot
.global _start_r10
_start_r10:
    /* Entry at EL2 from BL2. x0=FDT pointer, x1=reserved, x2=reserved, x3=reserved */
    
    /* Save FDT pointer for later */
    str x0, [sp, #-16]!
    
    /* Set up EL2 stack */
    msr spsel, #1              // Use SP_EL2
    ldr x0, =__el2_stack_top
    mov sp, x0
    
    /* Configure HCR_EL2 for EL1 hosting */
    mrs x1, hcr_el2
    orr x1, x1, #(1 << 31)    // RW: EL1 is AArch64
    orr x1, x1, #(1 << 0)     // VM: enable stage 2 translation (not used yet)
    orr x1, x1, #(1 << 7)     // AMO: allow AArch32/64 mixing
    orr x1, x1, #(1 << 29)    // TGE: trap general exceptions
    msr hcr_el2, x1
    isb
    
    /* Configure CNTHCTL_EL2 for EL1 timer access */
    mov x1, #(1 << 0) | (1 << 1)  // EL1PCEN | EL1PCTEN
    msr cnthctl_el2, x1
    isb
    
    /* Set up VBAR_EL2 for exception handling */
    adr x1, vbar_el2
    msr vbar_el2, x1
    isb
    
    /* Drop to EL1 */
    bl el2_to_el1_drop
    
    /* Never returns */
    b .

/* EL2 vector table (minimal - just for unexpected exceptions) */
.section .vectors.el2, "ax"
.balign 0x800
.global vbar_el2
vbar_el2:
    /* Synchronous */
    .balign 0x80
    b el2_sync
    /* IRQ */
    .balign 0x80
    b el2_irq
    /* FIQ */
    .balign 0x80
    b el2_fiq
    /* SError */
    .balign 0x80
    b el2_serror
    /* Repeat for other 12 slots */
    .rept 12
    .balign 0x80
    b el2_unexpected
    .endr

/* EL2 exception handlers */
el2_sync:
el2_irq:
el2_fiq:
el2_serror:
el2_unexpected:
    /* Just park - we shouldn't get exceptions at EL2 */
    msr spsel, #1
    ldr x0, =__el2_stack_top
    mov sp, x0
1:  wfe
    b 1b

.section .text

/* Drop from EL2 to EL1 */
.global el2_to_el1_drop
el2_to_el1_drop:
    /* x0 = EL1 entry point (r10_el1_entry) */
    
    /* Set up SPSR_EL2 for EL1h entry */
    /* D=1, A=1, I=1, F=1 (mask all), M=5 (EL1h) */
    mov x1, #0x3C5
    msr spsr_el2, x1
    
    /* Set ELR_EL2 to EL1 entry */
    msr elr_el2, x0
    
    /* Set SP_EL1 */
    ldr x1, =__el1_stack_top
    msr sp_el1, x1
    
    /* Set TTBR0_EL1 (will be set up by mmu_init in EL1) */
    /* For now, identity map - we'll enable MMU in EL1 */
    
    /* ERET to EL1 */
    eret

/* EL1 stack */
.section .bss
.balign 16
.global __el2_stack_top
__el2_stack_bottom:
    .space 4096
__el2_stack_top:

.balign 16
.global __el1_stack_top
__el1_stack_bottom:
    .space 8192
__el1_stack_top: