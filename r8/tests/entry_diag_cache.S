/* QEMU-only hostile handoff fixture. MMU stays off; set SCTLR.C at the
 * current EL using real MSR instructions, then branch to x17. No stack,
 * peripheral access or writes to the diagnostic Image/record.
 */
.text
.global entry_diag_cache
entry_diag_cache:
    mrs x14, CurrentEL
    cmp x14, #4
    b.eq 1f
    mrs x15, sctlr_el2
    orr x15, x15, #4
    msr sctlr_el2, x15
    isb
    br x17
1:  mrs x15, sctlr_el1
    orr x15, x15, #4
    msr sctlr_el1, x15
    isb
    br x17
