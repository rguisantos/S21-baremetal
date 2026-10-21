/* QEMU virt EL2 firmware stub; never part of the Samsung shim. */
.section .text.boot,"ax"
.global loader_start
loader_start:
    msr daifset, #0xf
    mrs x1, CurrentEL
    cmp x1, #8
    b.ne loader_park
    mrs x1, sctlr_el2
    mov x2, #5
    tst x1, x2
    b.ne loader_park
    mrs x1, sctlr_el1
    mov x2, #5
    tst x1, x2
    b.ne loader_park
    msr spsel, #1
    ldr x1, =__loader_stack_top
    mov sp, x1
    ldr x1, =__bss_start
    ldr x2, =__bss_end
1:  cmp x1, x2
    b.hs 2f
    str xzr, [x1], #8
    b 1b
2:  ldr x1, =loader_vectors
    msr vbar_el2, x1
    isb
    bl loader_main
loader_park:
    wfe
    b loader_park
.balign 0x800
loader_vectors:
    .rept 16
    b loader_fault
    .balign 0x80
    .endr
loader_fault:
    ldr x1, =loader_status
    mov w2, #-99
    str w2, [x1]
    b loader_park
.global loader_enter
.type loader_enter,%function
loader_enter:
    /* GDB stops here to check the complete image before any R10 writes. */
    mov x16, x0
    mov x0, x1
    mov x1, xzr
    mov x2, xzr
    mov x3, xzr
    br x16
.section .rodata,"a"
.balign 8
.global loader_firmware, loader_firmware_end
loader_firmware:
.incbin R10_LOADER_DTB
loader_firmware_end:
.balign 8
.global loader_payload, loader_payload_end
loader_payload:
.incbin R10_LOADER_PAYLOAD
loader_payload_end:
