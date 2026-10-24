#!/usr/bin/env python3
"""HZC2 conditional writes to the geometry query's five-base table.

Only constructor arithmetic is interpreted on the host. No register is read,
callback resolved at runtime or firmware store executed. Scenarios require an
explicit register word and keep the prior-table assumption visible.
"""
import argparse
import hashlib
import json
import struct
import sys

from inspect_bl2_geometry_query import query_plan, table5
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_epbl_preparation import adrp_ldr_pointer, uint
from inspect_lk_final_edges import signed
from inspect_monitor_preparation import word
from inspect_sboot_hzc2 import bl_target

TABLE = 0x30f98
WRITE_START, WRITE_END = 0x2d288, 0x2d2c4
RANGES = ((0x1dee4, 0x1dee8), (0x1e0dc, 0x1e0e8),
          (0x2eff0, 0x2f00c), (0x2d270, 0x2d2cc), (0x2e3d0, 0x2e3e4))


def page_address(value, pc):
    if value & 0x9f000000 != 0x90000000 or value & 31 == 31:
        raise ValueError('expected ADRP X register')
    return (pc & ~4095) + (signed(((value >> 29) & 3) | (((value >> 5) & 0x7ffff) << 2), 21) << 12)


def constructor(data, start=WRITE_START, end=WRITE_END):
    """Only ADRP, MOVZ/MOVK X, ADD X immediate (including LSL 12), STR X.

    Unknown registers cannot be read. The only permitted stores are the five
    aligned u64 cells. No memory read, call, branch or implicit stack model.
    """
    if start % 4 or end % 4 or not 0 <= start < end <= len(data) or end-start > 64:
        raise ValueError('constructor outside bounded aligned bytes')
    registers, stores = {}, []

    def get(index):
        if index == 31 or index not in registers:
            raise ValueError('unknown constructor register')
        return registers[index]

    for pc in range(start, end, 4):
        w = word(data, pc)
        rd = w & 31
        if w & 0x9f000000 == 0x90000000:
            value = page_address(w, pc)
        elif w & 0xff800000 in (0xd2800000, 0xf2800000):
            shift = ((w >> 21) & 3)*16
            value = ((w >> 5) & 65535) << shift
            if w & 0xff800000 == 0xf2800000:
                value |= get(rd) & ~(65535 << shift)
        elif w & 0xff800000 == 0x91000000:
            value = get((w >> 5) & 31) + (((w >> 10) & 4095) << (12 if w & (1 << 22) else 0))
        elif w & 0xffc00000 == 0xf9000000:
            destination = (get((w >> 5) & 31) + ((w >> 10) & 4095)*8) & ((1 << 64)-1)
            if destination not in range(TABLE, TABLE+40, 8):
                raise ValueError('store outside the five-cell query table')
            stores.append(dict(pc=hex(pc), destination=hex(destination), value=hex(get(rd)), width_bits=64))
            continue
        else:
            raise ValueError(f'unsupported constructor instruction at {pc:#x}')
        if rd == 31:
            raise ValueError('unsupported constructor SP/ZR destination')
        registers[rd] = value & ((1 << 64)-1)
    if sorted(int(s['destination'], 16) for s in stores) != list(range(TABLE, TABLE+40, 8)):
        raise ValueError('constructor must write each of the five cells exactly once')
    return stores


