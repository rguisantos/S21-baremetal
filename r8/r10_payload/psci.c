/* psci.c — R10: PSCI client (SMC + HVC fallback) with SMP support */

#include "r10.h"

/* PSCI via SMC (per DTB) */
static inline s64 psci_smc(u64 fn, u64 arg0, u64 arg1, u64 arg2)
{
    register u64 x0 asm("x0") = fn;
    register u64 x1 asm("x1") = arg0;
    register u64 x2 asm("x2") = arg1;
    register u64 x3 asm("x3") = arg2;
    
    asm volatile("smc #0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3) : "memory");
    return (s64)x0;
}

/* PSCI via HVC (per BL firmware strings) */
static inline s64 psci_hvc(u64 fn, u64 arg0, u64 arg1, u64 arg2)
{
    register u64 x0 asm("x0") = fn;
    register u64 x1 asm("x1") = arg0;
    register u64 x2 asm("x2") = arg1;
    register u64 x3 asm("x3") = arg2;
    
    asm volatile("hvc #0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3) : "memory");
    return (s64)x0;
}

s64 psci_call(u64 fn, u64 arg0, u64 arg1, u64 arg2)
{
    /* Try SMC first (per DTB) */
    s64 ret = psci_smc(fn, arg0, arg1, arg2);
    
    /* If not supported, try HVC (per BL strings) */
    if (ret == PSCI_NOT_SUPPORTED) {
        ret = psci_hvc(fn, arg0, arg1, arg2);
    }
    
    return ret;
}

/* PSCI CPU_ON: bring up secondary CPU
 * fn: PSCI_CPU_ON (0x84000003)
 * arg0: target CPU MPIDR (Aff1<<8 | Aff0)
 * arg1: entry point address
 * arg2: context ID (passed to entry in x0)
 */
s64 psci_cpu_on(u64 target_mpidr, u64 entry_point, u64 context)
{
    return psci_call(PSCI_CPU_ON, target_mpidr, entry_point, context);
}

/* PSCI CPU_OFF: power off calling CPU */
s64 psci_cpu_off(void)
{
    return psci_call(PSCI_CPU_OFF, 0, 0, 0);
}

/* PSCI CPU_SUSPEND: suspend to power state */
s64 psci_cpu_suspend(u64 power_state, u64 entry_point, u64 context)
{
    return psci_call(PSCI_CPU_SUSPEND, power_state, entry_point, context);
}

/* PSCI SYSTEM_RESET */
s64 psci_system_reset(void)
{
    return psci_call(PSCI_SYSTEM_RESET, 0, 0, 0);
}

/* PSCI SYSTEM_OFF */
s64 psci_system_off(void)
{
    return psci_call(PSCI_SYSTEM_OFF, 0, 0, 0);
}

/* PSCI VERSION */
s64 psci_version(void)
{
    return psci_call(PSCI_VERSION, 0, 0, 0);
}

/* PSCI MIGRATE_INFO_TYPE */
s64 psci_migrate_info_type(void)
{
    return psci_call(PSCI_MIG_INFO_TYPE, 0, 0, 0);
}

/* Print PSCI error string */
void psci_print_error(s64 ret)
{
    switch (ret) {
        case PSCI_SUCCESS: uart_puts("SUCCESS"); break;
        case PSCI_NOT_SUPPORTED: uart_puts("NOT_SUPPORTED"); break;
        case PSCI_INVALID_PARAM: uart_puts("INVALID_PARAM"); break;
        case PSCI_DENIED: uart_puts("DENIED"); break;
        case PSCI_ALREADY_ON: uart_puts("ALREADY_ON"); break;
        case PSCI_ON_PENDING: uart_puts("ON_PENDING"); break;
        case PSCI_INTERNAL_FAIL: uart_puts("INTERNAL_FAIL"); break;
        case PSCI_NOT_PRESENT: uart_puts("NOT_PRESENT"); break;
        case PSCI_DISABLED: uart_puts("DISABLED"); break;
        case PSCI_INVALID_ADDRESS: uart_puts("INVALID_ADDRESS"); break;
        default: uart_puts("UNKNOWN"); break;
    }
}

/* Get current CPU MPIDR (Aff1<<8 | Aff0) */
u64 psci_get_mpidr(void)
{
    return mrs_mpidr_el1() & 0xFF;  // Aff0 only for our topology
}