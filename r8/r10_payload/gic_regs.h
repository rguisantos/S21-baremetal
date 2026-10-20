/* Absolute GICv3 MMIO addresses. Never add their base a second time.
 * Only registers used by the single-CPU stage are exposed here. */
#ifndef R10_GIC_REGS_H
#define R10_GIC_REGS_H
#define GICD_BASE 0x10200000UL
#define GICR_BASE 0x10240000UL
#define GICR_SGI_BASE 0x10000UL
#define GICR_CTLR(base) ((base) + 0x0000)
#define GICR_TYPER(base) ((base) + 0x0008)
#define GICR_WAKER(base) ((base) + 0x0014)
#define GICR_SGI_IGROUPR(base) ((base) + GICR_SGI_BASE + 0x0080)
#define GICR_SGI_ISENABLER(base) ((base) + GICR_SGI_BASE + 0x0100)
#define GICR_SGI_ICENABLER(base) ((base) + GICR_SGI_BASE + 0x0180)
#define GICR_SGI_IPRIORITYR(base) ((base) + GICR_SGI_BASE + 0x0400)
#define GICD_CTLR_DS (1U << 6)
#define GICR_WAKER_PROCESSOR_SLEEP (1U << 1)
#define GICR_WAKER_CHILDREN_ASLEEP (1U << 2)
#define ICC_SRE_EL1_SRE (1U << 0)
#define ICC_CTLR_EL1_EOImode (1U << 1)
#define ICC_CTLR_EL1_CBPR (1U << 0)
#define ICC_IAR1_EL1_INTID_MASK 0x00ffffffU
#endif
