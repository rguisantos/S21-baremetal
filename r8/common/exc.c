/* exc.c — despacho e decodificação de exceções (nível didático)
 *
 * Decodifica ESR_EL1: EC (bits 31:26) = classe, ISS (bits 24:0) =
 * detalhes. Para Data Aborts: ISS.WnR (bit 6) diz leitura/escrita e
 * ISS.DFSC (bits 5:0) diz a razão (tradução vs permissão, e nível).
 */

#include "r8lib.h"

_Static_assert(sizeof(struct exc_frame) == 0x120, "frame visivel: 288 bytes");
_Static_assert(__builtin_offsetof(struct exc_frame, elr) == 248, "offset elr");
_Static_assert(__builtin_offsetof(struct exc_frame, spsr) == 256, "offset spsr");
_Static_assert(__builtin_offsetof(struct exc_frame, esr) == 264, "offset esr");
_Static_assert(__builtin_offsetof(struct exc_frame, far) == 272, "offset far");

static const char *ec_name(u32 ec)
{
    switch (ec) {
    case 0x00: return "Undefined instruction";
    case 0x07: return "FP/SIMD access trap";
    case 0x0e: return "Illegal Execution State";
    case 0x15: return "SVC (AArch64)";
    case 0x16: return "HVC";
    case 0x17: return "SMC";
    case 0x18: return "MSR/MRS trap";
    case 0x20: return "Instruction Abort (menor EL)";
    case 0x21: return "Instruction Abort (EL atual)";
    case 0x22: return "PC alignment fault";
    case 0x24: return "Data Abort (menor EL)";
    case 0x25: return "Data Abort (EL atual)";
    case 0x26: return "SP alignment fault";
    default:   return "outra classe";
    }
}

static const char *dfsc_name(u32 dfsc, unsigned *level)
{
    /* Tabela FSC (ARMv8) — ISS[5:0] de Data/Instruction Aborts.
     * Encodings de level conferem com arm_fi_to_lfsc() do QEMU:
     *   translation = 0b000100 | lvl   access flag = 0b001000 | lvl
     *   permission  = 0b001100 | lvl                                */
    if (dfsc >= 4 && dfsc <= 7) {
        *level = dfsc - 4;
        return "translation fault";
    }
    if (dfsc >= 8 && dfsc <= 11) {
        *level = dfsc - 8;
        return "access flag fault";
    }
    if (dfsc >= 12 && dfsc <= 15) {
        *level = dfsc - 12;
        return "permission fault";
    }
    if (dfsc <= 3) {
        *level = dfsc;
        return "address size fault";
    }
    if (dfsc == 33) return "alignment fault";
    return "?";
}

void exc_unexpected_c(unsigned from_vector)
{
    (void)from_vector;
    printf("\n[EXC!!] exceção em slot inesperado (SP_EL0/lower EL) — parando\n");
    park();
}

/* hook default: módulos que usam IRQ (r8c) sobrepõem com versão forte */
void __attribute__((weak)) irq_hook(struct exc_frame *f)
{
    (void)f;
    printf("[EXC!!] IRQ chegou sem handler registrado — parando\n");
    park();
}

void exc_dispatch(struct exc_frame *f, u64 kind)
{
    switch (kind) {
    case KIND_SYNC: {
        u32 esr = (u32)f->esr;
        u32 ec  = (esr >> 26) & 0x3f;
        u32 iss = esr & 0x1ffffff;

        printf("\n  [EXC sync] ELR=%p  ESR=%#010x  EC=%#02x (%s)\n",
               f->elr, esr, ec, ec_name(ec));

        if (ec == 0x24 || ec == 0x25) {
            unsigned lvl = 0;
            const char *w = (iss >> 6) & 1 ? "ESCRITA" : "leitura";
            printf("             FAR=%p  %s  DFSC=%#02x (%s L%u)\n",
                   f->far, w, iss & 0x3f, dfsc_name(iss & 0x3f, &lvl), lvl);
        }
        if (ec == 0x00)
            printf("             ISS=%#010x (registrador de nível errado?)\n", iss);

        /* recuperação DIDÁTICA: pular a instrução que faultou.
         * Nota: QEMU reporta IL=1 em faults de MMU vindos de caminhada
         * de tabelas — mas os LDR/STR plantados aqui têm 4 bytes, então
         * avançar 4 é seguro NESTE kit (um OS real decodificaria a
         * instrução para saber o tamanho). */
        f->elr += 4;
        printf("             recuperado: ELR += 4 (IL=%u) e seguimos\n",
               (esr >> 25) & 1);
        break;
    }
    case KIND_IRQ:
    case KIND_FIQ:
        irq_hook(f);
        break;
    case KIND_SERROR:
        printf("\n[EXC!!] SError — parando\n");
        park();
    default:
        park();
    }
}
