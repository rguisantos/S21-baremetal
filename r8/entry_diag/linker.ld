ENTRY(diag_image)
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
    . = 0x40080000;
    .text : { KEEP(*(.text.boot)) *(.text*) } :text
    .data : { *(.data*) } :data
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
ASSERT(diag_record % 64 == 0, "record alignment")
ASSERT(diag_end - diag_image < 0x100000, "ADR reach")
