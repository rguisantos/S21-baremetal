#!/usr/bin/env python3
"""Static HZC2 geometry-query callback, register fields and MMIO provenance.

No firmware, device access or response simulation. Optional plans retain the
old control word and response as unknowns. Pointer translation stays nominal.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_epbl_preparation import adrp_ldr_pointer, uint
from inspect_lk_final_edges import signed
from inspect_monitor_preparation import word

QUERY, QUERY_END = 0x28480, 0x284e4
PREPARE, PREPARE_END = 0x2a24c, 0x2a2a8
RANGES = ((QUERY, QUERY_END), (PREPARE, PREPARE_END),
          (0x2f194, 0x2f1e0), (0x2f20c, 0x2f220),
          (0x2f234, 0x2f248), (0x2f258, 0x2f26c))
QUERY_TEMPLATE = ('71000c1f 53001c42 540000c8 90000043 913e6063 f8605863 '
                  'b9400063 14000007 7100101f 12800003 540001a1 90000043 '
                  'f947cc63 b9400063 33040423 90000041 913e6021 330c1843 '
                  'f8605820 52800021 b9000003 b9000401 b9400c03 2a0303e0 d65f03c0')
PREPARE_TEMPLATE = ('71000c1f 540000c8 d0000021 913f0021 f8605821 b9405021 '
                    '14000007 7100101f 12800001 54000181 d0000021 f947e021 '
                    'b9405021 d0000022 32080021 913f0042 f8605840 b9005001 '
                    '12077821 b9005001 52800001 2a0103e0 d65f03c0')


def adrp_add(data, first, second):
    a, b = word(data, first), word(data, second)
    if a & 0x9f000000 != 0x90000000 or b & 0xffc00000 != 0x91000000:
        raise ValueError('requires ADRP and unshifted ADD X immediate')
    if a & 31 == 31 or (b >> 5) & 31 != a & 31 or b & 31 == 31:
        raise ValueError('ADRP/ADD register mismatch')
    page = (first & ~4095) + (signed(((a >> 29) & 3) | (((a >> 5) & 0x7ffff) << 2), 21) << 12)
    return page + ((b >> 10) & 4095)


def bfi32(value):
    uint(value, 32)
    if value & 0xffc00000 != 0x33000000:
        raise ValueError('requires 32-bit BFM insertion')
    rotate, last = (value >> 16) & 63, (value >> 10) & 63
    if rotate >= 32 or last >= 32 or rotate <= last:
        raise ValueError('unsupported BFM form; expected wrapping BFI W')
    lsb, width = 32 - rotate, last + 1
    return dict(destination=value & 31, source=(value >> 5) & 31,
                lsb=lsb, width=width, mask=((1 << width)-1) << lsb)


def table5(data, offset):
    if offset < 0 or offset % 8 or offset + 40 > len(data):
        raise ValueError('five-pointer table outside aligned file bytes')
    return list(struct.unpack_from('<5Q', data, offset))


def decode(data):
    # Whole small routines are matched: a partial witness must not silently
    # ignore an added wait, barrier, service call, access or different branch.
    for start, template in ((QUERY, QUERY_TEMPLATE), (PREPARE, PREPARE_TEMPLATE)):
        expected = [int(v, 16) for v in template.split()]
        if [word(data, start + i*4) for i in range(len(expected))] != expected:
            raise ValueError(f'unsupported complete callback body at {start:#x}')
    query_table = adrp_add(data, 0x2848c, 0x28490)
    prepare_table = adrp_add(data, 0x2a254, 0x2a258)
    if adrp_add(data, 0x284bc, 0x284c0) != query_table:
        raise ValueError('query read/write tables differ')
    if adrp_ldr_pointer(data, 0x284ac, 0x284b0)[0] != query_table:
        raise ValueError('slot-four query read is not from table zero')
    if adrp_add(data, 0x2a280, 0x2a288) != prepare_table:
        raise ValueError('preparation read/write tables differ')
    if adrp_ldr_pointer(data, 0x2a274, 0x2a278)[0] != prepare_table:
        raise ValueError('slot-four preparation read is not from table zero')
    return dict(query_table_offset=query_table, query_bases=table5(data, query_table),
                prepare_table_offset=prepare_table, prepare_bases=table5(data, prepare_table),
                term_field=bfi32(word(data, 0x284b8)),
                selector_field=bfi32(word(data, 0x284c4)))


def query_plan(decoded, slot, term, selector):
    slot, term, selector = (uint(v, 32) for v in (slot, term, selector))
    result = dict(mode='symbolic_supplied_query_plan',
                  inputs_w0_w1_w2=[hex(v) for v in (slot, term, selector)],
                  operations=[], returned_x0=None, hardware_executed=False,
                  response_observed=False, memory_map_verified=False)
    if slot > 4:
        result['returned_x0'] = '0xffffffff'  # MOV W3,-1; MOV W0,W3 zero-extends.
        return result
    fields = (decoded['term_field'], decoded['selector_field'])
    mask = fields[0]['mask'] | fields[1]['mask']
    inserted = sum((v & ((1 << f['width'])-1)) << f['lsb']
                   for v, f in zip((term, selector & 255), fields))
    read_base = decoded['query_bases'][slot if slot < 4 else 0]
    base = decoded['query_bases'][slot]
    result['operations'] = [
        dict(pc='0x28498' if slot < 4 else '0x284b4', operation='read32',
             address=hex(read_base), result='unknown_old_control'),
        dict(pc='0x284d0', operation='write32', address=hex(base),
             value=dict(unknown_source='old_control', preserve_mask=hex(0xffffffff ^ mask),
                        insert_bits=hex(inserted))),
        dict(pc='0x284d4', operation='write32', address=hex(base+4), value=1),
        dict(pc='0x284d8', operation='read32', address=hex(base+12), result='unknown_response'),
    ]
    result['returned_x0'] = 'zero_extend32(unknown_response)'
    return result


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    d = decode(data)
    # Both caller bases are derived from their actual address instructions.
    query_cell = adrp_add(data, 0x2f1bc, 0x2f1c4) + 208
    prepare_cell = adrp_add(data, 0x2f194, 0x2f198) + 88
    if word(data, 0x2f1d0) != 0xf9406b8b or word(data, 0x2f1d4) != 0xd63f0160:
        raise ValueError('unexpected query callback load/call')
    if word(data, 0x2f1ac) != 0xf9402f21 or word(data, 0x2f1b8) != 0xd63f0020:
        raise ValueError('unexpected preparation callback load/call')
    bindings = []
    for cell, target in ((query_cell, QUERY), (prepare_cell, PREPARE)):
        pointer = struct.unpack_from('<Q', data, cell)[0]
        if pointer - NOMINAL_DELTA != target:
            raise ValueError('callback nominal target differs')
        bindings.append(dict(cell=hex(cell), pointer=hex(pointer), nominal_target=hex(target)))
    return dict(
        mode='static_geometry_query_provenance', input=dict(size=IMAGES['sboot'][0], sha256=IMAGES['sboot'][1]),
        nominal_callbacks=dict(delta=hex(NOMINAL_DELTA), bindings=bindings, runtime_binding_verified=False),
        query=dict(start=hex(QUERY), end_exclusive=hex(QUERY_END), instruction_count=25,
                   sha256=hashlib.sha256(data[QUERY:QUERY_END]).hexdigest(),
                   table_offset=hex(d['query_table_offset']), bases=[hex(v) for v in d['query_bases']],
                   bases_scope='initial file bytes; known conditional writer 0x2d270 may replace them',
                   runtime_table_contents_verified=False,
                   term_field=d['term_field'], selector_field=d['selector_field'],
                   control_preserve_mask=hex(0xffffffff ^ (d['term_field']['mask'] | d['selector_field']['mask'])),
                   write_control_offset=0, trigger_offset=4, trigger_value=1, response_offset=12,
                   response_width_bits=32, slot4_initial_read_uses_slot0=True,
                   invalid_slot_return_x0='0xffffffff', polling_or_barrier_in_body=False),
        preparation=dict(start=hex(PREPARE), end_exclusive=hex(PREPARE_END), instruction_count=23,
                         sha256=hashlib.sha256(data[PREPARE:PREPARE_END]).hexdigest(),
                         table_offset=hex(d['prepare_table_offset']), bases=[hex(v) for v in d['prepare_bases']],
                         control_offset=80, set_then_clear_bit=24, slot4_initial_read_uses_slot0=True,
                         valid_return_x0=0, invalid_slot_return_x0='0xffffffff', polling_or_barrier_in_body=False),
        caller=dict(packing_candidate='0x2f130', query_calls=['0x2f1d4', '0x2f21c', '0x2f244', '0x2f268'],
                    selectors_w2=[5, 6, 7, 8], slots_w0=[0, 1, 2, 3], terms_w1=[1, 2],
                    selectors_6_7_8_require_nonzero_selector5=True),
        words={hex(pc): f'{word(data, pc):08x}' for a, b in RANGES for pc in range(a, b, 4)},
        firmware_executed=False, hardware_response_observed=False, geometry_runtime_observed=False,
        memory_map_verified=False, free_memory_verified=False,
        limits=['Nominal code/table binding only; mutable tables and physical placement unobserved',
                'Query bases have a known conditional writer at 0x2d270; file values do not establish live table contents',
                'Literal base values are not evidence of their live mapping, clocks or register semantics',
                'No responses, DRAM initialization, register access or synthetic hardware execution',
                'Slot-four asymmetry is instruction behavior; no broadcast semantics or defect inferred',
                'No wait in these two bodies does not establish completion or behavior of surrounding calls'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    for name in ('slot', 'term', 'selector'):
        parser.add_argument('--'+name, type=lambda v: int(v, 0))
    args = parser.parse_args()
    supplied = (args.slot, args.term, args.selector)
    if any(v is not None for v in supplied) and any(v is None for v in supplied):
        parser.error('--slot, --term and --selector must be supplied together')
    try:
        result = inspect(args.sboot)
        if args.slot is not None:
            q = result['query']
            result['supplied_plan'] = query_plan(dict(query_bases=[int(v, 16) for v in q['bases']],
                                                       term_field=q['term_field'], selector_field=q['selector_field']),
                                                 *supplied)
            result['supplied_plan']['base_state_assumption'] = 'initial file table; conditional rewrite not applied'
    except (OSError, ValueError, struct.error) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
