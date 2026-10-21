/* Synthetic firmware: its ELF reserves 0x44000000..__loader_end. */
#include "../common/r8lib.h"
#include "../../shim/payload_stage.h"
extern unsigned char loader_payload[],loader_payload_end[];
extern unsigned char loader_firmware[],loader_firmware_end[];
extern unsigned char __loader_start[],__loader_end[];
extern void loader_enter(uint64_t entry,uint64_t fdt) __attribute__((noreturn));
volatile int loader_status;
volatile uint64_t loader_observed_el;
/* Second range is a fault-injection slot controlled only by the test harness. */
struct r10_range loader_protected[2]={{0,0},{0,16}};
static void say(const char *s) { while (*s) uart_putc(*s++); }
static void stop(int status)
{
    loader_status=status;
    say("EL2 LOADER REJECT\n");
    for (;;) asm volatile("wfe" ::: "memory");
}
static void synchronize_image(uint64_t base,uint64_t size)
{
    uint64_t ctr; asm volatile("mrs %0, ctr_el0":"=r"(ctr));
    uint64_t line=4ULL<<((ctr>>16)&15);
    for (uint64_t p=base&~(line-1);p<base+size;p+=line)
        asm volatile("dc cvac, %0"::"r"(p):"memory");
    asm volatile("dsb sy\n\tic iallu\n\tdsb sy\n\tisb":::"memory");
}
void loader_main(void)
{
    asm volatile("mrs %0, CurrentEL":"=r"(loader_observed_el));
    uart_init(); say("EL2 LOADER START\n");
    struct payload_plan plan;
    if (payload_validate(loader_payload,(size_t)(loader_payload_end-loader_payload),
                         (uint64_t)loader_payload,&plan)) stop(PAYLOAD_BAD_WIRE);
    loader_protected[0]=(struct r10_range){(uint64_t)__loader_start,
                                         (uint64_t)(__loader_end-__loader_start)};
    struct payload_environment env={loader_firmware,(size_t)(loader_firmware_end-loader_firmware),
        (uint64_t)loader_firmware,(uint64_t)loader_payload,MRS(mpidr_el1),
        loader_protected,2,(void *)plan.base,(size_t)plan.memory_size};
    int rc=payload_stage(loader_payload,(size_t)(loader_payload_end-loader_payload),&env,&plan);
    if (rc) stop(rc);
    synchronize_image(plan.base,plan.memory_size);
    /* This test firmware owns the QEMU distributor and assigns NS timer PPI.
     * Production R10 only reads the inherited distributor, as on hardware. */
    mmio_write32(0x08000000,0x12);
    asm volatile("dsb sy\n\tisb":::"memory");
    mmio_write32(0x080a0000+0x10000+0x80,1U<<30);
    loader_status=2;
    say("EL2 LOADER STAGED\n");
    loader_enter(plan.entry,plan.dtb_address);
}
