#!/usr/bin/env python3
"""Selected second NEWTIME call: live slot, fixed argument copy and pointer store."""
import argparse
import hashlib
import json
import struct

from inspect_bl2_geometry_record import expect
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_monitor_preparation import word
from inspect_newtime_hzc2 import TEMPLATES as PREFIX, embedded, selection
from inspect_newtime_record_hzc2 import unsigned

NEW = (
    (0x1dc90, 'a9ba53f3 900000b3 a90263f7 a9015bf5 a9036bf9 f90023fe 53003c15 2a0103f7 2a0203f8 b4000063 911a2260 f9018803'),
    (0x1ded8, '900000b6'),
    (0x1dee4, '900000b4'),
    (0x1e83c, 'd286c901 b94c2ac0 f2a040e1 911a2279 11000400 b90c2ac0 f0000095 b9000020 97fffbf5 f9015f20 9400057c'),
    (0x1ea18, 'd286c901 b94c2ac0 91102294 f2a040e1 11000400 911a2273 b90c2ac0 2a1803e2 f9408683 b9000020 2a1703e1 f9417a60 d63f0060 f9404680 d63f0000 f9406282 2a1803e1 2a1703e0 d63f0040 f9402280 d63f0000'),
    (0x2f6c0, 'd286c701 f81f0ffe f2a040e1 f9000020 d0000001 911a2021 f9417820 f9418821 f9401421 d63f0020 7100041f 54000081 f84107fe 52800360 17ffc1b0 7100081f 54000081 f84107fe 528000a0 17ffc1ab 51000c00 7100041f 54fffec9 f84107fe d65f03c0'),
    (0x2ef90, 'd2813600 f2a2b0c0 b9400000 37f80280 d2870c00 f2a040e0 b9400401 5286c000 72a040e0 0b000020 f0000001 93407c00 f9047820 d2813781 f2a2b0c1 b9404c03 b9400022 33103862 b9000022 7940a002 b9400020 33003c40 b9000020 d65f03c0'),
    (0x2d5ac, '90000026 f2a040e0 911a20c2'),
    (0x2d6d0, '911a20d3'),
    (0x2d7d0, 'd286c000 f2a040e0 8b35c075 1b017e81 f9400000 f9017a60 8b21c061 f9000664 f9417a60 f9013a75 d3441c00 390ac660'),
)
TEMPLATES = NEW+PREFIX
RECORD, ALTERNATE, WINDOW = 0x02073600, 0x02075600, 0x4400


def publication(table, caller_value, wrapper_value, control=None):
    """Two explicit samples; reaching the first store is not callback success."""
    caller_value, wrapper_value = unsigned(caller_value, 64), unsigned(wrapper_value, 64)
    if control not in (None, 'name', 'key'):
        raise ValueError('unsupported lookup control')
    selected = selection(table, wrapper_value) if control is None else None
    reached = selected is not None
    return dict(fixed_argument_copy=caller_value, callback_input=wrapper_value,
        first_store_reached=reached, first_u64_written=wrapper_value if reached else None,
        row=selected['row'] if reached else None,
        comparison_key=selected['comparison_key'] if reached else None,
        prefix_error=None if reached else {'name': 3, 'key': 2, None: 1}[control])


def phase_counter(before):
    return (unsigned(before, 32)+1) & 0xffffffff


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    for pc, template in TEMPLATES:
        expect(data, pc, template)
    pointers = {0x31510: 0x2f6c0, 0x30808: 0x193fc,
                0x31490: 0x2ef90, 0x314c8: 0x2d568, 0x307e0: 0x30b50}
    for cell, target in pointers.items():
        if struct.unpack_from('<Q', data, cell)[0]-NOMINAL_DELTA != target:
            raise ValueError('nominal publication pointer changed')
    table = next(t for t in embedded(data)['parsed']['entries'] if t['key'] == 0x11111111)
    pcs = sorted(pc+i*4 for pc, t in TEMPLATES for i in range(len(t.split())))
    if len(pcs) != len(set(pcs)):
        raise ValueError('instruction witnesses overlap')
    index = b''.join(struct.pack('<II', pc, word(data, pc)) for pc in pcs)
    return dict(mode='static_bl2_second_newtime_publication', sboot_sha256=IMAGES['sboot'][1],
        instructions=dict(words=len(pcs), index_sha256=hashlib.sha256(index).hexdigest(),
            new_words=sum(len(t.split()) for _, t in NEW),
            prefix_words=sum(len(t.split()) for _, t in PREFIX)),
        nominal_pointers=[dict(cell=hex(c), target=hex(t)) for c, t in pointers.items()],
        phase=dict(earlier_size_call='0x1e85c -> 0x1d830',
            selected_caller=['0x1ea18', '0x1ea4c'],
            context_pages=['X19:0x31000', 'X20:0x31000', 'X22:0x31000'],
            w23_w24_from_original_arguments=['W1 at0x1dcac', 'W2 at0x1dcb0'],
            counter_cell='0x31c28', counter_store='0x1ea30',
            fixed_counter_copy=['0x1ea3c', '0x02073648'],
            counter_arithmetic='(previous_u32 + 1) mod2^32',
            geometry_load=['0x1ea44', '0x31978'], indirect_call=['0x1ea48', '0x31510'],
            intervening_calls_and_reachability_verified=False),
        wrapper=dict(entry='0x2f6c0', fixed_argument_copy=['0x2f6cc', '0x02073638'],
            geometry_reload=['0x2f6d8', '0x31978'], context_cell='0x31998',
            context_callback_offset=40, indirect_call='0x2f6e4',
            argument_and_reload_guaranteed_equal=False),
        first_store=dict(callback='0x193fc', name='NEWTIME', key='0x11111111',
            selector_rows=table['rows'], pointer_cell='0x30520', store='0x19694',
            stored_value='original wrapper reload, before comparison-key normalization',
            source_sample='wrapper reload, not caller sample',
            errors_before_store=dict(name=3, key=2, row=1),
            callback_remainder_and_wrapper_error_helper_executed=False),
        continuation=dict(after_wrapper_return=['0x1ea50 -> nominal0x2ef90',
                '0x1ea60 -> nominal0x2d568', '0x1ea68 -> unresolved_callback'],
            selected_gate_helper=['0x2ef90', '0x2eff0'],
            gate_reads=['0x158609b0', '0x158609bc'], gate_writes=['0x158609bc'],
            reload_source='0x02073600', pointer_and_fixed_record_alias_verified=False,
            final_record_preservation_verified=False),
        firmware_executed=False, hardware_record_or_final_ram_fdt_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        parser.exit(2, f'inspect_bl2_geometry_publication: {exc}\n')
    print(json.dumps(result, indent=2))
