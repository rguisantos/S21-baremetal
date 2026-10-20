/* start_r10.S — R10: EL2 entry, EL2→EL1 drop, secondary CPU boot */

.section .text.boot, "ax"
.global _start_r10
.type _start_r10, %function
_start_r10:
    /* Entry contract:
     * Primary CPU (CPU 0): x0 = FDT pointer
     * Secondary CPUs (1-7): x0 = MPIDR (from PSCI CPU_ON context)
     * x19 = saved FDT/MPIDR
     */
    mov x19, x0
    
    /* Install our own stack before any stack access */
    msr spsel, #1
    ldr x1, =__el2_stack_top
    mov sp, x1
    
    /* Determine if primary or secondary CPU:
     * Primary (CPU 0): MPIDR Aff0 = 0, x0 = FDT pointer (not a valid CPU MPIDR)
     * Secondary: MPIDR Aff0 = 1-7, x0 = MPIDR passed by PSCI CPU_ON
     * We check MPIDR directly rather than x0 value.
     */
    mrs x0, mpidr_el1
    and x0, x0, #0xFF          /* Aff0 = CPU index */
    cmp x0, #0
    b.ne secondary_entry
    
    /* ==================== PRIMARY CPU PATH ==================== */
    /* Clear BSS while running on our private EL2 stack */
    ldr x1, =__bss_start
    ldr x2, =__bss_end
0:  cmp x1, x2
    b.hs 1f
    str xzr, [x1], #8
    b 0b
1:
    
    /* HCR_EL2 configuration */
    mrs x1, hcr_el2
    bic x1, x1, #(1 << 0)      /* VM = 0: no stage-2 translation */
    bic x1, x1, #(1 << 29)     /* TGE = 0: don't trap EL1 exceptions */
    orr x1, x1, #(1 << 31)     /* RW = 1: EL1 is AArch64 */
    msr hcr_el2, x1
    isb
    
    /* Timer access for EL1 */
    mov x1, #3                 /* EL1PCTEN | EL1PCEN */
    msr cnthctl_el2, x1
    msr cntvoff_el2, xzr
    isb
    
    /* EL2 vector table */
    ldr x1, =vbar_el2
    msr vbar_el2, x1
    isb
    
    /* Drop to EL1 */
    ldr x0, =r10_el1_entry
    ldr x1, =__el1_stack_top
    msr sp_el1, x1
    bl el2_to_el1_drop
    
    /* Should never return */
1:  wfe
    b 1b

    /* ==================== SECONDARY CPU PATH ==================== */
secondary_entry:
    /* x19 = MPIDR (saved from entry x0) */
    mov x0, x19
    
    /* Set up EL2 stack for this CPU */
    msr spsel, #1
    ldr x1, =__el2_stack_top
    mov sp, x1
    
    /* Clear BSS - ONLY primary should do this! 
     * Secondaries must NOT clear BSS as it's shared.
     * Skip BSS clear for secondaries.
     */
    
    /* HCR_EL2 configuration (same as primary) */
    mrs x1, hcr_el2
    bic x1, x1, #(1 << 0)      /* VM = 0 */
    bic x1, x1, #(1 << 29)     /* TGE = 0 */
    orr x1, x1, #(1 << 31)     /* RW = 1 */
    msr hcr_el2, x1
    isb
    
    /* Timer access for EL1 */
    mov x1, #3
    msr cnthctl_el2, x1
    msr cntvoff_el2, xzr
    isb
    
    /* EL2 vector table */
    ldr x1, =vbar_el2
    msr vbar_el2, x1
    isb
    
    /* Drop to EL1 at secondary_cpu_entry */
    ldr x0, =secondary_cpu_entry
    /* SP_EL1 and exception stack will be set by percpu_init_cpu 
     * before PSCI CPU_ON, via msr sp_el1 in primary.
     * For secondary, we need to set them here before ERET.
     * The primary has already written them to percpu_data_array[cpu].
     * We read them back using our MPIDR.
     */
    adrp x1, percpu_data_array
    add x1, x1, :lo12:percpu_data_array
    ldr x2, [x1, #8]           /* mpidr of this CPU (saved by primary) */
    /* Find our index in the array by matching MPIDR */
    /* Simpler: primary wrote sp_el1 to percpu_data_array[cpu].sp_el1
     * where cpu = Aff0. We can compute offset.
     */
    mov x2, #0
    mov x3, #8
    mul x2, x0, x3             /* x2 = Aff0 * 8 (offset to mpidr field) */
    add x2, x1, x2
    ldr x2, [x2]               /* x2 = our mpidr (for verification) */
    
    /* Calculate offset to our percpu_data: sizeof(percpu_data) * Aff0 */
    /* percpu_data is 64-byte aligned, so each entry is multiple of 64 */
    mov x3, #64
    mul x2, x0, x3             /* x2 = Aff0 * 64 */
    add x1, x1, x2             /* x1 = &percpu_data_array[Aff0] */
    
    /* Read sp_el1 (offset 40 in percpu_data) */
    ldr x1, [x1, #40]
    msr sp_el1, x1
    
    /* Read exc_stack_top (offset 48) */
    ldr x1, [x1, #48]
    /* We don't use exc_stack_top directly here; it's for exception entry */
    
    /* Drop to EL1 at secondary_cpu_entry */
    ldr x0, =secondary_cpu_entry
    mov x1, #0x3c5             /* SPSR_EL2: EL1h, DAIF=1111 */
    msr spsr_el2, x1
    msr elr_el2, x0
    eret

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
