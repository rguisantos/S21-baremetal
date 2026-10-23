#include "efi_video.h"
int s21_video_geometry(uint64_t base, uint64_t display, uint64_t stride,
                       uint64_t width, uint64_t height, uint64_t depth,
                       uint64_t *allocation_size)
{
    if (!allocation_size || !base || (base & 4095) || display != 1 ||
        width != 1125 || height != 2436 || depth != 32 || stride != width*4)
        return 0;
    uint64_t bytes = stride*height;
    uint64_t pages = (bytes+4095)&~UINT64_C(4095);
    if (pages > UINT64_MAX-base) return 0;
    *allocation_size = pages;
    return 1;
}
