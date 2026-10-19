/* mmu.c — R10: MMU initialization with identity mapping */

#include "r10.h"

/* Page tables (4KB aligned, 16KB total for L0+L1) */
__attribute__((aligned(4096)))
static u64 l0_table[512];   // L0: 512 entries, covers 48-bit VA

__attribute__((aligned(4096)))
static u64 l1_table[512];   // L1: 512 entries, each 2MB block

void mmu_init(void)
{
    /* Clear page tables */
    for (int i = 0; i < 512; i++) {
        l0_table[i] = 0;
        l1_table[i] = 0;
    }
    
    /* Identity map 0x0000_0000_0000_0000 - 0x0000_FFFF_FFFF_FFFF (256 TB)
     * using 2MB blocks at L1 level
     * L0 index 0 covers 0x0000_0000_0000_0000 - 0x0000_00FF_FFFF_FFFF (512 GB)
     * We'll map first 4 GB (DRAM + peripherals) with 2MB blocks
     */
    
    /* L0[0] -> L1 table */
    l0_table[0] = (u64)l1_table | 0x3;  // Valid, Table descriptor
    
    /* Map 0x0000_0000 - 0xFFFF_FFFF (4 GB) with 2MB blocks */
    for (int i = 0; i < 2048; i++) {  // 4GB / 2MB = 2048 blocks
        u64 pa = (u64)i * BLOCK_SIZE;
        u64 attr = MAIR_NORMAL_WB;  // AttrIdx=2 (WB)
        
        if (pa >= 0x10000000 && pa < 0x20000000) {
            /* Peripheral region (0x1000_0000 - 0x1FFF_FFFF) - Device memory */
            attr = MAIR_DEVICE_nGnRnE;  // AttrIdx=0
        }
        
        l1_table[i] = pa | attr << 2 | 0x1;  // Block descriptor, AF=1, SH=Inner
    }
    
    /* Configure MAIR_EL1 */
    u64 mair = (MAIR_DEVICE_nGnRnE << 0) |
               (MAIR_NORMAL_NC << 8) |
               (MAIR_NORMAL_WB << 16);
    MSR(mair_el1, mair);
    
    /* Configure TCR_EL1 */
    u64 tcr = TCR_EL1_T0SZ(48) | TCR_EL1_T1SZ(48) |
              TCR_EL1_IRGN0_WB | TCR_EL1_ORGN0_WB | TCR_EL1_SH0_INNER |
              TCR_EL1_TG0_4K | TCR_EL1_IRGN1_WB | TCR_EL1_ORGN1_WB |
              TCR_EL1_SH1_INNER | TCR_EL1_TG1_4K;
    MSR(tcr_el1, tcr);
    ISB();
    
    /* Set TTBR0_EL1 */
    MSR(ttbr0_el1, (u64)l0_table);
    ISB();
    
    /* Enable MMU + caches */
    u64 sctlr = mrs_sctlr_el1();
    sctlr |= SCTLR_M | SCTLR_C | SCTLR_I | SCTLR_SA0 | SCTLR_SA;
    msr_sctlr_el1(sctlr);
    ISB();
}