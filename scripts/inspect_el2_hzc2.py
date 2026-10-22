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


def instruction(data, offset):
    if offset < 0 or offset % 4 or offset + 4 > len(data):
        raise ValueError('instruction outside aligned image bytes')
    return struct.unpack_from('<I', data, offset)[0]


def jump_table_target(data, table, index, base):
    entry = table + index * 2
    if index < 0 or entry < 0 or entry + 2 > len(data):
        raise ValueError('jump table entry outside image')
    displacement = struct.unpack_from('<h', data, entry)[0]
    target = base + displacement * 4
    instruction(data, target)
    return target


def constant_return(data, start, exit_offset):
    """Decode only MOVZ X28, optional MOVK X28, then B to the known exit.

    This bounded leaf decoder deliberately rejects loads, calls, conditional
    paths, other registers and other A64 immediate encodings.
    """
    instruction(data, exit_offset)
    value = None
    for offset in range(start, start + 6 * 4, 4):
        word = instruction(data, offset)
        if word >> 26 == 0b000101:
            displacement = word & 0x3ffffff
            if displacement & 0x2000000:
                displacement -= 0x4000000
            if value is None or offset + displacement * 4 != exit_offset:
                raise ValueError('constant path does not reach expected result store')
            return dict(value=value, branch_offset=offset)
        opcode = word & 0xff800000
        if word & 31 != 28 or opcode not in (0xd2800000, 0xf2800000):
            raise ValueError('unsupported instruction in constant return path')
        shift = ((word >> 21) & 3) * 16
        immediate = ((word >> 5) & 0xffff) << shift
        if opcode == 0xd2800000:
            if value is not None:
                raise ValueError('expected only one initial MOVZ')
            value = immediate
        else:
            if value is None:
                raise ValueError('MOVK requires an initial MOVZ')
            value = (value & ~(0xffff << shift)) | immediate
    raise ValueError('constant return path exceeds instruction limit')


