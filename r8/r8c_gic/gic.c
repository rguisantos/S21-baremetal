/* gic.c — R8C: bring-up do GICv3 (distributor + redistributor + ICC)
 *
 * Mapa no QEMU virt (hw/arm/virt.c), confirmado pelo DTB real:
 *   GICD 0x08000000 (64 KB) — o MESMO endereço no GICv2 e no GICv3.
 *   GICR 0x080A0000 (frames de 128 KB por CPU: RD_base + SGI_base).
 *   ITS  0x08080000 — ARMADILHA: não é o GICD. Já apontamos p/ cá
 *   por engano: o "GICD_CTLR=0x80000001" lido era GITS_CTLR (ITS
 *   ligado + RWP) e o "TYPER=0x43b" era GITS_IIDR, a assinatura do
 *   QEMU. O endereço fala mais alto que o comentário.
 *
 * Plano (o clássico de qualquer bring-up de GICv3):
 *   EL2: acordar redistributor, INTID 30 (PPI do CNTP) em Group 1,
 *        habilitar INTID 30, ligar distributor, ICC_SRE_EL2=7
 *   EL1: ICC_PMR=0xff (deixa tudo passar), ICC_IGRPEN1=1,
 *        VBAR, timer, daifclr
 */

#include "r8lib.h"

#define GICD_BASE      0x08000000UL   /* virt: GICD v2 E v3 (ITS fica em 0x08080000) */
#define GICR_BASE      0x080A0000UL

#define GICD_CTLR      (GICD_BASE + 0x000)
#define GICD_TYPER     (GICD_BASE + 0x004)

#define GICR_WAKER     (GICR_BASE + 0x014)
#define GICR_SGI_BASE  (GICR_BASE + 0x10000)
#define GICR_IGROUPR0  (GICR_SGI_BASE + 0x080)
#define GICR_ISENABLER0 (GICR_SGI_BASE + 0x100)

#define INTID_CNTP     30          /* PPI: non-secure physical timer */

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

    /* Distributor: habilita os grupos. Sem EL3 no sistema, o GIC é
     * "single security state" (DS=1): ARE é RAO/WI (roteamento por
     * afinidade sempre ligado — é o que dá vida ao GICR) e só os
     * bits 0 (EN_GRP0) e 1 (EN_GRP1NS) gravam no CTLR. O IRQ do
     * timer é Group 1: sem EN_GRP1NS ele fica pendente e nunca sobe. */
    mmio_w(GICD_CTLR, 0x3);    /* EN_GRP0 | EN_GRP1NS (o restante: RAO/WI) */
    printf("[GIC] GICD_CTLR = %#010x (DS|ARE RAO; so' os bits 0,1 gravam)\n",
           mmio_r(GICD_CTLR));

    /* CNTHCTL_EL2: libera o EL1 a tocar o timer fisico
     * (sem EL1PCEN/EL1PCTEN, CNTP_* no EL1 trapa para um EL2 sem VBAR) */
    MSR(cnthctl_el2, 3);           /* EL1PCEN | EL1PCTEN */

    /* system registers da CPU interface: SRE=1 (usar ICC_*), Enable p/ EL1 */
    MSR(icc_sre_el2, 7);
    printf("[GIC] ICC_SRE_EL2 = %#lx\n", MRS(icc_sre_el2));
}
