/* el.c — R8B: a escada de exception levels EL3 -> EL2 -> EL1
 *
 * Rodar com:  -M virt,secure=on,virtualization=on  (entrada em EL3).
 *   secure=on dá o EL3; virtualization=on IMPLEMENTA o EL2 — sem ele
 *   o virt nasce sem EL2 e o ERET seria ilegal mesmo com SCR perfeito.
 * Sem secure: entra em EL2 e a escada começa um degrau abaixo (adaptativo).
 *
 * Demonstrações:
 *  1. relatório de cada nível (CurrentEL, SCR_EL3, HCR_EL2)
 *  2. o ritual do ERET sintetizado para descer de nível
 *  3. "o muro": MSR SCR_EL3 executado em EL1 -> undefined instruction
 *     capturado pelo nosso handler (EC=0x00)
 */

#include "r8lib.h"

void module_main(unsigned entry_el)
{
    uart_init();
    printf("\n");
    puts("=== R8B — Exception Levels: escada EL3 -> EL2 -> EL1 ===");
    printf("entry: CurrentEL = EL%u\n", entry_el);

    if (entry_el == 3) {
        printf("[EL3] monitor seguro. SCR_EL3 (reset do QEMU)=%#018lx\n",
               MRS(scr_el3));
        puts("      reset = 0x30: sao os RES1 (bits 4,5) — nao sao RW/NS;");
        puts("      a arquitetura entrega RW=NS=EEL2=0. Quem grava e o EL3.");
        puts("[EL3] ERET -> EL2h:  SPSR_EL3=0x3c9  ELR=&el2_trampoline");
        puts("[EL3] o drop programa o SCR_EL3 antes do ERET (DDI0487):");
        puts("      RES1 (bits 4,5): \"reserved should-be-1\" (TF-A grava)");
        puts("      RW   (bit 10): EL2 e EL1 em AArch64. Sem ele, o SPSR");
        puts("            pede AArch64: retorno ILEGAL -> PSTATE.IL=1.");
        puts("      NS   (bit  0): alvo nao-seguro — e la que um OS vive");
        puts("      EEL2 (bit 18): liga o EL2 no mundo SEGURO (FEAT_SEL2);");
        puts("            p/ EL2 nao-seguro nao e exigido — mas o EL3 manda.");
        drop_from_el3_to_el2((u64)el2_trampoline);
    } else if (entry_el == 2) {
        puts("(secure=off: entrada ja no EL2)");
        el2_stage();
    } else {
        printf("entrada inesperada em EL%u — parando\n", entry_el);
    }
    park();
}

void el2_stage(void)
{
    printf("[EL2] hypervisor. CurrentEL=%u  HCR_EL2=%#018lx\n",
           get_current_el(), MRS(hcr_el2));
    puts("      ERET -> EL1h:  SPSR_EL2=0x3c5  ELR=&el1_trampoline");
    drop_from_el2_to_el1((u64)el1_trampoline);
    park();
}

void el1_stage(void)
{
    printf("[EL1] chegamos. CurrentEL=%u — o nivel onde um OS vive\n", get_current_el());
    vbar_install();
    printf("[EL1] VBAR_EL1=%p instalada\n", vectors);

    puts("\n-- o muro de privilegio --");
    puts("   executando \"msr scr_el3, xzr\" AQUI, no EL1...");
    asm volatile("msr scr_el3, xzr" ::: "memory");
    puts("   [MURO] bloqueado: trap de instrucao indefinida (EC=0x00).");
    puts("   [MURO] o handler capturou, decodificou e pulou a instrucao.");
    puts("   [MURO] registradores de EL3 so existem para quem esta no EL3.");

    puts("\n=== R8B PASS — a escada desce, mas nao sobe sem permissao ===\n");
    shutdown();
}
