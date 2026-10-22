#!/usr/bin/env python3
"""Model the HZC2 LK memory-node callbacks for a supplied raw FDT.

Read-only: does not invoke HVC, simulate allocation or validate free memory.
The host model requires explicit parent cells 2/1 and complete reg tuples;
these input guards must not be attributed to the decoded LK walker.
"""
import argparse
import hashlib
import json
import struct

from check_lk_v3_layout import read_input, require
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_proton import fdt_nodes

MAX_FDT = 2 * 1024 * 1024


def model(data):
    require(len(data) <= MAX_FDT, 'FDT exceeds 2 MiB limit')
    nodes = fdt_nodes(data)
    submitted, missing_reg = [], []
    for path, props in nodes.items():
        if not path.rsplit('/', 1)[-1].startswith('memory'):
            continue
        if 'reg' not in props:
            missing_reg.append(path)
            continue
        parent = path.rsplit('/', 1)[0] or '/'
        cells = nodes[parent]
        require(cells.get('#address-cells') == struct.pack('>I', 2)
                and cells.get('#size-cells') == struct.pack('>I', 1),
                path + ': host model requires explicit parent cells 2/1')
        reg = props['reg']
        require(len(reg) >= 12 and len(reg) % 12 == 0,
                path + ': reg must contain complete 12-byte tuples')
        base, size = struct.unpack_from('>QI', reg)
        require(base + size < 1 << 64, path + ': range end overflows 64 bits')
        submitted.append(dict(
            node=path, base=hex(base), size=hex(size),
            end_exclusive=hex(base + size), reg_size=len(reg),
            ignored_reg_tuple_count=len(reg) // 12 - 1,
            uh_initial_nonzero_guard_passes=bool(base and size)))
    require(submitted, 'no memory-prefix node with reg in supplied FDT')
    return dict(
        mode='static_lk_uh_callback_model',
        input_fdt=dict(size=len(data), sha256=hashlib.sha256(data).hexdigest()),
        selection=dict(node_name_prefix='memory', traversal='FDT structure order',
                       device_type_checked=False, status_checked=False,
                       parent_ranges_translated=False, reg_tuples_read_per_node=1),
        submitted_ranges=submitted, skipped_nodes_without_reg=missing_reg,
        service_id='0x83000002', callback='0x209a38',
        walker_call='0xfb4f0', earlymem_writer_call='0xfb4fc',
        callback_return_checks_uh_success=False,
        runtime_observed=False, uh_acceptance_verified=False,
        allocation_simulated=False, memory_map_verified=False,
        free_memory_verified=False, is_final_fdt=False,
        limits=['Models callback arguments from the supplied FDT, not the device FDT',
                'Host guards require cells 2/1, complete tuples and no end overflow',
                'No uH range normalization, allocator, reservations or service execution'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', help='Exact decompressed HZC2 sboot.bin')
    parser.add_argument('fdt', help='Raw FDT, maximum 2 MiB; no DT table or LZ4')
    args = parser.parse_args()
    try:
        read_exact(args.sboot, *IMAGES['sboot'])
        result = model(read_input(args.fdt, MAX_FDT))
        result['firmware_sha256'] = IMAGES['sboot'][1]
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f'check_lk_uh_ranges: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
