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
    __payload_start = .;
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

    /* Every stack belongs to the data PT_LOAD memory extent. A loader must
     * reserve p_memsz, not just p_filesz, before entering the payload. */
    .stacks ALIGN(4096) (NOLOAD) : {
        __el2_stack_bottom = .; . += 4096; __el2_stack_top = .;
        __el1_stack_bottom = .; . += 8192; __el1_stack_top = .;
        . += 4096; __exc_stack_top = .;
        __sec_el2_stacks = .; . += 8 * 4096;
        __sec_cpu_stacks = .; . += 8 * 16384;
        __sec_exc_stacks = .; . += 8 * 4096;
        __payload_end = .;
    } :data

    /DISCARD/ : {
        *(.comment)
        *(.eh_frame*)
        *(.note*)
    }
}
