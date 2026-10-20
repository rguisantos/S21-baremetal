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
    . = 0x80080000;
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

    /DISCARD/ : {
        *(.comment)
        *(.eh_frame*)
        *(.note*)
    }
}
