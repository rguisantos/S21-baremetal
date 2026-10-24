#!/usr/bin/env python3
"""Static HZC2 record-to-geometry reloads and selected record lifecycle.

No record bytes, register responses or RAM capacity are supplied or invented.
Only the exact firmware is read. Copy destinations and reloads are conditional
code witnesses, not a measured boot sequence or a physical-to-file mapping.
"""
import argparse
import hashlib
import json
import struct
import sys

from inspect_bl2_geometry_query import adrp_add
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_bl2_query_base_rewrite import page_address
from inspect_descriptor_provenance import copy_loop
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_epbl_preparation import uint
from inspect_monitor_preparation import word
from inspect_sboot_hzc2 import bl_target

RECORD = 0x02073600
RANGES = ((0x161d8, 0x16228), (0x1dc94, 0x1dc98), (0x1dee4, 0x1dee8),
          (0x1e2a4, 0x1e2e4), (0x1f9e8, 0x1fa0c), (0x2d364, 0x2d3bc),
          (0x2d5ac, 0x2d5b0), (0x2d6d0, 0x2d6d4), (0x2d7d0, 0x2d800),
          (0x2f724, 0x2f758), (0x2f758, 0x2f78c), (0x2f7f4, 0x2f890))
PREFIX = ('d286c001 90000022 f2a040e1 f81f0ffe 911a2042 f9400021 f9017841 '
          'f9417843 d3441c63 390ac443 53001c61 b4000040 f9018840')
RELOAD = ('d286c000 f2a040e0 8b35c075 1b017e81 f9400000 f9017a60 '
          '8b21c061 f9000664 f9417a60 f9013a75 d3441c00 390ac660')


def expect(data, start, template):
    expected = [int(v, 16) for v in template.split()]
    if [word(data, start+i*4) for i in range(len(expected))] != expected:
        raise ValueError(f'unsupported geometry-record witness at {start:#x}')


def wide64(data, offsets, register):
    """Selected MOVZ X then MOVK X producers; not intervening execution."""
    if type(register) is not int or not 0 <= register < 31 or not 1 <= len(offsets) <= 4:
        raise ValueError('requires one to four X move-wide producers')
    if list(offsets) != sorted(set(offsets)):
        raise ValueError('move-wide producer offsets must be unique and ordered')
    value = 0
    for i, pc in enumerate(offsets):
        w = word(data, pc)
        if w & 0xff80001f != (0xd2800000 if i == 0 else 0xf2800000) | register:
            raise ValueError('move-wide opcode/width/register mismatch')
        shift = ((w >> 21) & 3)*16
        value = (value & ~(65535 << shift)) | (((w >> 5) & 65535) << shift)
    return value


def reloads(data):
    expect(data, 0x2d364, PREFIX)
    expect(data, 0x2d7d0, RELOAD)
    if word(data, 0x2d5ac) != 0x90000026 or word(data, 0x2d6d0) != 0x911a20d3:
        raise ValueError('second reload state context changed')
    result = []
    for source_pcs, reg, state, load, store, mode_store in (
            ((0x2d364, 0x2d36c), 1, adrp_add(data, 0x2d368, 0x2d374), 0x2d378, 0x2d37c, 0x2d388),
            ((0x2d7d0, 0x2d7d4), 0, adrp_add(data, 0x2d5ac, 0x2d6d0), 0x2d7e0, 0x2d7e4, 0x2d7fc)):
        result.append(dict(source_address=hex(wide64(data, source_pcs, reg)),
                           source_load=hex(load), source_width_bits=64,
                           state_base=hex(state), geometry_store=hex(store),
                           geometry_cell=hex(state+752), geometry_value='unknown_record_u64',
                           mode_store=hex(mode_store), mode_cell=hex(state+689),
                           mode_source_bits=[4, 7], mode_width_bits=8))
    return result


def field_copy(data, pc):
    if word(data, pc+8) != 0xb9400001 or word(data, pc+20) != 0xb9000001:
        raise ValueError('expected LDR W1,[X0] and STR W1,[X0]')
    source = wide64(data, (pc, pc+4), 0)
    destination = wide64(data, (pc+12, pc+16), 0)
    return dict(load_pc=hex(pc+8), store_pc=hex(pc+20), source=hex(source),
                destination=hex(destination), width_bits=32,
                touches_first_record_u64=destination < RECORD+8 and RECORD < destination+4)


