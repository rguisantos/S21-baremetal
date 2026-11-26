/*
 * Reproduz o salto final modelado do LK HZC2 (docs/lk-cache-handoff.md):
 * x0 = FDT, x1..x3 = 0, BR para a Image em EL1. O harness grava os dois
 * endereços nos offsets 0x8 (Image) e 0x10 (FDT).
 */
	.globl _start
_start:
	b	1f
	.balign 8
image_pa:	.quad 0
fdt_pa:		.quad 0
1:	ldr	x4, image_pa
	ldr	x0, fdt_pa
	mov	x1, xzr
	mov	x2, xzr
	mov	x3, xzr
	br	x4
