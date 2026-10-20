/*
 * S21 Ultra Exynos 2100 boot shim linker script
 *
 * Entry at _start in .text.head
 * Load address: 0x80080000 (typical kernel load address on Exynos)
 * Runs at EL2 from BL2, drops to EL1
 */
ENTRY(_start)

PHDRS {
    text PT_LOAD FLAGS(5);
    data PT_LOAD FLAGS(6);
    bss  PT_LOAD FLAGS(6);
}

SECTIONS
{
    . = 0x80080000;
    
    .text.head : {
        *(.text.head)
    } :text
    
    .text : {
        *(.text*)
        *(.rodata*)
    } :text
    
    . = ALIGN(4096);
    .data : {
        *(.data*)
        *(.got*)
    } :data
    
    . = ALIGN(4096);
    .bss (NOLOAD) : {
        _bss_start = .;
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(16);
        _bss_end = .;
        __bss_end = .;
    } :bss
    
    _end = .;
    
    /* Stacks */
    . = ALIGN(4096);
    _stack_bottom = .;
    . += 4096;
    _stack_top = .;
    
    . = ALIGN(4096);
    _sec_stacks = .;
    . += 8 * 4096;  /* 8 CPUs * 4KB each */
    
    /* Exception vectors */
    . = ALIGN(0x800);
    vectors = .;
    . += 16 * 0x80;  /* 16 slots * 128 bytes */
    
    /* Discard */
    /DISCARD/ : {
        *(.comment)
        *(.eh_frame*)
        *(.note*)
    }
}