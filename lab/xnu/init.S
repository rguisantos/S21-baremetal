/* Minimal static Darwin process 1 for the QEMU-only XNU experiment.
 * GNU assembler input; scripts/run_xnu_lab.py wraps .text in a Mach-O.
 * No libc, dyld, SDK or iOS programs. Darwin syscalls use x16 / svc #0x80.
 * This is user-space code, never a firmware entry point.
 */
.text
.p2align 2
.global _start
_start:
    sub sp, sp, #128
    adr x0, console
    mov x1, #2                  // O_RDWR
    mov x2, #0
    mov x16, #5                 // open
    svc #0x80
    b.cs silent_fail
    mov x19, x0

    mov x16, #20                // getpid
    svc #0x80
    b.cs identity_fail
    cmp x0, #1
    b.ne identity_fail
    mov x16, #24                // getuid
    svc #0x80
    b.cs identity_fail
    cbnz x0, identity_fail
    adr x1, identity_ok
    mov x2, #(identity_ok_end - identity_ok)
    bl write_exact

    adr x0, fixture_path
    mov x1, #0                  // O_RDONLY
    mov x2, #0
    mov x16, #5
    svc #0x80
    b.cs fixture_fail
    mov x20, x0
    add x1, sp, #64
    mov x2, #(fixture_end - fixture)
    mov x16, #3                 // read
    svc #0x80
    b.cs fixture_fail
    cmp x0, #(fixture_end - fixture)
    b.ne fixture_fail
    adr x3, fixture
    add x4, sp, #64
    mov x5, #(fixture_end - fixture)
1:
    ldrb w6, [x3], #1
    ldrb w7, [x4], #1
    cmp w6, w7
    b.ne fixture_fail
    subs x5, x5, #1
    b.ne 1b
    mov x0, x20
    add x1, sp, #64
    mov x2, #1
    mov x16, #3
    svc #0x80
    b.cs fixture_fail
    cbnz x0, fixture_fail       // exact contents, including EOF
    mov x0, x20
    mov x16, #6                 // close
    svc #0x80
    b.cs fixture_fail
    adr x1, fixture_ok
    mov x2, #(fixture_ok_end - fixture_ok)
    bl write_exact

    stp xzr, xzr, [sp]
    mov x0, sp
    mov x1, #0
    mov x2, #0                  // optional mach_absolute_time output
    mov x16, #116               // gettimeofday
    svc #0x80
    b.cs timer_fail
    // select(0, NULL, NULL, NULL, {0, 200000}, NULL)
    str xzr, [sp, #32]
    mov w9, #0x0d40
    movk w9, #3, lsl #16        // 200000 microseconds
    str w9, [sp, #40]
    str wzr, [sp, #44]
    mov x0, #0
    mov x1, #0
    mov x2, #0
    mov x3, #0
    add x4, sp, #32
    mov x5, #0
    mov x16, #93                // select
    svc #0x80
    b.cs timer_fail
    cbnz x0, timer_fail
    stp xzr, xzr, [sp, #16]
    add x0, sp, #16
    mov x1, #0
    mov x2, #0
    mov x16, #116
    svc #0x80
    b.cs timer_fail
    ldr x9, [sp]
    ldr x10, [sp, #16]
    sub x10, x10, x9
    mov x11, #0x4240
    movk x11, #0xf, lsl #16     // 1000000
    mul x10, x10, x11
    ldrsw x9, [sp, #8]
    ldrsw x12, [sp, #24]
    sub x12, x12, x9
    add x10, x10, x12
    mov x11, #0x86a0
    movk x11, #1, lsl #16       // minimum 100000 us
    cmp x10, x11
    b.lt timer_fail
    mov x11, #0x9680
    movk x11, #0x98, lsl #16    // maximum 10000000 us
    cmp x10, x11
    b.gt timer_fail
    adr x1, timer_ok
    mov x2, #(timer_ok_end - timer_ok)
    bl write_exact
    adr x1, all_ok
    mov x2, #(all_ok_end - all_ok)
    bl write_exact
    // Return through this research kernel's halt -> loader path, not exit(1).
    mov x0, #8                  // RB_HALT
    mov x16, #55                // reboot
    svc #0x80
    adr x1, halt_fail
    mov x2, #(halt_fail_end - halt_fail)
    b fail

write_exact:
    mov x0, x19
    mov x21, x2
    mov x16, #4                 // write
    svc #0x80
    b.cs silent_fail
    cmp x0, x21
    b.ne silent_fail
    ret

identity_fail:
    adr x1, bad_identity
    mov x2, #(bad_identity_end - bad_identity)
    b fail
fixture_fail:
    adr x1, bad_fixture
    mov x2, #(bad_fixture_end - bad_fixture)
    b fail
timer_fail:
    adr x1, bad_timer
    mov x2, #(bad_timer_end - bad_timer)
fail:
    bl write_exact
silent_fail:
    mov x0, #8
    mov x16, #55
    svc #0x80
2:
    b 2b

console: .asciz "/dev/console"
fixture_path: .asciz "/etc/s21-lab.txt"
fixture: .ascii "S21-XNU-LAB-FIXTURE-v1\n"
fixture_end:
identity_ok: .ascii "S21 XNU LAB: identity PASS pid=1 uid=0\n"
identity_ok_end:
fixture_ok: .ascii "S21 XNU LAB: APFS fixture PASS\n"
fixture_ok_end:
timer_ok: .ascii "S21 XNU LAB: timer PASS select=200ms elapsed=100ms..10s\n"
timer_ok_end:
all_ok: .ascii "S21 XNU LAB: ALL PASS; requesting RB_HALT\n"
all_ok_end:
bad_identity: .ascii "S21 XNU LAB: FAIL identity\n"
bad_identity_end:
bad_fixture: .ascii "S21 XNU LAB: FAIL APFS fixture\n"
bad_fixture_end:
bad_timer: .ascii "S21 XNU LAB: FAIL timer\n"
bad_timer_end:
halt_fail: .ascii "S21 XNU LAB: FAIL RB_HALT returned\n"
halt_fail_end:
