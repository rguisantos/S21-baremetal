#ifndef S21_EFI_VIDEO_H
#define S21_EFI_VIDEO_H
#include <stdint.h>
/* Explicit laboratory ABI: QEMU XR24, 1125x2436, graphics mode. */
int s21_video_geometry(uint64_t base, uint64_t display, uint64_t stride,
                       uint64_t width, uint64_t height, uint64_t depth,
                       uint64_t *allocation_size);
#endif
