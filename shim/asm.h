#ifndef ASM_H
#define ASM_H

#include <stdint.h>

/* System register read/write */
#define rsr(r) ({ uint64_t _v; __asm__ volatile("mrs %0, " r : "=r"(_v)); _v; })
#define wsr(r, v) __asm__ volatile("msr " r ", %0" : : "r"((uint64_t)(v)))
#define isb() __asm__ volatile("isb" ::: "memory")
#define dsb(opt) __asm__ volatile("dsb " #opt ::: "memory")
#define dmb(opt) __asm__ volatile("dmb " #opt ::: "memory")

/* Memory-mapped register access */
static inline uint32_t rd32(uintptr_t addr) {
    return *(volatile uint32_t *)addr;
}

static inline void wr32(uintptr_t addr, uint32_t val) {
    *(volatile uint32_t *)addr = val;
}

static inline uint64_t rd64(uintptr_t addr) {
    return *(volatile uint64_t *)addr;
}

static inline void wr64(uintptr_t addr, uint64_t val) {
    *(volatile uint64_t *)addr = val;
}

/* PSCI */
#define PSCI_VERSION      0x84000000UL
#define PSCI_CPU_ON       0xc4000003UL
#define PSCI_CPU_OFF      0x84000002UL
#define PSCI_SYSTEM_RESET 0x84000009UL
#define PSCI_SYSTEM_OFF   0x84000008UL

/* Colors */
#define COL_RED    0xffff0000
#define COL_GREEN  0xff00ff00
#define COL_BLUE   0xff0000ff
#define COL_WHITE  0xffffffff
#define COL_BLACK  0xff000000

extern void reset(unsigned after_s);

#endif