def scenario(prior_bases, stores, register_word):
    register_word = uint(register_word, 32)
    if not isinstance(prior_bases, (list, tuple)) or len(prior_bases) != 5:
        raise ValueError('requires five explicit prior table entries')
    prior = [uint(v, 64) for v in prior_bases]
    nibble = (register_word >> 20) & 15
    after = prior.copy()
    if nibble == 1:
        for store in stores:
            after[(int(store['destination'], 16)-TABLE)//8] = int(store['value'], 16)
    return dict(mode='supplied_register_and_prior_table_only', register_word=hex(register_word),
                nibble_20_23=nibble, selected_body_writes=nibble == 1,
                before=[hex(v) for v in prior], after=[hex(v) for v in after],
                state_assumption='explicit prior table; only the selected writer is applied',
                register_runtime_observed=False, table_runtime_observed=False,
                firmware_executed=False, memory_map_verified=False)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    expected = {0x1e0dc: 0x91102280, 0x1e0e0: 0xf9401000, 0x1e0e4: 0xd63f0000,
                0x2d274: 0xf81f0ffe, 0x2d27c: 0xd63f0000,
                0x2d280: 0x7100041f, 0x2d284: 0x54000201,
                0x2d2c4: 0xf84107fe, 0x2d2c8: 0xd65f03c0,
                0x2e3d0: 0xd2800200, 0x2e3d4: 0xf2a20000, 0x2e3d8: 0xb9400000,
                0x2e3dc: 0xd3545c00, 0x2e3e0: 0xd65f03c0}
    if any(word(data, pc) != w for pc, w in expected.items()):
        raise ValueError('unsupported caller/gate/getter witness')
    init_cell = page_address(word(data, 0x1dee4), 0x1dee4) + 0x408 + 32
    getter_cell, getter_pointer = adrp_ldr_pointer(data, 0x2d270, 0x2d278)
    init_pointer = struct.unpack_from('<Q', data, init_cell)[0]
    if init_pointer-NOMINAL_DELTA != 0x2eff0 or getter_pointer-NOMINAL_DELTA != 0x2e3d0:
        raise ValueError('nominal initializer/getter pointers differ')
    if bl_target(word(data, 0x2effc), 0x2effc) != 0x2d270:
        raise ValueError('initializer does not call the selected writer')
    stores = constructor(data)
    return dict(
        mode='static_query_base_rewrite', input=dict(size=IMAGES['sboot'][0], sha256=IMAGES['sboot'][1]),
        nominal_callbacks=dict(delta=hex(NOMINAL_DELTA),
            bindings=[dict(cell=hex(init_cell), pointer=hex(init_pointer), target='0x2eff0'),
                      dict(cell=hex(getter_cell), pointer=hex(getter_pointer), target='0x2e3d0')],
            runtime_binding_verified=False,
            caller_base_assumption='X20 retains the 0x31000 page from 0x1dee4 across intervening calls'),
        calls=dict(initializer_indirect='0x1e0e4', writer_direct='0x2effc', writer='0x2d270',
                   later_geometry_call='0x1e85c', reachability_observed=False),
        gate=dict(getter='0x2e3d0', register_address='0x10000010', read_width_bits=32,
                  field_lsb=20, field_width=4, rewrite_when_equal=1,
                  nonmatching_action='no table writes; retain prior contents, not restore file values',
                  register_runtime_observed=False),
        table=dict(offset=hex(TABLE), initial_file_bases=[hex(v) for v in table5(data, TABLE)],
                   conditional_stores=stores, initial_values_verified_at_runtime=False,
                   code_callback_tables_modified_by_this_body=False,
                   preparation_base_table_modified_by_this_body=False),
        constructor_sha256=hashlib.sha256(data[WRITE_START:WRITE_END]).hexdigest(),
        words={hex(pc): f'{word(data, pc):08x}' for a, b in RANGES for pc in range(a, b, 4)},
        firmware_executed=False, complete_writer_census=False, memory_map_verified=False,
        limits=['Positive conditional table writer, not all writers or a measured initialization sequence',
                'Callback placement and preservation of X20 across calls remain nominal assumptions',
                'The register address/field is decoded; no silicon identity or live nibble inferred',
                'Skip retains prior state; a supplied scenario must name its prior-table assumption',
                'No MMIO, callback, hardware response or FDT execution; no RAM capacity inferred'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    parser.add_argument('--register-word', type=lambda v: int(v, 0))
    for name in ('slot', 'term', 'selector'):
        parser.add_argument('--'+name, type=lambda v: int(v, 0))
    args = parser.parse_args()
    plan_args = (args.slot, args.term, args.selector)
    if any(v is not None for v in plan_args) and (args.register_word is None or any(v is None for v in plan_args)):
        parser.error('a plan requires --register-word, --slot, --term and --selector together')
    try:
        result = inspect(args.sboot)
        if args.register_word is not None:
            result['supplied_scenario'] = s = scenario([int(v, 16) for v in result['table']['initial_file_bases']],
                                                       result['table']['conditional_stores'], args.register_word)
            s['prior_table_source_assumption'] = 'initial file bytes, not observed runtime contents'
            if args.slot is not None:
                from inspect_bl2_geometry_query import inspect as inspect_query
                q = inspect_query(args.sboot)['query']
                s['query_plan'] = query_plan(dict(query_bases=[int(v, 16) for v in s['after']],
                                                 term_field=q['term_field'], selector_field=q['selector_field']), *plan_args)
    except (OSError, ValueError, struct.error) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