def harx_memory_info(data):
    results = {}
    for query in (0, 1, 2, 3, 4):
        target = jump_table_target(data, 0xc9c0, query, 0x1b0c)
        result = constant_return(data, target, 0x2124)
        results[str(query)] = dict(target=hex(target), value=hex(result['value']),
                                   branch_offset=hex(result['branch_offset']))
    if instruction(data, 0x2128) != 0xf900001c:  # STR X28, [X0]
        raise ValueError('unexpected result context store')
    base, size = (int(results[str(query)]['value'], 16) for query in (1, 2))
    log_base, log_size = (int(results[str(query)]['value'], 16) for query in (3, 4))
    return dict(
        service_id='0xc6000020', table_offset='0xc9c0', queries=results,
        result_store='0x2128: STR X28, [X0]',
        conditional_interval=dict(base=hex(base), size=hex(size),
                                  end_exclusive=hex(base + size)),
        ram_log_interval=dict(base=hex(log_base), size=hex(log_size),
                              end_exclusive=hex(log_base + log_size)),
        runtime_execution_verified=False,
        limit='Constant returns in this handler; LK feature flag and actual HVC outcome unobserved')


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
    range_pointer = struct.unpack_from('<Q', uh, table + 2 * 8)[0]
    range_handler = pointer_offset(range_pointer, UH_BASE, len(uh))
    strings = {}
    for off in (0xc169, 0xc19e, 0xc1be, 0xd145, 0xd179, 0xd19c, 0xd1d1):
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
        'lk_range_registration': {
            'node_name_prefix': 'memory', 'property': 'reg',
            'walker_file_offset': '0x148c38', 'callback_file_offset': '0x209a38',
            'service_id': '0x83000002',
            'reg_bytes_read_per_node': 12, 'callback_checks_uh_return': False,
            'calls': calls(sboot, (0xfb4f0, 0xfb4fc, 0x148c6c, 0x148cbc,
                                   0x148cc8, 0x148cd8, 0x148cf0, 0x148d08,
                                   0x148d3c)),
            'words': words(sboot, (0xfb4e0, 0xfb4e4, 0xfb4e8, 0xfb4ec,
                                   0x148c50, 0x148c84, 0x148cdc, 0x148d04,
                                   0x148d0c, 0x148d10, 0x148d18, 0x148d20,
                                   0x148d24, 0x148d2c, 0x148d30, 0x209a60)),
            'limit': 'Callback argument derivation only; actual dynamic FDT not acquired',
        },
        'uh_dispatch': {
            'registered_range': ['0x83000000', '0x8300ffff'],
            'dispatcher_file_offset': '0x6c3c', 'app': 0, 'command': 4,
            'assumed_pointer_base': hex(UH_BASE),
            'constructor_file_offset': hex(constructor),
            'table_file_offset': hex(table),
            'selected_pointer': hex(handler_pointer),
            'handler_file_offset': hex(handler),
            'range_handler_pointer': hex(range_pointer),
            'range_handler_file_offset': hex(range_handler),
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
        'harx_memory_info': harx_memory_info(harx),
        'lk_harx_gap': {
            'feature_flag_image_relative': '0x487c90',
            'flag_store_before_crash_callback_hvc': '0xf90d8',
            'flag_does_not_prove_callback_hvc_success': True,
            'calls': calls(sboot, (0xf90dc, 0xfaee8, 0xf9368, 0xf9394,
                                   0xf93bc, 0xfaf34, 0xfaf50)),
            'words': words(sboot, (0xf90a4, 0xf90c4, 0xf90d8, 0xf9334,
                                   0xf9340, 0xf9348, 0xf934c,
                                   0xf936c, 0xf9370, 0xf9374, 0xf9378,
                                   0xf93cc, 0xf93d0, 0xf93d4,
                                   0xf93e8, 0xf93ec, 0xf93f0,
                                   0xfaeec, 0xfaef0, 0xfaf38, 0xfaf3c,
                                   0xfaf40, 0xfaf44, 0xfaf48, 0xfaf4c,
                                   0xfaf54, 0xfaf58)),
            'harx_words': words(harx, (0x156c, 0x15f0, 0x15f4, 0x15f8,
                                       0x15fc, 0x1aec, 0x1afc, 0x1b00,
                                       0x1b04, 0x1b08, 0x1b0c, 0x1b14,
                                       0x2114, 0x2118, 0x2124, 0x2128)),
            'limit': 'Conditional omission from RAM-node construction, not a complete reservation map',
        },
        'harx_log_reader': {
            'service_id': '0xc6000043', 'requested_page_size': '0x1000',
            'read_cursor_image_relative': '0x10000',
            'read_cursor_can_advance': True,
            'words': words(harx, (0x1cf4, 0x1cfc, 0x1d18, 0x1d1c,
                                  0x1da8, 0x1dac, 0xb98, 0xba0, 0xba4,
                                  0xbd8, 0xc30, 0xc3c, 0xc40, 0xc44,
                                  0xc48, 0xc50, 0xc64, 0xc6c)),
            'limit': 'Static getter/reset paths; no service executed or device attribute read',
        },
        'harx_soc_info': {
            'service_id': '0x8200012e', 'expected_version': '0x66001000',
            'lk_legacy_service_id': '-0x12e',
            'legacy_translation_verified': False,
            'calls': calls(harx, (0x3a0, 0x3b4, 0x3c0, 0x2308, 0x23dc)),
            'printed_field_indices': {
                'secure_dram_base': dict(index=2, call='0x3a0', label='0xc19e'),
                'reserved_dram_size': dict(index=1, call='0x3c0', label='0xc169'),
                'secure_dram_size': dict(index=20, call='0x3b4', label='0xc1be'),
            },
            'words': words(harx, (0x2298, 0x229c, 0x22a0, 0x22a8,
                                  0x22f0, 0x22f8, 0x2314, 0x2318,
                                  0x23c4, 0x23cc, 0x9aa4, 0x9aa8, 0x9aac,
                                  0x390, 0x3a8, 0x3bc, 0x460, 0x470, 0x480)),
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
