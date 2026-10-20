/* QEMU-only synthetic loader; product entry and dispatcher are unchanged. */
.section .text.boot
.global r10_test_boot
r10_test_boot:
    ldr x1, =r10_test_bss
    mov x2, #0xdead
    str x2, [x1]
    /* Loader-owned FDT copy outside the payload, within QEMU RAM. */
    ldr x1, =r10_test_fdt
    ldr x2, =r10_test_fdt_end
    ldr x0, =0x47000000
    mov x3, x0
1:  ldrb w4, [x1], #1
    strb w4, [x3], #1
    cmp x1, x2
    b.lo 1b
    b _start_r10
.section .rodata
.balign 8
.global r10_test_fdt
r10_test_fdt:
    .incbin R10_TEST_DTB
r10_test_fdt_end:
