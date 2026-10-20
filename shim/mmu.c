/*
 * S21 Ultra Exynos 2100 MMU - 4K granule, identity map
 *
 * 48-bit VA, T0SZ=16 (48-bit), 4K pages, 2MB blocks at L1.
 * Identity map 0..4GB: L0->L1->2MB blocks.
 */
#include <stdint.h>
#include "mmu.h"
#include "asm.h"

#define PG_SHIFT	12
#define PG_SIZE		(1UL << PG_SHIFT)		/* 4K */
#define BLK_SHIFT	21
#define BLK_SIZE	(1UL << BLK_SHIFT)		/* 2MB level-1 block */
#define NENT		512

#define ATTR_DEV	0	/* MAIR attr0 = 0x00 Device-nGnRnE */
#define ATTR_NC		1	/* MAIR attr1 = 0x44 Normal non-cacheable */
#define ATTR_WB		2	/* MAIR attr2 = 0xff Normal WB RW-alloc */
#define MAIR_VAL	0xff4400UL	/* attr0=0x00, attr1=0x44, attr2=0xff */

#define D_BLOCK		1UL
#define D_TABLE		3UL
#define D_PAGE		3UL
#define D_ATTR(i)	((uint64_t)(i) << 2)
#define D_SH_OUTER	(2UL << 8)
#define D_SH_INNER	(3UL << 8)
#define D_AF		(1UL << 10)
#define D_PXN		(1UL << 53)
#define D_UXN		(1UL << 54)

#define DEV_FLAGS	(D_ATTR(ATTR_DEV) | D_AF | D_PXN | D_UXN)
#define WB_FLAGS	(D_ATTR(ATTR_WB) | D_AF | D_UXN)
#define NC_FLAGS	(D_ATTR(ATTR_NC) | D_SH_OUTER | D_AF | D_UXN)

#define TCR_VAL		(16UL | (1UL<<8)|(1UL<<10)|(3UL<<12)|(0UL<<14)| \
			 (16UL<<16)|(1UL<<24)|(3UL<<28)|(0UL<<30) | \
			 (1UL<<23)|(1UL<<32))

#define SCTLR_M		(1UL << 0)
#define SCTLR_C		(1UL << 2)
#define SCTLR_I		(1UL << 12)
#define SCTLR_A		(1UL << 1)
#define SCTLR_WXN	(1UL << 19)

extern char _head[], _end[];

static uint64_t l2_pool[512] __attribute__((aligned(4096)));
static uint64_t l3_pool[2][512] __attribute__((aligned(4096)));

int mmu_enable(struct mmu_info *info)
{
	uintptr_t img_lo = (uintptr_t)_head & ~(4095);
	uintptr_t img_hi = ((uintptr_t)_end + 4095) & ~4095;
	
	info->img_lo = img_lo;
	info->img_hi = img_hi;
	info->ttbr = (uintptr_t)l2_pool;
	info->n_l3 = 0;
	
	/* L1 table (we use as L2 for 4K granule) */
	uint64_t *l1 = (uint64_t *)l2_pool;
	for (int i = 0; i < 512; i++) l1[i] = 0;
	
	/* Identity map 0..4GB with 2MB blocks */
	for (uint64_t i = 0; i < (4UL << 30) >> 21; i++) {
		l1[i] = (i << 21) | 0x1 | 2;	/* block, AF=1, inner shareable */
	}
	
	/* Mark framebuffer as non-cacheable */
	/* FB at 0x8f000000 - will be updated from DTB */
	
	/* MAIR */
	wsr("mair_el1", 0x0044ff00UL);	/* attr0=dev, attr1=nc, attr2=wb */
	
	/* TCR: 48-bit VA, 4K pages, T0SZ=16 */
	wsr("tcr_el1", (16UL) | (1UL<<8)|(1UL<<10)|(3UL<<12)|(0UL<<14) |
			  (16UL<<16)|(1UL<<24)|(3UL<<28)|(0UL<<30) |
			  (1UL<<23)|(1UL<<32));
	
	wsr("ttbr0_el1", (uint64_t)l2_pool);
	__asm__ volatile("isb; tlbi vmalle1; dsb nsh; isb" ::: "memory");
	
	uint64_t sctlr = rsr("sctlr_el1");
	sctlr &= ~(1UL<<1) | (1UL<<19);	/* A=0, WXN=0 */
	sctlr |= (1UL<<0) | (1UL<<2) | (1UL<<12);	/* M=1, C=1, I=1 */
	wsr("sctlr_el1", sctlr);
	isb();
	
	return 0;
}

uint64_t mmu_probe(uintptr_t va)
{
	__asm__ volatile("at s1e1r, %0; isb" : : "r"(va) : "memory");
	return rsr("par_el1");
}