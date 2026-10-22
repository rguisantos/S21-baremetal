#!/usr/bin/env python3
"""Hash-bound HZC2 LK RAM-node call evidence and explicit input scenarios.

Models arguments to 0xf1570, not successful FDT edits or available memory.
No service, firmware instruction, allocation or device operation is executed.
"""
import argparse
import json
import struct

from inspect_el2_hzc2 import IMAGES, calls, read_exact, words
from inspect_sec_pgtbl_hzc2 import U32, U64, response_model

LOW_BASE = 0x80000000
HIGH_BASE = 0x880000000
CHUNK = 0x20000000
MAX_CALLS = 128  # Host output limit, not a check performed by LK.
FIELDS = ('total_ram_bytes', 'soc_version_x0', 'soc_base_x0',
          'soc_reserved_size_x0', 'pgtbl_base_x0', 'pgtbl_size_x0',
          'harx_status_w0', 'harx_base', 'harx_size')
MAX_SCENARIO = 8192


def normalize(values):
    if not isinstance(values, dict) or set(values) != set(FIELDS):
        raise ValueError('scenario must supply exactly: ' + ', '.join(FIELDS))
    result = {}
    for key in FIELDS:
        value = values[key]
        if isinstance(value, str):
            if len(value) > 20:
                raise ValueError('scenario integer literal too long')
            try:
                value = int(value, 0)
            except ValueError as error:
                raise ValueError('invalid integer for ' + key) from error
        limit = U32 if key == 'harx_status_w0' else U64
        if type(value) is not int or not 0 <= value <= limit:
            raise ValueError(key + ': requires an unsigned register value')
        result[key] = value
    return result


