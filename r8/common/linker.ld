/* linker.ld — script comum dos módulos R8 (QEMU virt: RAM em 0x40000000) */

OUTPUT_ARCH(aarch64)
ENTRY(_start)

SECTIONS
{
    . = 0x40080000;

    .text : {
        KEEP(*(.text.boot))
        *(.text .text.*)
    }

    .rodata : {
        *(.rodata .rodata.*)
    }

    . = ALIGN(0x800);
    .vectors : {
        KEEP(*(.vectors))
    }

    .data : {
        *(.data .data.*)
    }

    . = ALIGN(16);
    .bss (NOLOAD) : {
        __bss_start = .;
        *(.bss .bss.* COMMON)
        . = ALIGN(16);
        __bss_end = .;
    }

    . = ALIGN(16);
    .stack (NOLOAD) : {
        . += 0x8000;                  /* 32 KB de pilha            */
        __stack_top = .;
    }

    .exc_stack (NOLOAD) : {
        . += 0x1000;                  /* pilha de exceção (slot SP_EL0) */
        __exc_stack_top = .;
    }

    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
