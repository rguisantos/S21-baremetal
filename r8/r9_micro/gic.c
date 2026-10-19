/* gic.c — R9: bring-up do GICv3 (herdado comprovado do R8C)
 *
 * Mapa no QEMU virt (hw/arm/virt.c), validado no R8C por leitura:
 *   GICD 0x08000000 — o MESMO endereço no GICv2 e no GICv3.
 *   GICR 0x080A0000 — frames de 128 KB por CPU (RD_base + SGI_base).
 *   ITS  0x08080000 — ARMADILHA conhecida: não é o GICD (R8C passou por cá).
 *
 * Sem EL3 no sistema o GIC fica em "single security state" (DS=1):
 * ARE é RAO/WI e só os bits 0 e 1 gravam no GICD_CTLR. O timer sinaliza
 * como PPI INTID 30 (CNTP), Group 1 — sem EN_GRP1NS ele nunca sobe.
 *
 * Diferença do R8C: o ACK/EOI mora aqui (gic_ack/gic_eoi) para o
 * handler de IRQ do scheduler usar — o protocolo é o mesmo ciclo.
 */

#include "r9.h"

#define GICD_BASE      0x08000000UL
#define GICR_BASE      0x080A0000UL

#define GICD_CTLR      (GICD_BASE + 0x000)
#define GICD_TYPER     (GICD_BASE + 0x004)

#define GICR_WAKER     (GICR_BASE + 0x014)
#define GICR_SGI_BASE  (GICR_BASE + 0x10000)
#define GICR_IGROUPR0  (GICR_SGI_BASE + 0x080)
#define GICR_ISENABLER0 (GICR_SGI_BASE + 0x100)

#define INTID_CNTP     30          /* PPI: non-secure physical timer */

/* binutils 2.44 não conhece os NOMES ICC_EOR*_EL1 — encodings numéricos:
 *   ICC_EOR1_EL1 = s3_0_c12_c12_1    ICC_EOR0_EL1 = s3_0_c12_c8_1     */
#define MSR_EOR1(v) asm volatile("msr s3_0_c12_c12_1, %0" :: "r"((u64)(v)) : "memory")
#define MSR_EOR0(v) asm volatile("msr s3_0_c12_c8_1,  %0" :: "r"((u64)(v)) : "memory")

void gic_init(void)          /* chamado no EL2, antes do drop */
{
    printf("[GIC] GICD @ %p   GICR @ %p\n", GICD_BASE, GICR_BASE);
    printf("[GIC] GICD_TYPER = %#010x\n", mmio_r(GICD_TYPER));

    /* redistributor: tirar do sono */
    mmio_w(GICR_WAKER, 0);
    u32 spins = 0;
    while ((mmio_r(GICR_WAKER) & (1u << 2)) && ++spins < 1000000)
        ;
    printf("[GIC] redistributor acordou (WAKER=%#010x, %u spins)\n",
           mmio_r(GICR_WAKER), spins);

    /* INTID 30 (PPI): Group 1 (sinaliza como IRQ no EL1 nao-seguro) */
    mmio_w(GICR_IGROUPR0, mmio_r(GICR_IGROUPR0) | (1u << INTID_CNTP));
    mmio_w(GICR_ISENABLER0, mmio_r(GICR_ISENABLER0) | (1u << INTID_CNTP));
    printf("[GIC] INTID %u (CNTP) em Group 1 e habilitado\n", INTID_CNTP);

    mmio_w(GICD_CTLR, 0x3);  /* EN_GRP0 | EN_GRP1NS (restante: RAO/WI)  */
    printf("[GIC] GICD_CTLR = %#010x (DS|ARE RAO; so' os bits 0,1 gravam)\n",
           mmio_r(GICD_CTLR));

    MSR(cnthctl_el2, 3);     /* EL1PCEN | EL1PCTEN: EL1 toca o CNTP    */
    MSR(icc_sre_el2, 7);     /* system registers da CPU interface      */
    printf("[GIC] ICC_SRE_EL2 = %#lx\n", MRS(icc_sre_el2));
}

u64 gic_ack(u32 *intid, int *from_g0)
{
    u64 iar = MRS(icc_iar1_el1);              /* ACK (Group 1)        */
    *intid   = (u32)(iar & 0xffffff);
    *from_g0 = 0;

    if (*intid == 0x3ff) {                     /* spurious no G1?      */
        iar = MRS(icc_iar0_el1);               /* tenta Group 0        */
        *intid   = (u32)(iar & 0xffffff);
        *from_g0 = 1;
    }
    return iar;
}

void gic_eoi(u64 iar, int from_g0)
{
    if ((u32)(iar & 0xffffff) == 0x3ff)
        return;                                /* spurious: sem EOI    */
    if (from_g0)
        MSR_EOR0(iar);                         /* EOI no grupo certo   */
    else
        MSR_EOR1(iar);
}
