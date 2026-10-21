#!/usr/bin/env python3
"""Read-only model of the traced HZC2 LK v3 copy branch, not a boot validator.

Requires raw Android boot/vendor_boot v3 with 4096-byte vendor pages and an
uncompressed little-endian ARM64 Image. Does not extract, repack or flash.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from inspect_sboot_hzc2 import inspect

PAGE = 4096
MAX_FILE = 64 * 1024 * 1024
BOOT_STAGING = 0x94000000
VENDOR_STAGING = 0x98000000
KERNEL_BASE = 0x80080000
RAMDISK_BASE = 0x84080000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def align(value):
    return (value+PAGE-1) & -PAGE


def read_input(path):
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_FILE+1)
    require(len(data) <= MAX_FILE, 'input exceeds 64 MiB limit')
    return data


def checked_slice(data, offset, size, label):
    require(0 <= offset <= len(data) and 0 <= size <= len(data)-offset,
            'truncated '+label)
    return memoryview(data)[offset:offset+size]


def model(boot, vendor, offset):
    require(isinstance(offset, int) and 0 <= offset <= 0x1f8000
            and offset % 0x8000 == 0, 'unsupported KASLR offset')
    require(len(boot) >= 1580 and boot[:8] == b'ANDROID!', 'invalid boot header')
    require(len(vendor) >= 2112 and vendor[:8] == b'VNDRBOOT', 'invalid vendor header')
    u32 = lambda data, pos: struct.unpack_from('<I', data, pos)[0]
    require(u32(boot, 40) == 3 and u32(boot, 20) == 1580,
            'requires boot v3 with header_size 1580')
    require(u32(vendor, 8) == 3 and u32(vendor, 2096) == 2112
            and u32(vendor, 12) == PAGE, 'requires vendor v3 with 4096-byte pages')
    kernel_size, boot_rd_size = struct.unpack_from('<II', boot, 8)
    vendor_rd_size = u32(vendor, 24)
    dtb_size = u32(vendor, 2100)
    kernel_off = align(u32(boot, 20))
    boot_rd_off = kernel_off+align(kernel_size)
    vendor_rd_off = align(u32(vendor, 2096))
    dtb_off = vendor_rd_off+align(vendor_rd_size)
    # Keep the model in the nonnegative SXTW range of the decoded LK branch.
    require(max(kernel_off, boot_rd_off, vendor_rd_off, dtb_off) < 1 << 31,
            'component offset exceeds modeled SXTW range')
    kernel = checked_slice(boot, kernel_off, kernel_size, 'kernel')
    checked_slice(boot, boot_rd_off, boot_rd_size, 'boot ramdisk')
    checked_slice(vendor, vendor_rd_off, vendor_rd_size, 'vendor ramdisk')
    checked_slice(vendor, dtb_off, dtb_size, 'vendor DTB region')
    require(len(kernel) >= 64 and bytes(kernel[56:60]) == b'ARMd',
            'requires uncompressed ARM64 Image')
    text_offset, image_size, flags = struct.unpack_from('<QQQ', kernel, 8)
    require(flags & 1 == 0, 'big-endian Image outside model')
    require(image_size >= kernel_size, 'Image memory extent smaller than kernel bytes')
    kernel_dest = KERNEL_BASE+offset
    ramdisk_end = RAMDISK_BASE+vendor_rd_size+boot_rd_size
    require(kernel_dest+image_size <= RAMDISK_BASE,
            'Image memory extent overlaps modeled ramdisk destination')
    require(ramdisk_end <= BOOT_STAGING,
            'ramdisk destination overlaps modeled boot staging')

    def copy(label, container, source, size, staging, destination, call):
        return dict(component=label, container=container, file_offset=hex(source),
                    size=size, staging_source=hex(staging+source),
                    destination=hex(destination), destination_end=hex(destination+size),
                    copy_call_file_offset=hex(call))

    return dict(
        mode='static_copy_model', runtime_observed=False, bootability_verified=False,
        kaslr_offset=hex(offset), modeled_kernel_entry=hex(kernel_dest),
        inputs={label: dict(size=len(data), sha256=hashlib.sha256(data).hexdigest())
                for label, data in (('boot', boot), ('vendor_boot', vendor))},
        copies=[copy('kernel', 'boot', kernel_off, kernel_size,
                     BOOT_STAGING, kernel_dest, 0x12e88c),
                copy('vendor_ramdisk', 'vendor_boot', vendor_rd_off, vendor_rd_size,
                     VENDOR_STAGING, RAMDISK_BASE, 0x12e7f8),
                copy('boot_ramdisk', 'boot', boot_rd_off, boot_rd_size,
                     BOOT_STAGING, RAMDISK_BASE+vendor_rd_size, 0x12e848)],
        image=dict(text_offset=hex(text_offset), declared_memory_size=image_size,
                   memory_end=hex(kernel_dest+image_size),
                   bytes_beyond_kernel_copy=image_size-kernel_size,
                   tail_zeroing_verified=False),
        vendor_dtb_region=dict(file_offset=hex(dtb_off), size=dtb_size,
                               staged_pointer=hex(VENDOR_STAGING+dtb_off),
                               registration_call_file_offset='0x12e850',
                               is_final_fdt=False),
        limits=['Models only the traced v3 dispatch with w0=6 and nonzero destinations',
                'Offset is a supplied scenario, not the observed SMC result',
                'No signature, AVB, later transformation or memory reservation validation',
                'No final EL/cache/FDT, clock or physical execution evidence'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path, help='exact raw HZC2 sboot.bin')
    parser.add_argument('boot', type=Path, help='raw boot.img, not LZ4')
    parser.add_argument('vendor_boot', type=Path, help='raw vendor_boot.img, not LZ4')
    parser.add_argument('--offset', required=True, type=lambda value: int(value, 0),
                        help='explicit modeled KASLR offset (0..0x1f8000, step 0x8000)')
    args = parser.parse_args()
    try:
        evidence = inspect(args.sboot)
        result = model(read_input(args.boot), read_input(args.vendor_boot), args.offset)
        result['firmware_sha256'] = evidence['sha256']
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(1, f'check_lk_v3_layout: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
