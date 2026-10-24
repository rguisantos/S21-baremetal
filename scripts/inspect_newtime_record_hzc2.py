#!/usr/bin/env python3
"""Conditional NEWTIME record layout, key gates and allocation in exact HZC2.

Enumerates branch choices, not measured MMIO samples. Relative record plans
assume an aligned, stable base and disjoint source/state/stack/record memory.
"""
import argparse
from collections import Counter
import hashlib
import json
import struct

from inspect_bl2_geometry_record import expect
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_monitor_preparation import word
from inspect_newtime_hzc2 import embedded, inspect as inspect_prefix

U32, U64 = (1 << 32)-1, (1 << 64)-1
DIRECTORY, DATA, LIMIT = 0x1a0, 0x2a0, 0x2400
TEMPLATES = (
    (0x18054, 'b00000c2 8b214001 91290042 a9010440 d65f03c0 b00000c2 91290042 f9400843 91000c61 8b20c020 f9400c41 927ef400 f9000840 eb00003f 54000042 14000000 aa0303e0 d65f03c0'),
    (0x19698, 'b90113bf 14000018 900000c0 91306000 f9400001 b98113a0 8b000020 39401002 f9406ba1 b98113a0 8b000020 2a0203e1 39002001 f94083a1 b98113a0 8b000020 39401002 f9406ba1 b98113a0 8b000020 2a0203e1 39003001 b94113a0 11000400 b90113a0 b94113a0 71000c1f 54fffced f9406ba0 91008000 91060001 f9406ba0 f9001001 f9406ba0 f9401001 b940b3a0 93407c00 d37cec00 8b000020 f90067a0 b940b3a0 93407c00 2a0003e1 2a0103e0 53040c00 4b010000 531c6c00 11400800 11098000 2a0003e1 f94067a0 97fffa3c b9011bbf 14000094 f94087a0 b9400000 d35f7c00 53001c00 7100041f 54000461 b9411ba0 7100201f 5400040c f94057a1 b9811ba0 d37df000 8b000020 f9400000 92400c00 f100201f 540001a1 f94057a1 b9811ba0 d37df000 8b000020 f94057a2 b9811ba1 d37df021 8b010041 f9400021 91000c21 f9000001 1400000c f94057a1 b9811ba0 d37df000 8b000020 f94057a2 b9811ba1 d37df021 8b010041 f9400021 d1000c21 f9000001 f94057a1 b9811ba0 d37df000 8b000020 f9400000 aa0003e1 f94083a0 94000c04 f90063a0 f94063a0 eb1f001f 54000061 52800080 1400006e f94063a0 b9401001 f94063a0 b9401400 1b007c20 531e7400 97fffa02 f9005fa0 f9406ba0 f9401001 b9811ba0 d37cec00 8b000020 f94057a2 b9811ba1 d37df021 8b010041 f9400021 b9000001 f9406ba0 f9401001 b9811ba0 d37cec00 8b000020 f9405fa1 f00000a2 91148042 f9400042 cb020021 b9000401 f9406ba0 f9401001 b9811ba0 d37cec00 8b000020 f94063a1 b9401021 b9000801 f9406ba0 f9401001 b9811ba0 d37cec00 8b000020 f94063a1 b9401421 b9000c01 b9011fbf 14000025 b90113bf 1400001b f94063a0 b9401001 b9411fa0 1b007c21 b94113a0 0b000020 93407c00 d37ef400 f9405fa1 8b000020 f94063a1 f9400c22 f94063a1 b9401023 b9411fa1 1b017c63 b94113a1 0b010061 93407c21 d37ef421 8b010041 b9400021 b9000001 b94113a0 11000400 b90113a0 f94063a0 b9401001 b94113a0 6b00003f 54fffc4c b9411fa0 11000400 b9011fa0 f94063a0 b9401401 b9411fa0 6b00003f 54fffb0c f90063bf b9411ba0 11000400 b9011ba0 b940b3a1 b9411ba0 6b00003f 54ffed4c 900000c0 91294000 f9400000 aa0003e1 f00000a0 91148000 f9400000 cb000020 2a0003e1 f9406ba0 b9001001 52800000 f94037a1 9100003f 910003bf a94153f3 a9425bf5 a94363f7 a9446bf9 a94573fb a8d27bfd d65f03c0'),
    (0x2f6c0, 'd286c701 f81f0ffe f2a040e1 f9000020 d0000001 911a2021 f9417820 f9418821 f9401421 d63f0020 7100041f 54000081 f84107fe 52800360 17ffc1b0 7100081f 54000081 f84107fe 528000a0 17ffc1ab 51000c00 7100041f 54fffec9 f84107fe d65f03c0'),
)


