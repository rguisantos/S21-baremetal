/* Copy stage for an explicitly owned memory window. Not wired to shim entry. */
#ifndef PAYLOAD_STAGE_H
#define PAYLOAD_STAGE_H
#include "payload.h"
#include "../r8/r10_payload/fdt.h"
struct payload_environment {
    const void *firmware_fdt;
    size_t firmware_size;
    uint64_t firmware_address, source_address, mpidr;
    const struct r10_range *protected_ranges;
    size_t protected_count;
    void *destination; /* Mapping of the physical window starting at plan.base. */
    size_t destination_size;
};
enum { PAYLOAD_BAD_WIRE=-1, PAYLOAD_BAD_FDT=-2, PAYLOAD_BAD_RAM=-3,
       PAYLOAD_PROTECTED=-4, PAYLOAD_BAD_DESTINATION=-5 };
/* Single-threaded, before IRQs/SMP. Firmware FDT and protected ranges must be
 * supplied independently by a trusted caller, not accepted from the payload.
 * Provide 1..8 complete exclusion ranges for live loader/platform memory.
 * Caller owns the destination mapping and entire declared physical window.
 * Caller keeps context/workspace separate from the destination and input.
 * All checks precede copy/zero writes there. Cache maintenance/EL/handoff are caller
 * responsibilities. Failure invalidates a nonaliased plan; aliased output
 * arguments are rejected untouched. Success does not jump. */
int payload_stage(const void *data,size_t size,const struct payload_environment *env,
                  struct payload_plan *plan);
#endif
