/* smp.c — R10: SMP bring-up, IPI, cross-CPU calls */

#include "r10.h"
#include "percpu.h"

/* Per-CPU data array */
struct percpu_data percpu_data_array[NR_CPUS] __attribute__((aligned(64)));

/* Secondary CPU boot synchronization - one per CPU */
volatile int secondary_holding_pen[NR_CPUS] = {0};
volatile u64 secondary_entry_point = 0;
volatile u64 secondary_context = 0;

/* IPI handlers - initialized once, never cleared */
static void (*ipi_handlers[IPI_MAX])(void) = {0};
static bool ipi_handlers_initialized = false;

/* SMP call function data */
static struct smp_call_data smp_call_data[NR_CPUS];

/* Per-CPU stack storage (defined in linker_r10.ld) */
extern char __sec_cpu_stacks[];
extern char __sec_exc_stacks[];

/* Stack sizes for secondary CPUs */
#define SEC_CPU_STACK_SIZE    (16 * 1024)   /* 16KB per CPU for EL1 stack */
#define SEC_EXC_STACK_SIZE    (4 * 1024)    /* 4KB per CPU for exception stack */

extern char __sec_cpu_stacks[];
extern char __sec_exc_stacks[];

#define SEC_CPU_STACK(i)     ((u64)__sec_cpu_stacks + (i) * SEC_CPU_STACK_SIZE + SEC_CPU_STACK_SIZE)
#define SEC_EXC_STACK(i)     ((u64)__sec_exc_stacks + (i) * SEC_EXC_STACK_SIZE + SEC_EXC_STACK_SIZE)

/* ================================================================
 * Per-CPU Early Init (called from primary CPU before SMP bringup)
 * ================================================================ */

void percpu_init_early(void)
{
    u32 cpu = get_current_cpu();
    u64 mpidr = get_current_mpidr();
    
    struct percpu_data *pcpu = &percpu_data_array[cpu];
    pcpu->cpu_id = cpu;
    pcpu->mpidr = mpidr;
    pcpu->preempt_count = 0;
    pcpu->preempt_need_resched = 0;
    pcpu->lock_depth = 0;
    
    uart_puts("percpu: CPU "); uart_puthex(cpu); uart_puts(" (MPIDR="); uart_puthex(mpidr); uart_puts(") early init\n");
}

void percpu_init_cpu(u32 cpu_id, u64 mpidr, u64 sp_el1, u64 exc_stack_top)
{
    struct percpu_data *pcpu = &percpu_data_array[cpu_id];
    pcpu->cpu_id = cpu_id;
    pcpu->mpidr = mpidr;
    pcpu->sp_el1 = sp_el1;
    pcpu->exc_stack_top = exc_stack_top;
    pcpu->preempt_count = 0;
    pcpu->preempt_need_resched = 0;
pcpu->lock_depth = 0;
    
    /* IPI handlers are initialized ONCE globally, not per-CPU */
    /* Do NOT clear ipi_handlers here - they are global */
}

void percpu_init_late(void)
{
    uart_puts("percpu: late init done\n");
}

/* ================================================================
 * Secondary CPU Entry Point (called from start_r10.S)
 * ================================================================ */

void secondary_cpu_entry(void)
{
    u32 cpu = get_current_cpu();
    struct percpu_data *pcpu = &percpu_data_array[cpu];
    
    /* Set up EL1 stack (already set via MSR SP_EL1 in start_r10.S) */
    MSR(spsel, 1);
    
    /* Install vector table */
    vbar_install();
    
    /* Initialize CPU interface */
    gic_cpu_interface_init();
    
    /* Mark CPU online */
    uart_puts("CPU "); uart_puthex(cpu); uart_puts(" online\n");
    
    /* Signal ready - per-CPU flag */
    __atomic_store_n(&secondary_holding_pen[cpu], 0, __ATOMIC_RELEASE);
    asm volatile("sev" ::: "memory");
    
    /* Wait for work (idle loop) */
    while (1) {
        asm volatile("wfe" ::: "memory");
        if (pcpu->preempt_need_resched) {
            pcpu->preempt_need_resched = 0;
            /* Schedule next task */
        }
    }
}

/* ================================================================
 * SMP Bring-up
 * ================================================================ */

int smp_bringup_cpus(void)
{
    uart_puts("SMP: Bringing up secondary CPUs...\n");
    
    /* CPU topology from DTB:
     * CPU 0: A55 (boot CPU)
     * CPU 1-3: A55
     * CPU 4-6: A78
     * CPU 7: X1
     */
    
    u64 mpidr_table[NR_CPUS] = {
        0x00, 0x01, 0x02, 0x03,  // A55 cluster
        0x04, 0x05, 0x06,        // A78 cluster
        0x07                     // X1
    };
    
    int online = 1;  // CPU 0 already online
    
    for (int i = 1; i < NR_CPUS; i++) {
        uart_puts("SMP: Starting CPU "); uart_puthex(i); uart_puts(" (MPIDR="); uart_puthex(mpidr_table[i]); uart_puts(")...\n");
        
        /* Set up secondary entry point and context */
        secondary_entry_point = (u64)secondary_cpu_entry;
        secondary_context = mpidr_table[i];
        secondary_holding_pen[i] = 1;
        
        /* Allocate dedicated stacks for secondary CPU from linker-defined areas */
        u64 sp_el1 = SEC_CPU_STACK(i);
        u64 exc_stack = SEC_EXC_STACK(i);
        
        /* Initialize per-CPU data for secondary */
        percpu_init_cpu(i, mpidr_table[i], sp_el1, exc_stack);
        
        /* Call PSCI CPU_ON with MPIDR as context (passed in x0 to _start_r10) */
        s64 ret = psci_cpu_on(mpidr_table[i], (u64)_secondary_start_r10, mpidr_table[i]);
        
        if (ret != PSCI_SUCCESS) {
            uart_puts("SMP: CPU_ON failed for CPU "); uart_puthex(i); uart_puts(": ");
            psci_print_error(ret); uart_putc('\n');
            continue;
        }
        
        /* Wait for secondary to signal ready - per-CPU flag */
        int timeout = 1000000;
        while (secondary_holding_pen[i] && timeout--) {
            asm volatile("wfe" ::: "memory");
        }
        
        if (timeout <= 0) {
            uart_puts("SMP: CPU "); uart_puthex(i); uart_puts(" timeout\n");
            continue;
        }
        
        online++;
        uart_puts("SMP: CPU "); uart_puthex(i); uart_puts(" online\n");
    }
    
    uart_puts("SMP: "); uart_puthex(online); uart_puts("/"); uart_puthex(NR_CPUS); uart_puts(" CPUs online\n");
    return online;
}

int smp_init(void)
{
    percpu_init_early();
    return smp_bringup_cpus();
}

/* ================================================================
 * IPI (Inter-Processor Interrupt) Handling
 * ================================================================ */

void ipi_register_handler(u32 ipi_type, void (*handler)(void))
{
    if (ipi_type < IPI_MAX) {
        ipi_handlers[ipi_type] = handler;
        ipi_handlers_initialized = true;
    }
}

void ipi_send(u32 target_cpu, u32 ipi_type)
{
    if (target_cpu >= NR_CPUS || ipi_type >= IPI_MAX) return;
    
    u64 mpidr = percpu_data_array[target_cpu].mpidr;
    u32 aff0 = (u32)(mpidr & 0xff);
    u32 aff1 = (u32)((mpidr >> 8) & 0xff);
    u32 aff2 = (u32)((mpidr >> 16) & 0xff);
    u32 aff3 = (u32)((mpidr >> 32) & 0xff);
    if (aff0 >= 16) return; /* TargetList only addresses Aff0 0..15, RS=0. */
    gic_send_sgi(ipi_type, 1U << aff0, aff1, aff2, aff3);
}

void ipi_send_mask(u32 cpu_mask, u32 ipi_type)
{
    for (int i = 0; i < NR_CPUS; i++) {
        if (cpu_mask & (1 << i)) {
            ipi_send(i, ipi_type);
        }
    }
}

void ipi_send_all_but_self(u32 ipi_type)
{
    u32 self = get_current_cpu();
    u32 mask = ((1 << NR_CPUS) - 1) & ~(1 << self);
    ipi_send_mask(mask, ipi_type);
}

void ipi_handle(u32 ipi_type)
{
    if (ipi_type < IPI_MAX && ipi_handlers[ipi_type]) {
        ipi_handlers[ipi_type]();
    }
}

/* IPI handler called from exc_irq */
void ipi_handler(u32 sgi_id)
{
    ipi_handle(sgi_id);
}

/* ================================================================
 * Cross-CPU Function Calls
 * ================================================================ */

void smp_call_function_single(int cpu, smp_func_t func, void *arg, int wait)
{
    if (cpu < 0 || cpu >= NR_CPUS) return;
    if (cpu == get_current_cpu()) {
        func(arg);
        return;
    }
    
    struct smp_call_data *data = &smp_call_data[cpu];
    data->func = func;
    data->arg = arg;
    data->done = 0;
    
    /* Send IPI to target CPU */
    ipi_send(cpu, IPI_CALL_FUNC);
    
    if (wait) {
        while (!data->done) {
            asm volatile("wfe" ::: "memory");
        }
    }
}

void smp_call_function_many(const u32 *cpu_mask, smp_func_t func, void *arg, int wait)
{
    for (int i = 0; i < NR_CPUS; i++) {
        if (cpu_mask && !(cpu_mask[i / 32] & (1 << (i % 32)))) continue;
        if (i == get_current_cpu()) continue;
        
        struct smp_call_data *data = &smp_call_data[i];
        data->func = func;
        data->arg = arg;
        data->done = 0;
        
        ipi_send(i, IPI_CALL_FUNC);
    }
    
    if (wait) {
        for (int i = 0; i < NR_CPUS; i++) {
            if (cpu_mask && !(cpu_mask[i / 32] & (1 << (i % 32)))) continue;
            if (i == get_current_cpu()) continue;
            
            while (!smp_call_data[i].done) {
                asm volatile("wfe" ::: "memory");
            }
        }
    }
}

void smp_call_function_all(smp_func_t func, void *arg, int wait)
{
    for (int i = 0; i < NR_CPUS; i++) {
        if (i == get_current_cpu()) continue;
        
        struct smp_call_data *data = &smp_call_data[i];
        data->func = func;
        data->arg = arg;
        data->done = 0;
        
        ipi_send(i, IPI_CALL_FUNC);
    }
    
    if (wait) {
        for (int i = 0; i < NR_CPUS; i++) {
            if (i == get_current_cpu()) continue;
            while (!smp_call_data[i].done) {
                asm volatile("wfe" ::: "memory");
            }
        }
    }
}

/* IPI handler for CALL_FUNC */
static void ipi_call_func_handler(void)
{
    u32 cpu = get_current_cpu();
    struct smp_call_data *data = &smp_call_data[cpu];
    
    if (data->func) {
        data->func(data->arg);
    }
    data->done = 1;
    asm volatile("sev" ::: "memory");
}

/* Register IPI handlers at init */
void ipi_init(void)
{
    ipi_register_handler(IPI_CALL_FUNC, ipi_call_func_handler);
    /* Others registered as needed */
}