#!/usr/bin/env python3
"""Hash-bound HZC2 BL2 RAM-size producer and supplied geometry arithmetic.

Offsets are file offsets. Callback translation is nominal, not observed at
runtime. This reader never runs the DRAM initializer or accesses a device.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_sboot_hzc2 import bl_target

LEAF_START, LEAF_END = 0x2caec, 0x2cb9c
TABLE = 0x30080
SLOTS = 0x31978
NOMINAL_DELTA = 0x020ea000
MAX_GEOMETRY = 4096
WITNESSES = ((0x160bc, 0x160c0), (0x16128, 0x1612c),
             (0x17ff8, 0x18010), (0x1dc90, 0x1dc98), (0x1e848, 0x1e864),
             (0x1f9b8, 0x1f9e8), (0x1d830, 0x1d868),
             (0x2f130, 0x2f484), (LEAF_START, LEAF_END))


def normalize_slots(values):
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError('supply exactly four unsigned 64-bit geometry words')
    result = []
    for value in values:
        if type(value) is str:
            if len(value) > 32:
                raise ValueError('geometry integer string exceeds host limit')
            value = int(value, 0)
        if type(value) is not int or not 0 <= value < 1 << 64:
            raise ValueError('geometry words must be unsigned 64-bit integers')
        result.append(value)
    return tuple(result)


def load_geometry(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_GEOMETRY + 1)
    if len(raw) > MAX_GEOMETRY:
        raise ValueError('geometry JSON exceeds 4096-byte host limit')
    try:
        return normalize_slots(json.loads(raw))
    except RecursionError as error:
        raise ValueError('geometry JSON nesting exceeds parser limit') from error


def geometry(values, table):
    """Model only the 44-instruction leaf, including global slot-zero mode."""
    slots = normalize_slots(values)
    if len(table) != 7 or any(type(v) is not int or not 0 <= v <= 0xffff for v in table):
        raise ValueError('requires seven unsigned 16-bit density entries')
    count = 2 if (slots[0] >> 4) & 15 == 3 else 1
    contributions = []
    for slot in slots:
        terms = []
        for term in range(count):
            index = (slot >> (28 if term == 0 else 20)) & 15
            factor = (slot >> (24 if term == 0 else 16)) & 15
            amount = table[index] if (slot >> 8) & 255 and index <= 6 else 0
            terms.append(amount * (2 if factor == 1 else 1))
        contributions.append(terms)
    mib = sum(map(sum, contributions))
    return dict(mode='supplied_geometry_only', slots=[hex(v) for v in slots],
                terms_per_slot=count, contributions_mib=contributions,
                total_mib=mib, total_bytes=mib << 20,
                geometry_runtime_observed=False, memory_map_verified=False,
                free_memory_verified=False)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    table = struct.unpack_from('<7H', data, TABLE)
    callbacks = []
    for cell, role in ((0x31500, 'prepare_packed_geometry'),
                       (0x31558, 'validate_before_tail_call'),
                       (0x31358, 'size_leaf')):
        pointer = struct.unpack_from('<Q', data, cell)[0]
        callbacks.append(dict(cell_offset=hex(cell), raw_pointer=hex(pointer),
                              role_in_candidate_path=role,
                              nominal_target_offset=hex(pointer - NOMINAL_DELTA)))
    calls = {hex(off): hex(bl_target(struct.unpack_from('<I', data, off)[0], off))
             for off in (0x160bc, 0x16128, 0x18000, 0x1e85c)}
    return dict(
        mode='static_read_only',
        input=dict(size=IMAGES['sboot'][0], sha256=IMAGES['sboot'][1]),
        producer=dict(initializer_offset='0x17e14', calls=calls,
                      return_from='0x1dc90', store_offset='0x1800c',
                      destination='0x02038848', width_bits=64),
        selected_state_path=dict(state_offset='0x31688',
                                 helper_call='0x1e85c', result_store='0x1e860',
                                 result_cell='0x31940', return_load='0x1f9cc',
                                 mutable_state_and_intervening_calls_unresolved=True),
        callback_path=dict(helper_offset='0x1d830', cells=callbacks,
                           nominal_pointer_minus_file_delta=hex(NOMINAL_DELTA),
                           physical_placement_verified=False,
                           runtime_binding_verified=False,
                           failure_branch='0x1d850 -> 0x1fdb8'),
        leaf=dict(start=hex(LEAF_START), end_exclusive=hex(LEAF_END),
                  instruction_count=(LEAF_END-LEAF_START)//4,
                  sha256=hashlib.sha256(data[LEAF_START:LEAF_END]).hexdigest(),
                  density_table_offset=hex(TABLE), density_table_mib=list(table),
                  geometry_offsets=[hex(SLOTS + 8*i) for i in range(4)],
                  packed_geometry_candidate='0x2f130',
                  formula='four gated slots; 1 or 2 terms from slot0[7:4]; sum MiB << 20'),
        words={hex(off): f'{struct.unpack_from("<I", data, off)[0]:08x}'
               for start, end in WITNESSES for off in range(start, end, 4)},
        physical_execution_verified=False, ram_size_runtime_observed=False,
        is_final_fdt=False, memory_map_verified=False, free_memory_verified=False,
        limits=['Positive producer path, not a complete writer census',
                'Callback pointers use a nominal translation; live table binding unobserved',
                'DRAM initialization, callbacks and mutable state are not executed or fully modeled',
                'Packed geometry, reachability and actual 0x02038848 contents remain unknown',
                'LK may cap its cached total; total alone does not establish banks or reservations'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    parser.add_argument('--geometry', type=Path, help='JSON array of exactly four supplied u64 words')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot)
        if args.geometry is not None:
            result['supplied_geometry'] = geometry(load_geometry(args.geometry),
                                                   result['leaf']['density_table_mib'])
    except (OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
