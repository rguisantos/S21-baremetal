/* Bounded, allocation-free FDT subset for the initial single-CPU R10 stage. */
#ifndef R10_FDT_H
#define R10_FDT_H
#include <stddef.h>
#include <stdint.h>
#define R10_FDT_MAX_SIZE (2U * 1024U * 1024U)
#define R10_FDT_MAX_RAM 64
#define R10_FDT_MAX_RESERVED 128
#define R10_FDT_MAX_CPUS 32
struct r10_range { uint64_t base, size; };
struct r10_platform {
    uint32_t blob_size, ram_count, reserved_count, cpu_count;
    struct r10_range ram[R10_FDT_MAX_RAM], reserved[R10_FDT_MAX_RESERVED];
    uint64_t cpus[R10_FDT_MAX_CPUS];
    struct r10_range gic_dist, gic_redist;
    uint64_t redist_stride;
    uint32_t gic_phandle, timer_parent, timer_irq, timer_frequency;
    uint32_t have_gic, have_timer, unresolved_reserved;
    struct r10_range initrd;
};
enum {
    R10_FDT_OK = 0, R10_FDT_INVALID = -1, R10_FDT_LIMIT = -2,
    R10_FDT_UNSUPPORTED = -3, R10_FDT_NO_RAM = -4,
    R10_FDT_INCOMPLETE = -5, R10_FDT_CONFLICT = -6,
    R10_FDT_RESOURCES = -7
};
/* Call only before IRQs/SMP: parser uses one static bounded traversal stack.
 * available must describe readable input bytes; it is not inferred from DTB.
 * On failure, out is invalid and must not be used. No writes to input/MMIO. */
int r10_fdt_parse(const void *blob, size_t available, struct r10_platform *out);
int r10_fdt_range_usable(const struct r10_platform *p, uint64_t start, uint64_t size);
int r10_fdt_check_boot(const struct r10_platform *p, uint64_t fdt_address,
                       uint64_t payload_start, uint64_t payload_end, uint64_t mpidr);
const char *r10_fdt_error(int error);
#endif