def unsigned(value, bits):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'requires unsigned {bits}-bit integer')
    return value


def allocation(cursor, limit, size_w):
    """Original leaf updates the cursor before comparing; exhaustion parks."""
    cursor, limit, size_w = unsigned(cursor, 64), unsigned(limit, 64), unsigned(size_w, 32)
    signed_size = size_w if size_w < 1 << 31 else size_w-(1 << 32)
    after = ((cursor+3+signed_size) & U64) & ~3
    return dict(returned_pointer=cursor if after <= limit else None,
                cursor_after=after, parked=after > limit)


def gated_key(key, index, branch_mask):
    key, index, branch_mask = unsigned(key, 64), unsigned(index, 32), unsigned(branch_mask, 9)
    if index <= 8 and branch_mask >> index & 1:
        return (key+(3 if key & 15 == 8 else -3)) & U64
    return key


def wrapper_result(status):
    status = unsigned(status, 32)
    if status in (1, 3, 4):
        return dict(tail_target='0x1fdb8', w0_argument=27, returns_directly=False)
    if status == 2:
        return dict(tail_target='0x1fdb8', w0_argument=5, returns_directly=False)
    return dict(returned_w0=(status-3) & U32, returns_directly=True)


def plan(tables, row, branch_mask):
    unsigned(row, 32); unsigned(branch_mask, 9)
    special = tables[0x11111111]
    if special['columns'] != 17 or not row < special['rows']:
        raise ValueError('unsupported special shape or row')
    keys = special['cells'][row*17+1:(row+1)*17]
    cursor, steps = DATA, []
    for index, original in enumerate(keys):
        key = gated_key(original, index, branch_mask)
        table = tables.get(key)
        if table is None:
            return dict(status='missing_key', return_code=4, cursor=cursor, steps=steps,
                        failed_index=index, failed_key=key, final_used_field_written=False)
        size = (table['columns']*table['rows']*4) & U32
        step = allocation(cursor, LIMIT, size)
        cursor = step['cursor_after']
        if step['parked']:
            return dict(status='parked_allocator', return_code=None, cursor=cursor, steps=steps,
                        failed_index=index, failed_key=key, final_used_field_written=False)
        steps.append(dict(index=index, original_key=original, key=key,
            descriptor_offset=DIRECTORY+index*16, payload_offset=step['returned_pointer'],
            bytes=size, columns=table['columns'], rows=table['rows']))
    return dict(status='complete', return_code=0, cursor=cursor, steps=steps,
                final_used_field_written=True)


def survey(tables):
    counts, missing, witnesses, rows = Counter(), Counter(), {}, []
    for row in range(tables[0x11111111]['rows']):
        row_counts, ends = Counter(), []
        for mask in range(512):
            result = plan(tables, row, mask)
            counts[result['status']] += 1; row_counts[result['status']] += 1
            if result['status'] == 'complete':
                ends.append(result['cursor'])
            elif result['status'] == 'missing_key':
                key = result['failed_key']; missing[key] += 1
                witnesses.setdefault(key, dict(row=row, branch_mask=mask,
                    failed_index=result['failed_index'], descriptors_committed=len(result['steps']),
                    cursor_before_error=hex(result['cursor'])))
        rows.append(dict(row=row, counts=dict(row_counts),
                         min_complete_used_bytes=min(ends) if ends else None,
                         max_complete_used_bytes=max(ends) if ends else None))
    return dict(effective_branch_sequences=512, row_count=len(rows), scenarios=sum(counts.values()),
        counts=dict(counts), per_row=rows,
        missing_keys=[dict(key=hex(k), scenarios=missing[k], witness=witnesses[k]) for k in sorted(missing)])


