/* S21R10 v1 wire format inspector. No copying, MMIO or handoff. */
#ifndef S21_PAYLOAD_H
#define S21_PAYLOAD_H
#include <stddef.h>
#include <stdint.h>
#define PAYLOAD_HEADER_SIZE 680U
#define PAYLOAD_SEGMENT_SIZE 32U
#define PAYLOAD_MAX_SEGMENTS 32U
#define PAYLOAD_MAX_SIZE (64U * 1024U * 1024U)
struct payload_segment {
    uint64_t address, memory_size, file_offset, file_size;
};
struct payload_plan {
    uint64_t base, entry, memory_size, kernel_end, dtb_address, dtb_offset, dtb_size;
    uint32_t count;
    struct payload_segment segments[PAYLOAD_MAX_SEGMENTS];
};
/* source_address is where the complete container would reside physically.
 * Call in one thread before IRQs/SMP (the FDT parser uses static workspace).
 * Failure invalidates plan. Success is structural, not RAM/EL authorization. */
int payload_validate(const void *data, size_t size, uint64_t source_address,
                     struct payload_plan *plan);
#endif
