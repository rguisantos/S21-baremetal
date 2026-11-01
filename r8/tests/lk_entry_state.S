/* QEMU-only state fixture. The original Samsung entry/getter are separate. */
.text
.balign 4
.global lk_state_setup, lk_state_read, lk_state_done
lk_state_setup:
    mrs x11, sctlr_el1
    tbnz x11, #0, lk_state_done
    msr tcr_el1, x10
    isb
    mrs x12, tcr_el1
    br x9
lk_state_read:
    mrs x10, currentel
    mrs x11, sctlr_el1
    mrs x12, tcr_el1
    mrs x13, cpacr_el1
    mov x14, sp
lk_state_done:
    b lk_state_done
