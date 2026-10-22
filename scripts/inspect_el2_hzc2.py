#!/usr/bin/env python3
"""Read-only evidence linking HZC2 LK, uH earlymem and Harx soc_info.

Only the exact received decompressed images are supported. No firmware code
or service is executed. Offsets are file offsets; see docs/el2-earlymem-hzc2.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from inspect_sboot_hzc2 import SIZE, SHA256, bl_target

IMAGES = {
    'sboot': (SIZE, SHA256),
    'uh': (93832, 'c2f7cd2708be9c8ea3a4ff22f8bbf224f726107633e5b70b09b8f352784fe407'),
    'harx': (3145728, '5564dcb1f59c4a66a4c69f7042fb30ee14c97a31ba5a77427c4a08612e1dc21e'),
}
UH_BASE = 0xc1400000


def read_exact(path, size, digest):
    """Bound the read before rejecting unsupported or damaged input."""
    with Path(path).open('rb') as stream:
        data = stream.read(size + 1)
    actual = hashlib.sha256(data).hexdigest()
    if len(data) != size or actual != digest:
        raise ValueError(f'unsupported image {Path(path).name}: '
                         f'{len(data)} bytes, sha256 {actual}')
    return data


def pointer_offset(pointer, base, length, width=4):
    """Translate only aligned pointers backed by bytes of this file, not BSS."""
    offset = pointer - base
    if width <= 0 or offset < 0 or offset % 4 or offset + width > length:
        raise ValueError('pointer outside aligned file-backed image')
    return offset


def words(data, offsets):
    return {hex(off): f'{struct.unpack_from("<I", data, off)[0]:08x}'
            for off in offsets}


def calls(data, offsets):
    return {hex(off): hex(bl_target(struct.unpack_from('<I', data, off)[0], off))
            for off in offsets}


def inspect(sboot_path, uh_path, harx_path):
    paths = dict(sboot=sboot_path, uh=uh_path, harx=harx_path)
    images = {name: read_exact(paths[name], *identity)
              for name, identity in IMAGES.items()}
    sboot, uh, harx = (images[name] for name in ('sboot', 'uh', 'harx'))
    table = 0x16000
    handler_pointer = struct.unpack_from('<Q', uh, table + 4 * 8)[0]
    handler = pointer_offset(handler_pointer, UH_BASE, len(uh))
    if handler != 0x1708:
        raise ValueError('unexpected app0 command4 handler')
    constructor_pointer = struct.unpack_from('<Q', uh, 0x12568)[0]
    constructor = pointer_offset(constructor_pointer, UH_BASE, len(uh))
    strings = {}
    for off in (0xd145, 0xd179, 0xd19c, 0xd1d1):
        strings[hex(off)] = harx[off:harx.index(0, off)].decode('ascii')
    return {
        'mode': 'static_read_only',
        'inputs': {name: dict(size=size, sha256=digest)
                   for name, (size, digest) in IMAGES.items()},
        'lk_earlymem': {
            'service_id': '0x83000004', 'x3': 0,
            'buffers_initially_zero': True,
            'calls': calls(sboot, (0x148b1c, 0x148b38, 0x209a5c)),
            'words': words(sboot, (0x148af4, 0x148af8, 0x148b00, 0x148b04,
                                   0x148b08, 0x148b14, 0x148b18, 0x148b20,
                                   0x209a28, 0x209a38, 0x209a3c, 0x209a40,
                                   0x209a44, 0x209a58)),
        },
        'uh_dispatch': {
            'registered_range': ['0x83000000', '0x8300ffff'],
            'dispatcher_file_offset': '0x6c3c', 'app': 0, 'command': 4,
            'assumed_pointer_base': hex(UH_BASE),
            'constructor_file_offset': hex(constructor),
            'table_file_offset': hex(table),
            'selected_pointer': hex(handler_pointer),
            'handler_file_offset': hex(handler),
            'words': words(uh, (0x7c9c, 0x7ca0, 0x7ca4, 0x7ca8, 0x7cac,
                                0x6c54, 0x6c60, 0x6c68, 0x6c6c,
                                0x6cb8, 0x6cc4, 0x6cd8, 0x6ce0, 0x6ce4,
                                0x33a0, 0x33b0, 0x33b4, 0x33bc,
                                0x33e0, 0x33ec, 0x33f0)),
        },
        'uh_earlymem': {
            'kind': 'stateful_allocation_path; not a pure query',
            'output_base_width_bits': 64, 'output_size_width_bits': 32,
            'range_list_state_image_relative': '0x171f8',
            'initialized_flag_image_relative': '0x17218',
            'calls': calls(uh, (0x16f8, 0x1774, 0x1914, 0x1924,
                                0x1cc4, 0x1e0c, 0x1e20)),
            'words': words(uh, (0x1728, 0x172c, 0x1750, 0x175c, 0x1764,
                                0x1934, 0x1938, 0x1a08, 0x1a0c,
                                0x1c10, 0x1c20, 0x1c24, 0x1c28,
                                0x1c98, 0x1cbc, 0x1de4, 0x1e04, 0x1e08,
                                0x2018, 0x2020, 0x2028, 0x2030)),
            'limit': 'Range-list contents, allocation result and runtime execution unobserved',
        },
        'harx_soc_info': {
            'service_id': '0x8200012e', 'expected_version': '0x66001000',
            'lk_legacy_service_id': '-0x12e',
            'legacy_translation_verified': False,
            'calls': calls(harx, (0x2308, 0x23dc)),
            'words': words(harx, (0x2298, 0x229c, 0x22a0, 0x22a8,
                                  0x22f0, 0x22f8, 0x2314, 0x2318,
                                  0x23c4, 0x23cc, 0x9aa4, 0x9aa8, 0x9aac)),
            'strings': strings,
            'ram_size_source_address': '0x02038848',
        },
        'runtime_values_observed': False, 'memory_map_verified': False,
        'is_final_fdt': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', help='Decompressed HZC2 sboot.bin')
    parser.add_argument('uh', help='Decompressed HZC2 uh.bin')
    parser.add_argument('harx', help='Decompressed HZC2 harx.bin')
    args = parser.parse_args()
    try:
        report = inspect(args.sboot, args.uh, args.harx)
    except (OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
