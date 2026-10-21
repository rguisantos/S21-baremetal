/* QEMU-only hostile handoff. x16 selects SCTLR M/C bits, x17 is the Image.
 * GDB supplies L0/L1 tables at 0x40040000/0x40041000. Only QEMU RAM's
 * [0x40000000,0x80000000) is identity mapped, read-only, executable.
 * No stack, MMIO or stores. Never linked into the production Image.
 */
.text
.global entry_diag_state
entry_diag_state:
    mrs x14, CurrentEL
    cmp x14, #4
    b.eq el1
    tbz x16, #0, el2_enable
    mov x12, #0xff             // MAIR Attr0: normal WB
    msr mair_el2, x12
    ldr x12, =((1<<31)|(1<<23)|(2<<16)|(3<<12)|(1<<10)|(1<<8)|16)
    msr tcr_el2, x12           // RES1, 40-bit PA, 4K, 48-bit VA
    ldr x13, =0x40040000
    msr ttbr0_el2, x13
    dsb sy
    tlbi alle2
    dsb sy
    isb
el2_enable:
    mrs x15, sctlr_el2
    orr x15, x15, x16
    msr sctlr_el2, x15
    isb
    tbz x16, #0, enter
    at s1e2r, x17
    isb
    mrs x12, par_el1           // read translation must succeed
    at s1e2w, x17
    isb
    mrs x13, par_el1           // write translation must fail (RO)
    b enter
el1:
    tbz x16, #0, el1_enable
    mov x12, #0xff
    msr mair_el1, x12
    ldr x12, =((2<<32)|(1<<23)|(3<<12)|(1<<10)|(1<<8)|16)
    msr tcr_el1, x12           // IPS40, EPD1, 4K, 48-bit VA
    ldr x13, =0x40040000
    msr ttbr0_el1, x13
    dsb sy
    tlbi vmalle1
    dsb sy
    isb
el1_enable:
    mrs x15, sctlr_el1
    orr x15, x15, x16
    msr sctlr_el1, x15
    isb
    tbz x16, #0, enter
    at s1e1r, x17
    isb
    mrs x12, par_el1
    at s1e1w, x17
    isb
    mrs x13, par_el1
enter:
    br x17
.ltorg
