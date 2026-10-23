/* Bounded UEFI memory-map checks, shared by the EFI application and host tests. */
#ifndef S21_EFI_MEMORY_H
#define S21_EFI_MEMORY_H
#include <stdint.h>
#include <stddef.h>
#define S21_MAP_CAPACITY 65536U
#define S21_MAP_MAX_DESCRIPTORS 1024U
#define S21_MEMORY_PAGE UINT64_C(4096)
#define S21_MEMORY_ALIGNMENT UINT64_C(0x2000000)
struct s21_memory_map {
    const uint8_t *data;
    uint64_t size, stride;
    uint32_t version;
};
struct s21_memory_region {
    uint64_t base, size, attribute;
    uint32_t type;
};
int s21_memory_valid(const struct s21_memory_map *);
int s21_memory_region(const struct s21_memory_map *, uint64_t index, struct s21_memory_region *);
/* These two operations require a map that passed s21_memory_valid. */
int s21_memory_covers(const struct s21_memory_map *, uint64_t base, uint64_t size, uint32_t type);
int s21_memory_largest(const struct s21_memory_map *, uint64_t limit, uint64_t *base, uint64_t *size);
#endif
