/*
 * Kernel falso para o teste de handoff: recebe x0 = boot_args (físico),
 * MMU desligada, e imprime os campos na PL011 do QEMU virt.
 * Posição independente; ligado em 0.
 */
	.section .text.entry, "ax"
	.globl _entry
_entry:
	adr	x1, _stack_top
	mov	sp, x1
	bl	fake_main
1:	wfe
	b	1b