def representatives(tables):
    selected = {(row, mask) for row in range(tables[0x11111111]['rows']) for mask in (0, 511, 0x90, 0x16f)}
    for row in survey(tables)['missing_keys']:
        witness = row['witness']; selected.add((witness['row'], witness['branch_mask']))
    return sorted(selected)


def inspect(path):
    prefix = inspect_prefix(path)
    data = read_exact(path, *IMAGES['sboot'])
    for pc, template in TEMPLATES:
        expect(data, pc, template)
    raw = embedded(data)
    tables = {t['key']: t for t in raw['parsed']['entries']}
    result = survey(tables)
    if result['counts'] != dict(complete=8512, missing_key=2752) or result['scenarios'] != 11264:
        raise ValueError('embedded conditional key survey changed')
    indexed = b''.join(struct.pack('<II', pc, word(data, pc)) for a, t in TEMPLATES for pc in range(a, a+4*len(t.split()), 4))
    return dict(mode='conditional_newtime_record_lifecycle', sboot_sha256=IMAGES['sboot'][1],
        prefix_instruction_index_sha256=prefix['instructions']['index_sha256'],
        layout=dict(record_base='unknown_live_pointer_at_0x30520',
            original_input_u64_offset=0, ect_version_bytes=[8, 12], newtime_version_bytes=[12, 16],
            final_used_u32_offset=16, directory_pointer_u64_offset=32,
            directory_offset=hex(DIRECTORY), descriptor_count=16, descriptor_stride=16,
            descriptor_fields=['key_low32', 'payload_offset_low32', 'columns_u32', 'rows_u32'],
            data_start_offset=hex(DATA), data_capacity=hex(LIMIT-DATA), record_end_offset=hex(LIMIT),
            reserved_gaps_zeroed=False),
        gates=dict(register='0x158609bc', bit=31, read='0x19774',
            resampled_each_iteration=True, sample_sequence_observed=False,
            effective_index_interval_inclusive=[0, 8], transformation='if selected and index<=8: low_nibble_8 ? key+3 : key-3 (u64)',
            branch_choices_not_register_values=True),
        allocator=dict(setup='0x18054', leaf='0x18068', cursor_cell='0x31a50', limit_cell='0x31a58',
            signed_request_bits=32, alignment_bytes=4, cursor_written_before_check=True,
            exhaustion='park_at_0x18090; no_NULL_return_or_rollback'),
        survey=result,
        first_u64_preservation=dict(later_direct_record_fields_start_at=8,
            descriptor_and_payload_regions_disjoint_from_first_u64=True,
            conditional_on_stable_base_and_nonoverlapping_memory=True,
            physical_preservation_verified=False),
        errors=dict(missing_key_code=4, prior_stores_rolled_back=False,
                    final_used_field_written_on_code4=False, error_implies_untouched_record=False),
        wrapper=dict(file='0x2f6c0', callback_status_mapping={str(s): wrapper_result(s) for s in range(6)},
                     handler_effects_on_record_verified=False),
        instructions=dict(new_words=len(indexed)//8, suffix_index_sha256=hashlib.sha256(indexed).hexdigest()),
        firmware_executed=False, hardware_gate_or_record_observed=False,
        final_ram_or_fdt_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        parser.exit(2, f'inspect_newtime_record_hzc2: {exc}\n')
    print(json.dumps(result, indent=2))
