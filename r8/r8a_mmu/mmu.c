/* mmu.c — R8A: MMU do zero no EL1 (QEMU virt, AArch64, granule 4 KB)
 *
 * Demonstração:
 *  1. tabelas de página L0/L1/L2 construídas em .bss
 *  2. liga a tradução (MAIR -> TCR -> TTBR0 -> SCTLR.M) com mapa identidade
 *  3. chama uma função pelo ALIAS virtual alto (mesmos bytes, outro VA)
 *  4. Data Abort deliberado: leitura em VA não mapeado (translation fault)
 *  5. Data Abort deliberado: escrita em página read-only (permission fault)
 *
 * Mapa construído (TTBR0, 48-bit VA):
 *   VA [0x00000000, 0x40000000)  -> PA idem, device  (UART, GIC...)
 *   VA [0x40000000, 0x80000000)  -> PA idem, RAM normal
 *   VA [0x8000000000, 0x8040000000) -> espelho (alias) da RAM
 *   VA [0x8040000000, ...)       -> tabela L2: 1a página = código em RO
 */

#include "r8lib.h"

/* ---------------- descritores AArch64 (granule 4 KB) ---------------- */
#define DESC_TABLE   0x3UL          /* bits [1:0] = 11            */
#define DESC_BLOCK   0x1UL          /* bits [1:0] = 01 (L1/L2)    */
#define DESC_PAGE    0x3UL          /* L3: página válida = 0b11
                                     * (no L3, 0b01 é inválido!)  */

#define ATTR_IDX(n)  ((u64)(n) << 2)   /* MAIR index            */
#define AP_RW        (0x0UL << 6)     /* AP[2:1]=00: RW        */
#define AP_RO        (0x2UL << 6)     /* AP[2:1]=10: RO        */
#define SH_INNER     (0x3UL << 8)
#define AF           (0x1UL << 10)    /* access flag (obrigat.) */
#define UXN          (1UL << 54)      /* execute-never para EL0  */
#define NX           ((1UL << 53) | (1UL << 54))  /* PXN|UXN     */

#define MAIR_DEVICE 0
#define MAIR_NORMAL 1

/* ---------------- tabelas (4 KB alinhadas, dentro do .bss) ---------- */
static u64 l0_id[512]    __attribute__((aligned(4096)));
static u64 l1_id[512]    __attribute__((aligned(4096)));
static u64 l1_alias[512] __attribute__((aligned(4096)));
static u64 l2_fine[512]  __attribute__((aligned(4096)));
static u64 l3_page[512]  __attribute__((aligned(4096)));   /* L3 de verdade */

static void build_tables(void)
{
    /* L0[0] -> L1 identidade  (cobre VA 0x0 até 0x8000000000) */
    l0_id[0] = (u64)l1_id | DESC_TABLE;
    /* 1 GB de device: UART 0x09000000, GIC 0x08000000, flash...
     * PXN|UXN: memória de dispositivo nunca é executável */
    l1_id[0] = 0x00000000UL | ATTR_IDX(MAIR_DEVICE) | AF | AP_RW | NX | DESC_BLOCK;
    /* 1 GB de RAM normal: código + pilha + tabelas.
     * UXN apenas: EL1 EXECUTA daqui (PXN aqui = abort no próximo fetch!) */
    l1_id[1] = 0x40000000UL | ATTR_IDX(MAIR_NORMAL) | AF | SH_INNER | AP_RW | UXN | DESC_BLOCK;

    /* L0[1] -> L1 do alias (VA 0x8000000000 = início do 2o 512 GB) */
    l0_id[1] = (u64)l1_alias | DESC_TABLE;
    /* alias: espelho do 1o GB de RAM em VA alto — executável (vamos
     * CHAMAR código por este endereço) */
    l1_alias[0] = 0x40000000UL | ATTR_IDX(MAIR_NORMAL) | AF | SH_INNER | AP_RW | UXN | DESC_BLOCK;
    /* 2o GB do alias desce até L3: L1 -> L2 (tabela) -> L3 (página) */
    l1_alias[1] = (u64)l2_fine | DESC_TABLE;
    l2_fine[0]  = (u64)l3_page | DESC_TABLE;
    /* 1a página de 4 KB: a página do NOSSO código, agora read-only.
     * (No L2, um descritor 0b01 seria um BLOCO de 2 MB — página de
     * 4 KB só existe no L3; a caminhada completa é L0->L1->L2->L3.) */
    l3_page[0]  = 0x40080000UL | ATTR_IDX(MAIR_NORMAL) | AF | SH_INNER | AP_RO | UXN | DESC_PAGE;

    /* VA 0x10000000000 (L0[2]) fica SEM mapeamento -> alvo do fault 1 */
}

