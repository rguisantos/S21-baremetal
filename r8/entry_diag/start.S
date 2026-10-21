/* Single-CPU entry probe. No stack, FDT dereference, MMIO or EL transition.
 * Caller owns the complete Image and supplies coherent executable bytes.
 * Refuse memory writes if current EL is unsupported or SCTLR.M/C is set.
 */
.section .text.boot,"ax"
.global diag_image, diag_entry, diag_done, diag_refused
.balign 8
diag_image:
    b diag_entry
    nop
    .quad 0x80000
    .quad diag_end - diag_image
    .quad 8                     // LE, page size unspecified, placement bit
    .quad 0, 0, 0
    .word 0x644d5241
    .word 0                     // no EFI stub

diag_entry:
    mrs x4, CurrentEL
    mrs x5, daif
    msr daifset, #15
    cmp x4, #4
    b.eq 1f
    cmp x4, #8
    b.ne diag_refused
    mrs x6, sctlr_el2
    b 2f
1:  mrs x6, sctlr_el1
2:  tbnz x6, #0, diag_refused
    tbnz x6, #2, diag_refused
    mrs x7, mpidr_el1
    mrs x8, spsel
    mov x9, sp
    adr x10, diag_image
    adr x11, diag_record
    str xzr, [x11]             // commit marker written last
    stp x0, x1, [x11, #16]
    stp x2, x3, [x11, #32]
    stp x4, x5, [x11, #48]
    stp x6, x7, [x11, #64]
    stp x8, x9, [x11, #80]
    stp x10, x11, [x11, #96]
    stp xzr, xzr, [x11, #112]
    mov x12, #1
    str w12, [x11, #8]
    mov x12, #128
    str w12, [x11, #12]
    dsb sy
    movz x12, #0x3253
    movk x12, #0x4531, lsl #16
    movk x12, #0x544e, lsl #32
    movk x12, #0x5952, lsl #48 // LE bytes "S21ENTRY", versioned marker
    str x12, [x11]
    dsb sy
diag_done:
    wfe
    b diag_done
diag_refused:
    wfe
    b diag_refused
.section .data,"aw"
.balign 64
.global diag_record, diag_end
diag_record:
    .zero 128
diag_end:
