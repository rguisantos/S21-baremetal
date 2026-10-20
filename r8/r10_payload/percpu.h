/* percpu.h — R10: Per-CPU variable support for SMP */

#ifndef PERCPU_H
#define PERCPU_H

#include "r10.h"

/* Maximum CPUs supported */
#define NR_CPUS          8

/* Per-CPU data structure */
struct percpu_data {
    /* CPU identification */
    u32 cpu_id;           // Logical CPU index (0..NR_CPUS-1)
    u64 mpidr;            // MPIDR value
    
    /* Stack pointers */
    u64 sp_el1;           // SP_EL1 for this CPU
    u64 sp_el0;           // SP_EL0 for this CPU
    u64 exc_stack_top;    // Exception stack top
    
    /* Scheduler */
    struct task_struct *current;   // Currently running task
    struct task_struct *idle;      // Idle task for this CPU
    
    /* Timer */
    u64 next_timer_deadline;       // Next timer expiration
    
    /* Interrupts */
    u32 irq_count;                 // IRQs handled on this CPU
    u32 ipi_count;                 // IPIs received
    
    /* Preemption */
    int preempt_count;             // Preemption disable count
    int preempt_need_resched;      // Need reschedule flag
    
    /* Locks */
    int lock_depth;                // Lock recursion depth
    
    /* Cache */
    char cache_line_pad[64];       // Avoid false sharing
};

/* Per-CPU array */
extern struct percpu_data percpu_data_array[NR_CPUS];

/* Get current CPU's per-CPU data */
static inline struct percpu_data *this_cpu_ptr(void)
{
    u32 cpu = get_current_cpu();
    return &percpu_data_array[cpu];
}

/* Get per-CPU data for specific CPU */
static inline struct percpu_data *per_cpu_ptr(int cpu)
{
    if (cpu >= NR_CPUS) return NULL;
    return &percpu_data_array[cpu];
}

/* Per-CPU variable macros */
#define DEFINE_PER_CPU(type, name) \
    __attribute__((section(".data.percpu"))) \
    type percpu_##name[NR_CPUS]

#define DECLARE_PER_CPU(type, name) \
    extern type percpu_##name[NR_CPUS]

#define get_cpu_var(var) \
    (percpu_##var[get_current_cpu()])

#define this_cpu_ptr(var) \
    (&percpu_##var[get_current_cpu()])

#define per_cpu_ptr(var, cpu) \
    (&percpu_##var[cpu])

/* Per-CPU operations */
static inline u64 get_current_mpidr(void)
{
    return mrs_mpidr_el1();
}

/* CPU topology helpers */
static inline int cpu_to_cluster(u32 cpu)
{
    if (cpu < 4) return 0;      // A55 cluster
    else if (cpu < 7) return 1; // A78 cluster
    else return 2;               // X1 cluster
}

static inline const char *cpu_type_name(u32 cpu)
{
    if (cpu < 4) return "A55";
    else if (cpu < 7) return "A78";
    else return "X1";
}

/* Per-CPU initialization */
void percpu_init_early(void);
void percpu_init_cpu(u32 cpu_id, u64 mpidr, u64 sp_el1, u64 exc_stack_top);
void percpu_init_late(void);

/* SMP boot */
int smp_init(void);
int smp_bringup_cpus(void);
void secondary_cpu_entry(void);

/* IPI (Inter-Processor Interrupt) */
#define IPI_RESCHEDULE    0
#define IPI_CALL_FUNC     1
#define IPI_CPU_STOP      2
#define IPI_TIMER         3
#define IPI_MAX           4

void ipi_send(u32 target_cpu, u32 ipi_type);
void ipi_send_mask(u32 cpu_mask, u32 ipi_type);
void ipi_send_all_but_self(u32 ipi_type);
void ipi_handle(u32 ipi_type);

/* Cross-CPU function call */
typedef void (*smp_func_t)(void *arg);

struct smp_call_data {
    smp_func_t func;
    void *arg;
    volatile int done;
};

void smp_call_function_single(int cpu, smp_func_t func, void *arg, int wait);
void smp_call_function_many(const u32 *cpu_mask, smp_func_t func, void *arg, int wait);
void smp_call_function_all(smp_func_t func, void *arg, int wait);

#endif /* PERCPU_H */