def copied_span(copy, address, size):
    address, size = uint(address, 64), uint(size, 64)
    first, end = (int(v, 16) for v in copy['source'])
    if size == 0 or not first <= address < address+size <= end:
        raise ValueError('requested span outside this copy source')
    destination = int(copy['destination'][0], 16) + address-first
    return dict(source=hex(address), destination=hex(destination), bytes=size,
                execution_observed=False, source_bytes_observed=False)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    paths = reloads(data)
    expect(data, 0x1e2a4, '91102299 911a2275 11000400 b90c2ac0 52800182 f9408723 b9000020 '
           'd2995fc0 f9017aa0 2a0203e1 f9417aa0 d63f0060 52800181 f9406322 2a0103e0 d63f0040')
    expect(data, 0x1f9e8, '53001c21 d2800003 4b030044 6b1f009f 5400008d 38236801 91000463 17fffffb d65f03c0')
    expect(data, 0x2f7f4, '911a2273 394b7a60 370004a0')
    expect(data, 0x2f75c, '52800582 52800001')
    if bl_target(word(data, 0x2f788), 0x2f788) != 0x1f9e8:
        raise ValueError('record-clear helper changed')
    if word(data, 0x2f744) != 0x340000a0 or word(data, 0x2f754) != 0x14000028:
        raise ValueError('record-clear branch changed')
    if bl_target(word(data, 0x2f740), 0x2f740) != 0x2e4fc:
        raise ValueError('record-clear gate call changed')
    state = paths[0]['state_base']
    caller_state = adrp_add(data, 0x1dc94, 0x1e2a8)
    table = adrp_add(data, 0x1dee4, 0x1e2a4)
    if caller_state != int(state, 16) or page_address(word(data, 0x1dc94), 0x1dc94) != 0x31000:
        raise ValueError('selected phase context changed')
    bindings = []
    for cell, target, role in ((0x31580, 0x2d364, 'registered_reload; caller_not_resolved'),
                               (table+192, 0x2d568, 'reload_with_parameter_setup'),
                               (table+264, 0x2f6c0, 'callback_after_marker')):
        pointer = struct.unpack_from('<Q', data, cell)[0]
        if pointer-NOMINAL_DELTA != target:
            raise ValueError('nominal record callback target changed')
        bindings.append(dict(cell=hex(cell), pointer=hex(pointer), target=hex(target), role=role))
    copies = [copy_loop(data, pc, 4) for pc in (0x161d8, 0x16200)]
    first = copied_span(copies[0], RECORD, 8)
    second = copied_span(copies[1], int(first['destination'], 16), 8)
    fields = [field_copy(data, pc) for pc in range(0x2f800, 0x2f890, 24)]
    for field in fields:
        offset = int(field['destination'], 16)-RECORD
        if int(field['source'], 16) != int(first['destination'], 16)+offset:
            raise ValueError('field source does not match selected backup-copy relation')
    return dict(
        mode='static_geometry_record_provenance', input=dict(size=IMAGES['sboot'][0], sha256=IMAGES['sboot'][1]),
        record=dict(address=hex(RECORD), first_word_width_bits=64, contents_observed=False,
                    file_mapping_verified=False, other_geometry_slots_verified=False, reloads=paths,
                    context_assumptions=['0x2d568 path carries page X6 from 0x2d5ac to X19 at 0x2d6d0',
                                         'Selected reloads only; surrounding setup/callbacks are not executed']),
        nominal_callbacks=dict(delta=hex(NOMINAL_DELTA), bindings=bindings, runtime_binding_verified=False,
                                phase_context='X19/X20 retain 0x31000 pages; X25=0x31408 in selected caller'),
        marker=dict(value=hex(wide64(data, (0x1e2c0,), 0)), store='0x1e2c4',
                    geometry_cell=paths[0]['geometry_cell'], width_bits=64,
                    callback_after_store='0x1e2d0', reload_callback='0x1e2e0',
                    reload_arguments_w0_w1=[12, 12], execution_observed=False,
                    role='literal intermediate state; not a measured geometry word or RAM capacity'),
        selected_copies=[{k: v for k, v in c.items() if k != 'destination_overlaps_descriptor'} for c in copies],
        conditional_record_locations=[first, second],
        conditional_clear=dict(call='0x2f788', helper='0x1f9e8',
                               destination=hex(wide64(data, (0x2f774, 0x2f778), 0)),
                               value_byte=0, bytes=44, if_previous_w0_zero_at='0x2f744',
                               previous_call='0x2f740 -> 0x2e4fc', return_observed=False,
                               post_function_record_contents_verified=False),
        conditional_field_restore=dict(gate='0x2f7fc', skip_if_state_byte_bit0_set=hex(int(state, 16)+734),
                                        fields=fields, touches_first_record_u64=any(f['touches_first_record_u64'] for f in fields),
                                        execution_observed=False),
        words={hex(pc): f'{word(data, pc):08x}' for a, b in RANGES for pc in range(a, b, 4)},
        firmware_executed=False, geometry_runtime_observed=False, complete_writer_census=False,
        memory_map_verified=False, free_memory_verified=False,
        limits=['Record address and copies do not recover original or runtime record bytes',
                'Registered reload at 0x2d364 has no caller resolved here; a table pointer is not reachability',
                'Prefix effects do not establish post-callback state, final geometry or execution order',
                'Selected clear and six restored fields do not determine the first u64 after the whole function',
                'Only the first geometry slot is traced; remaining slots and real responses are unobserved',
                'Literal markers and unobserved record contents do not identify physical RAM capacity'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, struct.error) as error:
        parser.exit(2, f'error: {error}\n')
