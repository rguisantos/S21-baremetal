ENTRY(_entry)
SECTIONS
{
	. = 0;
	.text : { *(.text.entry) *(.text*) }
	.rodata : { *(.rodata*) }
	.data : { *(.data*) }
	.bss : { *(.bss*) *(COMMON) }
	. = ALIGN(16);
	. += 0x2000;
	_stack_top = .;
	/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
