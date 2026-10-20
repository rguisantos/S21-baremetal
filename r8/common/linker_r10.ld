/* R10 experimental payload linker script.
 * Load address is a hypothesis for a future controlled loader, not a verified
 * Samsung boot/chainload contract.
 */
ENTRY(_start_r10)
PHDRS {
    text PT_LOAD FLAGS(5);
    data PT_LOAD FLAGS(6);
}
SECTIONS {
    . = DEFINED(R10_LOAD_ADDR) ? R10_LOAD_ADDR : 0x80080000;
    .text : {
        *(.text.boot)
        *(.vectors.el2)
        *(.text*)
        *(.rodata*)
        *(.vectors)
    } :text

    . = ALIGN(4096);
    .data : {
        *(.data*)
        *(.got*)
    } :data

    . = ALIGN(4096);
    .bss (NOLOAD) : {
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(16);
        __bss_end = .;
    } :data

    . = ALIGN(4096);
    __el2_stack_bottom = .;
    . += 4096;
    __el2_stack_top = .;

    . = ALIGN(16);
    __el1_stack_bottom = .;
    . += 8192;
    __el1_stack_top = .;

    . = ALIGN(16);
    .exc_stack (NOLOAD) : {
        . += 0x1000;
        __exc_stack_top = .;
    } :data

    /* Private EL2 entry stacks: 8 CPUs * 4 KiB. */
    . = ALIGN(4096);
    __sec_el2_stacks = .;
    . += 8 * 4096;

    /* Secondary CPU stacks (CPUs 1-7) */
    . = ALIGN(4096);
    __sec_cpu_stacks = .;
    . += 8 * 16384;  /* 8 CPUs * 16KB = 128KB */

    . = ALIGN(4096);
    __sec_exc_stacks = .;
    . += 8 * 4096;   /* 8 CPUs * 4KB = 32KB */

    /DISCARD/ : {
        *(.comment)
        *(.eh_frame*)
        *(.note*)
    }
}
