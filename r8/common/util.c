/* util.c — helpers comuns (bare-metal, sem libc) */

#include "r8lib.h"

unsigned get_current_el(void)
{
    u64 v;
    asm volatile("mrs %0, CurrentEL" : "=r"(v));
    return (unsigned)((v >> 2) & 3);
}

void vbar_install(void)
{
    asm volatile("msr vbar_el1, %0" :: "r"((u64)vectors) : "memory");
    asm volatile("isb");
}

void park(void)
{
    for (;;)
        asm volatile("wfe");
}

/* PSCI SYSTEM_OFF — sai do QEMU de forma limpa.
 * Conduit: SMC quando há EL3 no sistema, HVC caso contrário.
 * A presença de EL3 é detectável em ID_AA64PFR0_EL1. */
static int el3_present(void)
{
    u64 v;
    asm volatile("mrs %0, id_aa64pfr0_el1" : "=r"(v));
    return ((v >> 12) & 0xf) != 0;
}

void shutdown(void)
{
    register u64 x0 asm("x0") = 0x84000008UL;   /* PSCI 0.2 SYSTEM_OFF */

    if (el3_present())
        asm volatile("smc #0" :: "r"(x0) : "memory");
    else
        asm volatile("hvc #0" :: "r"(x0) : "memory");
    park();                                     /* se o PSCI falhar, dorme  */
}

void *memset(void *d, int c, u64 n)
{
    u8 *p = (u8 *)d;
    while (n--)
        *p++ = (u8)c;
    return d;
}

void *memcpy(void *d, const void *s, u64 n)
{
    u8 *dp = (u8 *)d;
    const u8 *sp = (const u8 *)s;
    while (n--)
        *dp++ = *sp++;
    return d;
}

int memcmp(const void *a, const void *b, u64 n)
{
    const u8 *pa = (const u8 *)a, *pb = (const u8 *)b;
    while (n--) {
        if (*pa != *pb)
            return *pa - *pb;
        pa++; pb++;
    }
    return 0;
}
