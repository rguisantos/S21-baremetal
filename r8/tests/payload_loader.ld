/* Synthetic QEMU firmware only; reserve every loader byte including its stack. */
OUTPUT_ARCH(aarch64)
ENTRY(loader_start)
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
    . = 0x44000000;
    __loader_start = .;
    .text : { *(.text.boot) *(.text*) *(.rodata*) } :text
    . = ALIGN(4096);
    .data : { *(.data*) *(.got*) } :data
    .bss ALIGN(4096) (NOLOAD) : {
        __bss_start = .; *(.bss*) *(COMMON) . = ALIGN(16); __bss_end = .;
    } :data
    .stack ALIGN(4096) (NOLOAD) : { . += 16384; __loader_stack_top = .; __loader_end = .; } :data
    /DISCARD/ : { *(.comment) *(.eh_frame*) *(.note*) }
}