static void mmu_enable(void)
{
    u64 mair = (0x00UL)          /* idx0: Device nGnRnE        */
             | (0xFFUL << 8);    /* idx1: Normal WB cacheable  */

    u64 tcr = (16UL)             /* T0SZ=16 -> VA de 48 bits   */
            | (0UL << 14)        /* TG0: granule 4 KB          */
            | (3UL << 12)        /* SH0: inner shareable       */
            | (1UL << 10)        /* ORGN0: write-back          */
            | (1UL << 8)         /* IRGN0: write-back          */
            | (2UL << 32);       /* IPS: PA de 40 bits         */

    MSR(mair_el1,  mair);
    MSR(tcr_el1,   tcr);
    MSR(ttbr0_el1, (u64)l0_id);
    asm volatile("isb");

    u64 sctlr = MRS(sctlr_el1);
    sctlr |= 1;                  /* M=1: MMU ligado            */
    MSR(sctlr_el1, sctlr);
    asm volatile("isb");
}

/* roda pelo VA ALTO: todos os acessos PC-relativos continuam coerentes
 * porque o alias espelha o mesmo físico; o ADR prova o VA real */
static void __attribute__((noinline)) run_from_alias(void)
{
    u64 pc;
    asm volatile("adr %0, ." : "=r"(pc));
    printf("  [ALIAS] executando em VA=%p — os MESMOS bytes físicos,\n", pc);
    printf("          agora vistos por outro endereço virtual\n");
}

/* ------------------------------------------------------------------ */

void module_main(unsigned entry_el)
{
    uart_init();
    printf("\n");
    puts("=== R8A — MMU do zero (QEMU virt, EL1, granule 4 KB) ===");
    printf("entry: CurrentEL = EL%u\n", entry_el);

    if (entry_el == 3) {
        puts("descendo EL3 -> EL2 (ERET, SPSR_EL3=0x3c9, SCR.RW=1, SCR.NS=1)");
        drop_from_el3_to_el2((u64)el2_trampoline);
    } else if (entry_el == 2) {
        el2_stage();
    } else if (entry_el == 1) {
        el1_stage();
    } else {
        printf("EL%u inesperado — parando\n", entry_el);
    }
    park();
}

void el2_stage(void)
{
    puts("[EL2] hypervisor — MMU do EL2 intocado; caindo para o EL1");
    puts("      ERET com SPSR_EL2=0x3c5 (EL1h, DAIF mascarados)");
    drop_from_el2_to_el1((u64)el1_trampoline);
    park();
}

void el1_stage(void)
{
    printf("[EL1] CurrentEL = EL%u — aqui vive o MMU de um OS\n", get_current_el());
    vbar_install();
    printf("[EL1] VBAR_EL1 = %p (16 slots, 2 KB alinhada)\n", vectors);

    puts("\n-- passo 1: VA de execução antes de ligar a tradução --");
    printf("   get_pc() = %p (VA == PA: identidade implicita)\n", get_pc());

    build_tables();
    puts("\n-- passo 2: tabelas prontas (L0 -> L1 id; L0 -> L1 alias -> L2 -> L3) --");
    printf("   L0@%p  L1@%p  L1_alias@%p  L2@%p  L3@%p\n",
           l0_id, l1_id, l1_alias, l2_fine, l3_page);
    puts("   MAIR_EL1=0xff00 (idx0 device, idx1 normal WB)  TCR_EL1: T0SZ=16");

    puts("\n-- passo 3: ligando: MAIR -> TCR -> TTBR0 -> SCTLR.M=1 -> ISB --");
    mmu_enable();
    printf("   get_pc() = %p (o fetch seguinte JA passou pela traducao)\n", get_pc());

    puts("\n-- passo 4: pulando para o alias alto (VA 0x8000000000+) --");
    {
        u64 alias = ((u64)&run_from_alias - 0x40000000UL) + 0x8000000000UL;
        printf("   chamando run_from_alias em VA=%p\n", alias);
        ((void (*)(void))alias)();
        puts("   [EL1] retornou do alias — o mundo identidade continua intacto");
    }

    puts("\n-- passo 5: Data Abort deliberado — leitura em VA NAO mapeado --");
    {
        volatile u64 *bad = (volatile u64 *)0x10000000000UL;
        puts("   lendo 0x10000000000 (L0[2] vazio)...");
        u64 v = *bad;
        (void)v;
        puts("   [EL1] sobrevivi: o handler decodificou ESR/FAR e pulou a instr.");
    }

    puts("\n-- passo 6: Data Abort de PERMISSAO — escrita em pagina RO de 4 KB --");
    {
        puts("   escrevendo 0xdeadbeef em 0x8040000000 (copia RO da pag. do codigo)...");
        *(volatile u64 *)0x8040000000UL = 0xdeadbeefUL;
        puts("   [EL1] sobrevivi de novo: WnR=1 + permission fault contaram tudo");
    }

    puts("\n=== R8A PASS — traducao, alias e faults sob controle ===\n");
    shutdown();
}
