/* linker_r10.ld — R10: Linker script for Exynos 2100 payload
 * Loads at 0x80080000 (typical kernel load address on Exynos)
 * Identity-mapped, no EL0, runs at EL1 after EL2 drop
 */

ENTRY(_start_r10)

PHDRS {
    text PT_LOAD FLAGS(5);   /* R_E */
    data PT_LOAD FLAGS(6);   /* RW */
    bss  PT_LOAD FLAGS(6);   /* RW */
}

SECTIONS
{
    . = 0x80080000;
    
    .text : {
        *(.text.boot)       /* _start_r10 first */
        *(.vectors.el2)     /* EL2 vector table */
        *(.text*)
        *(.rodata*)
        *(.vectors)         /* EL1 vector table from common */
    } :text
    
    . = ALIGN(4096);
    .data : {
        *(.data*)
        *(.got*)
    } :data
    
    . = ALIGN(4096);
    .bss : {
        *(.bss*)
        *(COMMON)
    } :bss
    
    . = ALIGN(16);
    __bss_start = .;
    __bss_end = .;
    
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
        . += 0x1000;                  /* exception stack */
        __exc_stack_top = .;
    }
    
    /* Discard */
    /DISCARD/ : {
        *(.comment)
        *(.eh_frame*)
        *(.note*)
    }
}