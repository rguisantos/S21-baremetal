/* Initial R10 stage: parse the loader's FDT before touching GIC/timer.
 * Validation here cannot undo loader/BSS/stack writes made before C entry. */
#include "r10.h"
#include "fdt.h"

void *g_fdt;
struct r10_platform r10_platform;
volatile int r10_boot_status;
extern char __payload_start[], __payload_end[];

static void boot_stop(int error)
{
    r10_boot_status=error;
    uart_puts("R10 stopped: "); uart_puts(r10_fdt_error(error)); uart_putc('\n');
    park();
}
void r10_el1_entry(void *fdt)
{
    g_fdt=fdt;
    vbar_install();
    uart_init();
    if (!fdt || ((u64)fdt & 7)) boot_stop(R10_FDT_INVALID);
    /* The loader must supply readable memory for the complete DTB. The
     * parser enforces totalsize <= 2 MiB; unmapped reads remain fatal. */
    int rc=r10_fdt_parse(fdt,R10_FDT_MAX_SIZE,&r10_platform);
    if (rc) boot_stop(rc);
    rc=r10_fdt_check_boot(&r10_platform,(u64)fdt,(u64)__payload_start,
                           (u64)__payload_end,MRS(mpidr_el1));
    if (rc) boot_stop(rc);
    uart_puts("R10: FDT resources and payload range checked\n");
    if (gic_init_region(r10_platform.gic_dist.base,r10_platform.gic_redist.base,
                        r10_platform.gic_redist.size,r10_platform.redist_stride)) {
        r10_boot_status=-100; uart_puts("R10: GIC handoff rejected\n"); park();
    }
    if (timer_init()) {
        r10_boot_status=-101; uart_puts("R10: timer setup rejected\n"); park();
    }
    r10_boot_status=1;
    asm volatile("msr daifclr, #2\n\tisb" ::: "memory");
    for (;;) asm volatile("wfi" ::: "memory");
}
