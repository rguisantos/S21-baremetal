/* QEMU-only synthetic loader; product entry and dispatcher are unchanged. */
.section .text.boot
.global r10_test_boot
r10_test_boot:
    ldr x1, =r10_test_bss
    mov x2, #0xdead
    str x2, [x1]
    ldr x0, =r10_test_fdt
    b _start_r10
.section .rodata
.balign 8
.global r10_test_fdt
r10_test_fdt:
    .quad 0x1122334455667788
