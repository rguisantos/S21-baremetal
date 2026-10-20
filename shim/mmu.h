#ifndef MMU_H
#define MMU_H

#include <stdint.h>

struct mmu_info {
	uintptr_t img_lo, img_hi;
	uintptr_t ttbr;
	int n_l3;
	uint64_t sctlr_before, sctlr_after;
};

int mmu_enable(struct mmu_info *info);
uint64_t mmu_probe(uintptr_t va);

extern volatile int mmu_enabled;

#endif