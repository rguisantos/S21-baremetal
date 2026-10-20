#ifndef FDT_H
#define FDT_H

#include <stdint.h>

/* Minimal FDT parsing for /chosen properties */

int fdt_check_header(uintptr_t dtb);
int fdt_check_compat(uintptr_t dtb, const char *compat);
int fdt_path_offset(uintptr_t dtb, const char *path);
int fdt_getprop_u64(uintptr_t dtb, int offset, const char *name, uint64_t *out);
int fdt_chosen_u64(uintptr_t dtb, const char *name, uint64_t *out);

#endif