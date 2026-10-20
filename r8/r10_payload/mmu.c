/* R10: conservative identity map of first 4 GiB.
 * L0 -> L1 -> L2 (4 KiB granules, 2 MiB blocks). MMIO 0x10000000-0x1fffffff
 * is Device-nGnRnE; all other mapped blocks are Normal WB.
 * This is a bring-up mapping, not a complete Exynos memory map.
 */
#include "r10.h"
#define DESC_VALID (1ULL << 0)
#define DESC_TABLE (1ULL << 1)
#define DESC_AF (1ULL << 10)
#define DESC_SH_INNER (3ULL << 8)
#define DESC_ATTRIDX(n) ((u64)(n) << 2)
#define DESC_BLOCK DESC_VALID
#define MAIR_IDX_DEVICE 0
#define MAIR_IDX_NORMAL 2
#define L1_ENTRIES_FOR_4G 4
__attribute__((aligned(4096))) static u64 l0_table[512];
__attribute__((aligned(4096))) static u64 l1_table[512];
__attribute__((aligned(4096))) static u64 l2_tables[L1_ENTRIES_FOR_4G][512];
void mmu_init(void)
{
    for (u64 i=0;i<512;++i) { l0_table[i]=0; l1_table[i]=0; }
    for (u64 t=0;t<L1_ENTRIES_FOR_4G;++t)
        for (u64 i=0;i<512;++i) l2_tables[t][i]=0;
    /* L0[0] covers 512 GiB; four L1 entries cover the first 4 GiB. */
    l0_table[0]=((u64)l1_table & ~0xfffULL)|DESC_VALID|DESC_TABLE;
    for (u64 gb=0;gb<L1_ENTRIES_FOR_4G;++gb) {
        l1_table[gb]=((u64)l2_tables[gb] & ~0xfffULL)|DESC_VALID|DESC_TABLE;
        for (u64 i=0;i<512;++i) {
            u64 pa=gb*0x40000000ULL+i*(u64)BLOCK_SIZE;
            int device=(pa>=0x10000000ULL && pa<0x20000000ULL);
            u64 attr=DESC_ATTRIDX(device?MAIR_IDX_DEVICE:MAIR_IDX_NORMAL);
            if (!device) attr|=DESC_SH_INNER;
            l2_tables[gb][i]=(pa & 0x0000ffffffe00000ULL)|attr|DESC_AF|DESC_BLOCK;
        }
    }
    /* MAIR AttrIdx 0 = Device-nGnRnE; AttrIdx 2 = Normal WB. */
    u64 mair=0x00ULL|(0x44ULL<<8)|(0xffULL<<16);
    MSR(mair_el1,mair);
    /* TG1=10b encodes 4 KiB; TG1=00b would encode 16 KiB. */
    u64 tcr=TCR_EL1_T0SZ(48)|TCR_EL1_IRGN0_WB|TCR_EL1_ORGN0_WB|
             TCR_EL1_SH0_INNER|TCR_EL1_TG0_4K|TCR_EL1_T1SZ(48)|
             TCR_EL1_IRGN1_WB|TCR_EL1_ORGN1_WB|TCR_EL1_SH1_INNER|(2ULL<<30);
    MSR(tcr_el1,tcr);
    MSR(ttbr0_el1,(u64)l0_table);
    MSR(ttbr1_el1,(u64)l0_table);
    asm volatile("dsb sy\n\ttlbi vmalle1\n\tdsb sy\n\tisb" ::: "memory");
    u64 sctlr=mrs_sctlr_el1();
    sctlr|=SCTLR_M|SCTLR_C|SCTLR_I|SCTLR_SA0|SCTLR_SA;
    MSR(sctlr_el1,sctlr);
    asm volatile("isb" ::: "memory");
}
