#!/usr/bin/env python3
"""Read-only source/config/DT evidence for the HZC2 Harx sysfs log getter.

Requires the exact received source archive and raw stock boot/vendor_boot.
Does not execute firmware, load modules, extract archive paths or read a phone.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import tarfile
import zlib

from check_lk_dtb_selection import entry_blob, parse_table
from check_lk_v3_layout import align, checked_slice, require
from inspect_el2_hzc2 import read_exact
from inspect_proton import fdt_nodes
from inspect_uart_reference import ARCHIVE_SHA

BOOT_SHA = '28818995d6c3060df19602a0104c2c7dac9861f31f2620f9dab8466e6cdf51a1'
VENDOR_SHA = 'f5b18d6b18230702cef98d80f4543a0f452cddb5829310b3acdafd6d600a60b5'
MAX_CONFIG = 2 * 1024 * 1024
FILES = {
    'drivers/soc/samsung/exynos-el2.c': '5052aa5efdbb096e3c7b32af4a5a00ab2999c1c65be1a193ccf2b12611cbe0aa',
    'include/soc/samsung/exynos-el2.h': 'a86099ef9c140a0ed75bb1ff60d1e8c9a1e4d5e6158bd35ded21621bfae40e96',
    'include/soc/samsung/exynos-hvc.h': '79350d9a1e3c6f87572ef19a25d5fd422c4fe6aab690f8b07678d34893ee43e6',
    'drivers/soc/samsung/Makefile': 'a9799d6c17384078ec03fd6e2626259f24ddb1d44a09e8d0913c5721b64c9caa',
    'drivers/soc/samsung/Kconfig': 'c80d8f1af6b604c4615927dd37827be00e7486c014b11c53c2c5b23e8bc6d103',
    'arch/arm64/configs/exynos2100-p3sxxx_defconfig': 'e0d7cfe4c8fceb31a5e44a9ba916c00338834a58011a44494e15120efe76c4fd',
}


def embedded_config(image):
    start, end = image.find(b'IKCFG_ST'), image.find(b'IKCFG_ED')
    require(image.count(b'IKCFG_ST') == image.count(b'IKCFG_ED') == 1
            and start + 8 < end, 'missing, duplicate or unordered IKCONFIG markers')
    decoder = zlib.decompressobj(31)
    try:
        raw = decoder.decompress(image[start + 8:end], MAX_CONFIG + 1)
    except zlib.error as error:
        raise ValueError('invalid IKCONFIG gzip') from error
    require(len(raw) <= MAX_CONFIG and decoder.eof and not decoder.unused_data
            and not decoder.unconsumed_tail, 'truncated, trailing or oversized IKCONFIG')
    entries = {}
    for line in raw.decode('ascii').splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
        elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
            key, value = line[2:-11], 'n'
        else:
            continue
        require(key not in entries, 'duplicate config assignment')
        entries[key] = value
    return dict(start_marker_image_offset=hex(start), size=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(), entries=entries)


def sources(path):
    found = {}
    with Path(path).open('rb') as source:
        require(hashlib.file_digest(source, 'sha256').hexdigest() == ARCHIVE_SHA,
                'requires the exact received Kernel.tar.gz')
        source.seek(0)
        with tarfile.open(fileobj=source, mode='r|gz') as archive:
            for member in archive:
                if member.name not in FILES:
                    continue
                require(member.name not in found and member.isfile()
                        and member.size <= 512 * 1024, 'unexpected source member')
                data = archive.extractfile(member).read()
                require(hashlib.sha256(data).hexdigest() == FILES[member.name],
                        'source hash mismatch: ' + member.name)
                found[member.name] = data.decode('utf-8')
    require(set(found) == set(FILES), 'source members missing')
    return found


def inspect(kernel_tar, boot_path, vendor_path):
    source = sources(kernel_tar)
    boot = read_exact(boot_path, 64 * 1024 * 1024, BOOT_SHA)
    vendor = read_exact(vendor_path, 64 * 1024 * 1024, VENDOR_SHA)
    kernel_size = struct.unpack_from('<I', boot, 8)[0]
    image = bytes(checked_slice(boot, 4096, kernel_size, 'stock Image'))
    require(image[56:60] == b'ARMd', 'stock Image header missing')
    config = embedded_config(image)
    flags = {key: config['entries'].get(key) for key in
             ('CONFIG_EXYNOS_EL2', 'CONFIG_ARM64_4K_PAGES', 'CONFIG_IKCONFIG')}
    require(flags == dict(CONFIG_EXYNOS_EL2='m', CONFIG_ARM64_4K_PAGES='y',
                          CONFIG_IKCONFIG='y'), 'unexpected stock kernel profile')
    del config['entries']
    config['flags'] = flags
    rd_size = struct.unpack_from('<I', vendor, 24)[0]
    dt_size = struct.unpack_from('<I', vendor, 2100)[0]
    region = bytes(checked_slice(vendor, 4096 + align(rd_size), dt_size, 'vendor DT region'))
    base = entry_blob(region, parse_table(region)['entries'][0])
    nodes = fdt_nodes(base)
    candidates = []
    for path, props in nodes.items():
        if b'samsung,exynos-el2-dynamic-lv3' in props.get('compatible', b'').split(b'\0'):
            status = props['status'].rstrip(b'\0').decode('ascii') if 'status' in props else None
            candidates.append(dict(dt_path=path, declared_status=status,
                                   base_tree_only=True,
                                   sysfs_path_candidate='/sys/devices/platform' + path + '/exynos_el2_log'))
    require(candidates, 'EL2 driver node missing in stock base DT')
    driver = source['drivers/soc/samsung/exynos-el2.c']
    markers = ('static ssize_t exynos_el2_log_print(',
               'static ssize_t exynos_el2_log_clear(',
               'static DEVICE_ATTR(exynos_el2_log, 0644,',
               '&dev_attr_exynos_el2_log);')
    lines = {marker: driver.count('\n', 0, driver.index(marker)) + 1 for marker in markers}
    return dict(
        mode='static_harx_log_evidence',
        inputs=dict(kernel_archive_sha256=ARCHIVE_SHA, boot_sha256=BOOT_SHA,
                    vendor_boot_sha256=VENDOR_SHA),
        source_sha256=FILES, source_lines=lines, stock_kernel_config=config,
        base_fdt=dict(size=len(base), sha256=hashlib.sha256(base).hexdigest()),
        driver_nodes=candidates, source_attribute_mode='0644',
        read_service='0xc6000043', read_service_arguments=['page_physical_address', 0, 0, 0],
        read_side_effect='Harx log read cursor can advance; no reset argument',
        store_effect='Separate store callback requests reader reset; collector must never write it',
        driver_loaded_observed=False, device_access_observed=False,
        memory_map_verified=False,
        limits=['Module configuration and base DT do not prove successful driver probe',
                'SELinux and actual attribute permissions have not been observed',
                'One bounded page may omit boot messages or reflect an advanced/wrapped cursor'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel_tar')
    parser.add_argument('boot')
    parser.add_argument('vendor_boot')
    args = parser.parse_args()
    try:
        report = inspect(args.kernel_tar, args.boot, args.vendor_boot)
    except (OSError, ValueError, struct.error, tarfile.TarError) as error:
        parser.exit(1, f'check_harx_log_evidence: {error}\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