def read_scenario(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate scenario key: ' + key)
            result[key] = value
        return result
    with open(path, 'rb') as stream:
        data = stream.read(MAX_SCENARIO + 1)
    if len(data) > MAX_SCENARIO:
        raise ValueError('scenario exceeds 8192-byte host limit')
    try:
        parsed = json.loads(data, object_pairs_hook=unique)
    except RecursionError as error:
        raise ValueError('scenario JSON nesting exceeds parser limit') from error
    return normalize(parsed)


def model(values):
    v = normalize(values)
    report = dict(
        mode='supplied_lk_ram_node_call_scenario',
        inputs={key: hex(value) for key, value in v.items()},
        stop='bank_calls_complete', requested_nodes=[],
        runtime_observed=False, service_replies_observed=False,
        provider_executed=False, fdt_writes_executed=False,
        is_final_fdt=False, memory_map_verified=False, free_memory_verified=False,
        limits=['Arguments to the bank writer only; editor success is unverified',
                'All nine inputs are supplied, not inferred from the phone model',
                'No legacy/positive soc_info translation or secure provider execution',
                'FDT preparation, bootargs, reservations and later processing omitted',
                '128 requested calls is a host limit, not an LK guard'])
    # LK compares the version and reserved size in W registers, the base in X.
    if v['soc_version_x0'] & U32 != 0x66001000:
        report['stop'] = 'soc_version_park_0xfadc4'
        return report
    if v['soc_base_x0'] == U64:
        report['stop'] = 'soc_base_park_0xfb66c'
        return report
    if v['soc_reserved_size_x0'] & U32 == U32:
        report['stop'] = 'soc_size_park_0xfb65c'
        return report

    pg = response_model(v['pgtbl_base_x0'], v['pgtbl_size_x0'])['lk']
    report['sec_pgtbl'] = pg
    cursor = (v['soc_base_x0'] + (v['soc_reserved_size_x0'] & U32)) & U64
    report['cursor_after_soc_wrapped64'] = hex(cursor)
    report['soc_size_upper32_ignored'] = hex(v['soc_reserved_size_x0'] >> 32)

    def request(base, size, call):
        if len(report['requested_nodes']) >= MAX_CALLS:
            raise ValueError('scenario exceeds 128 bank-writer calls (host limit)')
        base, size = base & U64, size & U32
        report['requested_nodes'].append(dict(
            call_offset=hex(call), node_name=f'memory@{base:x}',
            base=hex(base), size_low32=hex(size),
            end_exclusive_math=hex(base + size), end_overflows_u64=base + size > U64,
            zero_size=size == 0,
            reg_bytes_if_written_be=struct.pack('>QI', base, size).hex()))

    request(LOW_BASE, v['soc_base_x0'] - LOW_BASE, 0xfaf34)
    gap = (v['harx_status_w0'] == 0 and v['harx_base'] != 0 and v['harx_size'] != 0)
    report['harx_gap_taken'] = gap
    if gap:
        request(cursor, v['harx_base'] - cursor, 0xfaf50)
        cursor = (v['harx_base'] + v['harx_size']) & U64
    report['cursor_after_harx_wrapped64'] = hex(cursor)

    if pg['w22_split_flag']:
        request(cursor, int(pg['normalized_base'], 0) - cursor, 0xfb678)
        tail = int(pg['x27_end_wrapped64'], 0)
    else:
        tail = cursor
    total = v['total_ram_bytes']
    if total <= 0x7fffffff:
        request(tail, total + LOW_BASE - tail,
                0xfb740 if pg['w22_split_flag'] else 0xfb7c8)
    else:
        request(tail, -tail, 0xfb690 if pg['w22_split_flag'] else 0xfaf74)

    remaining = max(0, total - LOW_BASE)
    count = (remaining + CHUNK - 1) // CHUNK
    if count > MAX_CALLS - len(report['requested_nodes']):
        raise ValueError('scenario exceeds 128 bank-writer calls (host limit)')
    for index in range(count):
        request(HIGH_BASE + index * CHUNK, CHUNK, 0xfb7a8)
    report['high_memory'] = dict(
        base=hex(HIGH_BASE), chunk_size=hex(CHUNK), call_count=count,
        supplied_total_above_2GiB=hex(remaining),
        requested_bytes=hex(count * CHUNK),
        bytes_past_supplied_remainder=hex(count * CHUNK - remaining),
        final_chunk_is_clamped=False)
    return report


def evidence(path):
    data = read_exact(path, *IMAGES['sboot'])
    return dict(
        mode='static_read_only_lk_bank_constructor',
        sboot_sha256=IMAGES['sboot'][1], constructor='0xfad60',
        bank_writer='0xf1570', bank_phase_stop='0xfaf84',
        calls=calls(data, (0xfad84, 0xfada0, 0xfadd8, 0xfadf8,
                           0xfae40, 0xfae90, 0xfaee8, 0xfaf34, 0xfaf50,
                           0xfaf74, 0xfb678, 0xfb690, 0xfb740, 0xfb7a8, 0xfb7c8,
                           0xf15b8, 0xf1608, 0xf1634)),
        instruction_words=words(data, (0xfadac, 0xfaddc, 0xfadfc, 0xfae14,
                                      0xfaef0, 0xfaf10, 0xfaf18, 0xfaf30,
                                      0xfaf38, 0xfaf40, 0xfaf48, 0xfaf54, 0xfaf58,
                                      0xfaf5c, 0xfaf60, 0xfaf68, 0xfaf6c, 0xfaf80,
                                      0xfb674, 0xfb684, 0xfb688, 0xfb734, 0xfb738,
                                      0xfb73c, 0xfb788, 0xfb78c, 0xfb794, 0xfb798,
                                      0xfb79c, 0xfb7a0, 0xfb7a4, 0xfb7ac, 0xfb7b0,
                                      0xfb7c0, 0xfb7c4, 0xf1594, 0xf15d8,
                                      0xf15dc, 0xf15e0)),
        string_literals={hex(off): data[off:data.index(0, off)].decode('ascii')
                         for off in (0x20e520, 0x20e530, 0x20e540,
                                     0x20e558, 0x20e560, 0x20e568)},
        runtime_observed=False, provider_executed=False,
        memory_map_verified=False, is_final_fdt=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', help='exact raw HZC2 sboot.bin')
    parser.add_argument('--scenario', help='JSON with all nine explicit unsigned inputs')
    args = parser.parse_args()
    try:
        result = evidence(args.sboot)
        if args.scenario:
            result['scenario'] = model(read_scenario(args.scenario))
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f'check_lk_memory_banks: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
