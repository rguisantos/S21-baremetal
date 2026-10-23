/* Experimental QEMU consumer; no Samsung entry path is implemented here. */
#ifndef S21_EFI_RESOURCES_H
#define S21_EFI_RESOURCES_H
#include <stdint.h>
#include <stddef.h>
#define S21_XNU_VBASE UINT64_C(0xfffffff004000000)
#define S21_PAYLOAD_LIMIT (64U * 1024U * 1024U)
struct s21_resources {
    uint64_t io_base, io_size, dist, dist_size, redist, redist_size;
    uint64_t frequency, uart, uart_size;
    uint32_t mpidr, hvc;
};
#define S21_RESIDENT_BASE UINT64_C(0xfc000000)
#define S21_RESIDENT_OFFSET UINT64_C(0x8000000)
#define S21_RESIDENT_LIMIT UINT64_C(0xc0000000)
struct s21_resident { uint64_t base, size; };
int s21_resident_decode(const void *, uint32_t, struct s21_resident *);
int s21_resident_apfs(const void *, uint64_t);
#define S21_USERLAND_TAIL UINT64_C(0x40000000)
struct s21_profile { uint32_t id; uint64_t epoch; };
int s21_profile_decode(const void *, uint32_t, struct s21_profile *);
int s21_profile_cmdline(const struct s21_profile *, char *, uint32_t);
int s21_profile_headroom(const struct s21_profile *, uint64_t, uint64_t, uint64_t);
struct s21_payload {
    const uint8_t *kernel, *ramdisk, *resource;
    const char *cmdline;
    uint32_t kernel_size, ramdisk_size, resource_size;
    struct s21_resident resident;
    struct s21_profile profile;
};
int s21_resources_decode(const void *, uint32_t, struct s21_resources *);
int s21_resources_qemu(const struct s21_resources *, uint64_t frequency, uint64_t mpidr);
int s21_payload_decode(const void *, uint32_t available, struct s21_payload *);
int s21_layout_check(uint64_t base, uint64_t size, uint64_t kernel_lo, uint64_t kernel_hi,
                     uint64_t rd, uint64_t rd_size, uint64_t dt, uint64_t dt_size,
                     uint64_t ba, uint64_t top);
int s21_resident_layout(const struct s21_resident *, uint64_t base, uint64_t size,
                        uint64_t lo, uint64_t hi, uint64_t rd, uint64_t rn,
                        uint64_t dt, uint64_t dn, uint64_t ba, uint64_t top);
#endif
