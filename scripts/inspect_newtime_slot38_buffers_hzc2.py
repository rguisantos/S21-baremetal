#!/usr/bin/env python3
"""Static origin, byte footprint and conditional restore of slot38's buffer."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_hzc2 import embedded
from inspect_newtime_jump_tables_hzc2 import DELTA, case_walk, u32
from inspect_newtime_record_hzc2 import plan
from inspect_newtime_slot38_hzc2 import leaf_result, pointer_from_offset, s32

U64 = (1 << 64) - 1
RANGES = ((0x1fcc4, 0x1fce8), (0x22370, 0x225d0), (0x2d5cc, 0x2d5e0),
          (0x2f488, 0x2f4b0), (0x2fa54, 0x2fa98))
SELECTED = {
    0x1fcc4: ('mov', 'x3, #0x0'), 0x1fcc8: ('sub', 'w4, w2, w3'),
    0x1fccc: ('cmp', 'w4, wzr'), 0x1fcd0: ('b.le', '0x1fce4'),
    0x1fcd4: ('ldrb', 'w4, [x1, x3]'), 0x1fcd8: ('strb', 'w4, [x0, x3]'),
    0x1fcdc: ('add', 'x3, x3, #0x1'), 0x1fce0: ('b', '0x1fcc8'), 0x1fce4: ('ret', ''),
    0x22370: ('stp', 'x19, x20, [sp, #-448]!'),
    0x22384: ('mov', 'w24, w0'), 0x2239c: ('mov', 'w21, w1'),
    0x223dc: ('cmp', 'w21, #0x5'), 0x223e0: ('b.le', '0x22470'),
    0x223e4: ('mov', 'x0, #0x9bc'), 0x223e8: ('movk', 'x0, #0x1586, lsl #16'),
    0x223ec: ('ldr', 'w0, [x0]'), 0x223f0: ('uxth', 'w0, w0'),
    0x223f4: ('asr', 'w0, w0, w21'), 0x223f8: ('tbz', 'w0, #0, 0x22470'),
    0x223fc: ('mov', 'x0, #0x37e0'), 0x22400: ('sub', 'w2, w21, #0x6'),
    0x22408: ('mov', 'w1, #0x3600'), 0x2240c: ('movk', 'w1, #0x207, lsl #16'),
    0x22428: ('mov', 'x0, #0x3800'), 0x2242c: ('movk', 'x0, #0x207, lsl #16'),
    0x22430: ('ldp', 'w20, w0, [x0, #4]'), 0x22434: ('lsl', 'w0, w0, #2'),
    0x22438: ('add', 'w20, w20, w1'), 0x2243c: ('mul', 'w0, w0, w2'),
    0x22444: ('sxtw', 'x0, w0'), 0x22448: ('add', 'x20, x0, w20, sxtw'),
    0x22470: ('mov', 'x0, #0x37d0'), 0x224a0: ('mov', 'x0, #0x37f0'),
    0x22474: ('mov', 'w2, #0x3600'), 0x2247c: ('movk', 'w2, #0x207, lsl #16'),
    0x224a4: ('movk', 'x0, #0x207, lsl #16'),
    0x224a8: ('ldp', 'w20, w0, [x0, #4]'), 0x224ac: ('lsl', 'w0, w0, #2'),
    0x224b0: ('add', 'w20, w20, w2'), 0x224b4: ('mul', 'w0, w0, w21'),
    0x224b8: ('sxtw', 'x0, w0'), 0x224bc: ('add', 'x20, x0, w20, sxtw'),
    0x224dc: ('mov', 'x1, x25'), 0x224e0: ('mov', 'w2, #0xa0'),
    0x224e4: ('add', 'x0, sp, #0x60'),
    0x224e8: ('add', 'x28, sp, #0x100'), 0x224ec: ('add', 'x27, sp, #0x148'),
    0x224f4: ('bl', '0x1fcc4'), 0x224f8: ('mov', 'x1, x20'),
    0x224fc: ('mov', 'w2, #0x48'), 0x22500: ('mov', 'x0, x28'),
    0x22504: ('bl', '0x1fcc4'), 0x22508: ('ldrb', 'w2, [x22, #1672]'),
    0x2250c: ('mov', 'x1, x19'), 0x22510: ('mov', 'x0, x27'),
    0x22514: ('lsl', 'w2, w2, #2'), 0x22518: ('bl', '0x1fcc4'),
    0x22528: ('mov', 'x2, x20'), 0x22538: ('blr', 'x5'),
    0x22548: ('ldr', 'x2, [x24, #96]'), 0x22558: ('blr', 'x2'),
    0x22560: ('ldr', 'x2, [x23, #160]'), 0x22564: ('mov', 'w0, w21'),
    0x22568: ('mov', 'w1, #0x0'), 0x2256c: ('blr', 'x2'),
    0x22570: ('ldr', 'x2, [x24, #96]'), 0x2257c: ('blr', 'x2'),
    0x22580: ('add', 'x1, sp, #0x60'), 0x22584: ('mov', 'w2, #0xa0'),
    0x22588: ('mov', 'x0, x25'), 0x2258c: ('bl', '0x1fcc4'),
    0x22590: ('mov', 'x1, x28'), 0x22594: ('mov', 'w2, #0x48'),
    0x22598: ('mov', 'x0, x20'), 0x2259c: ('bl', '0x1fcc4'),
    0x225a0: ('ldrb', 'w2, [x22, #1672]'), 0x225a4: ('mov', 'x1, x27'),
    0x225a8: ('mov', 'x0, x19'), 0x225ac: ('lsl', 'w2, w2, #2'),
    0x225b0: ('bl', '0x1fcc4'), 0x225cc: ('ret', ''),
    0x2d5d8: ('ldr', 'w0, [x0, #8]'), 0x2d5dc: ('strb', 'w0, [x6, #1672]'),
    0x2f490: ('ldr', 'x2, [x2, #2456]'), 0x2f494: ('ldr', 'x2, [x2, #56]'),
    0x2f498: ('blr', 'x2'), 0x2f4a4: ('ldr', 'x1, [x0, #64]'),
    0x2f4a8: ('mov', 'w0, #0x4'), 0x2f4ac: ('br', 'x1'),
    0x2fa7c: ('cmn', 'w0, #0x1'), 0x2fa80: ('b.eq', '0x2fa90'),
    0x2fa8c: ('strb', 'w0, [x19, #1]'), 0x2fa94: ('ret', ''),
}


def uint(value, bits):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'expected u{bits}')
    return value


def windows(start, length):
    """Half-open ranges, split at X64 wrap; these are host calculations."""
    uint(start, 64); u32(length)
    if length == 0:
        return []
    end = start + length
    return [(start, end)] if end <= 1 << 64 else [(start, 1 << 64), (0, end & U64)]


def overlaps(start, length, other, other_length):
    return any(a < d and c < b for a, b in windows(start, length)
               for c, d in windows(other, other_length))


def target_buffer(index, control, low, high):
    """Selected X20 formula; descriptor fixture bounds are not firmware guards."""
    u32(index); u32(control)
    upper = s32(index) > 5 and bool(((control & 65535) >> (index & 31)) & 1)
    desc = high if upper else low
    for name in ('payload_offset', 'columns', 'rows', 'bytes'):
        u32(desc[name])
    row = (index - 6) & 0xffffffff if upper else index
    stride = (desc['columns'] << 2) & 0xffffffff
    base = pointer_from_offset(desc['payload_offset'])
    address = (base + s32((stride * row) & 0xffffffff)) & U64
    target = windows(address, 72)
    payload = windows(base, desc['bytes'])
    contained = all(any(c <= a and b <= d for c, d in payload) for a, b in target)
    return dict(column=7 if upper else 6, row=row, address=address, copy_bytes=72,
                row_in_dimensions=row < desc['rows'], copy_within_row=72 <= stride,
                inside_payload=contained)


def forward_copy(memory, destination, source, size_w, host_budget=2048):
    """1fcc4 fixture: signed-W loop guard, forward byte copies, partial writes."""
    uint(destination, 64); uint(source, 64); u32(size_w)
    count = size_w if s32(size_w) > 0 else 0
    if type(host_budget) is not int or not 0 <= count <= host_budget:
        raise ValueError('host copy fixture budget exceeded')
    for index in range(count):
        value = memory[(source + index) & U64]
        uint(value, 8)
        memory[(destination + index) & U64] = value
    return count


def backup_ranges(frame, count):
    uint(frame, 64); uint(count, 8)
    return [((frame + 96) & U64, 160), ((frame + 256) & U64, 72),
            ((frame + 328) & U64, count * 4)]


def copy_cycle(memory, frame, buffers, count_before, count_after, action):
    """Selected six copies only; action stands for opaque intervening effects."""
    if len(buffers) != 3:
        raise ValueError('expected A/B/C fixture pointers')
    for (destination, size), source in zip(backup_ranges(frame, count_before), buffers):
        forward_copy(memory, destination, source, size)
    action(memory)
    for (source, size), destination in zip(backup_ranges(frame, count_after), buffers):
        forward_copy(memory, destination, source, size)


def footprint_survey(data):
    raw = embedded(data)
    tables = {t['key']: t for t in raw['parsed']['entries']}
    counts, grouped = Counter(), {}
    for row in range(tables[0x11111111]['rows']):
        for choices in range(512):
            result = plan(tables, row, choices)
            counts[result['status']] += 1
            if result['status'] != 'complete':
                continue
            selected = result['steps'][3:9]
            key = tuple((s['key'], s['payload_offset'], s['columns'], s['rows']) for s in selected)
            if key not in grouped:
                grouped[key] = dict(first_row=row, first_construction_choices=hex(choices),
                    multiplicity=0, columns=[dict(column=s['index'] + 1, key=hex(s['key']),
                        payload_offset=s['payload_offset'], columns=s['columns'], rows=s['rows'],
                        bytes=s['bytes']) for s in selected])
            grouped[key]['multiplicity'] += 1
    profiles, effects, total = [], {}, Counter()
    global_min, global_max = 1 << 64, 0
    protected = [(0x31408 + DELTA, 48 * 8), (0x318f0 + DELTA, 8), (0x31998 + DELTA, 8)]
    copy_counts = set()
    for profile in grouped.values():
        low, high = profile['columns'][2:4]
        local = Counter(); starts, ends = [], []
        copy_counts.add(profile['columns'][4]['columns'] & 255)
        for index in range(256):
            controls = [0]
            if index > 5 and (index & 31) < 16:
                controls.append(1 << (index & 31))
            for control in controls:
                b = target_buffer(index, control, low, high)
                starts.append(b['address']); ends.append(b['address'] + 72)
                local['u8_control_path_cases'] += 1
                local['outside_payload_cases'] += not b['inside_payload']
                local['overlap_selected_slots_cache_binding_cases'] += any(
                    overlaps(b['address'], 72, address, size) for address, size in protected)
                if leaf_result(index, 0x1ff) != 0xffffffff:
                    local['slot38_accepted_cases'] += 1
                    local['accepted_outside_payload_cases'] += not (
                        b['inside_payload'] and b['row_in_dimensions'] and b['copy_within_row'])
                    desc = low if b['column'] == 6 else high
                    table_key = int(desc['key'], 16); table = tables[table_key]
                    source = raw['block_file'] + table['offset'] + 12 + b['row'] * table['columns'] * 4
                    before, = struct.unpack_from('<I', data, source)
                    effects[(table_key, b['row'])] = dict(key=hex(table_key), payload_row=b['row'],
                        first_word_file=hex(source), byte_file=hex(source + 1),
                        byte_before=hex(data[source + 1]), byte_if_cleared=hex(data[source + 1] & 0xfd),
                        word_before=hex(before), word_if_cleared=hex(before & ~0x200))
        profile['B_footprint'] = dict(local, min_start=hex(min(starts)), max_end_exclusive=hex(max(ends)))
        profiles.append(profile); total.update(local)
        global_min = min(global_min, min(starts)); global_max = max(global_max, max(ends))
    return dict(construction_choices=dict(counts), distinct_six_column_profiles=len(profiles),
        profiles=profiles, compressed_host_path_counts=dict(total),
        all_u8_B_windows_envelope=[hex(global_min), hex(global_max)],
        protected_nominal_windows=[dict(start=hex(a), bytes=n) for a, n in protected],
        copy_count_values=sorted(copy_counts),
        stack_backups=[dict(count=n, third_end=328 + 4*n, inside_448_byte_frame=328 + 4*n <= 448)
                      for n in sorted(copy_counts)],
        preserved_source_byte_effects=[effects[k] for k in sorted(effects)],
        source_effects_all_change_bit1=all(int(v['byte_before'], 16) & 2 for v in effects.values()),
        physical_feasibility_of_scenarios_tested=False,
        excluding_failed_or_partial_record_constructions=True)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    cmd = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root'),
           str(root / 'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for lo, hi in RANGES:
        lines.update(parse_lines(subprocess.check_output(cmd + ['-D', '-z', '-b', 'binary', '-m',
            'aarch64', f'--start-address={lo}', f'--stop-address={hi}', str(Path(path).resolve())], text=True)))
    if set(lines) != {p for lo, hi in RANGES for p in range(lo, hi, 4)}:
        raise ValueError('GNU selected coverage differs')
    relatives = 0
    for pc, (word, op, args) in lines.items():
        if word != struct.unpack_from('<I', data, pc)[0] or op in ('.inst', 'udf'):
            raise ValueError('GNU selected word differs')
        kind, target = flow(word, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, args) != target:
                raise ValueError('GNU relative target differs')
            relatives += 1
    for pc, expected in SELECTED.items():
        if lines[pc][1:] != expected:
            raise ValueError(f'GNU selected operand differs at {pc:#x}')
    bindings = {hex(p): dict(initial_pointer=hex(struct.unpack_from('<Q', data, p)[0]),
        target_if_initial=hex(struct.unpack_from('<Q', data, p)[0] - DELTA))
        for p in (0x31040, 0x31048, 0x314a8)}
    return dict(mode='static_newtime_slot38_buffer_lifecycle_hzc2', sboot_sha256=IMAGES['sboot'][1],
        nominal_delta=hex(DELTA), function=dict(entry='0x22370', frame_bytes=448,
            walk=case_walk(data, [0x22370], 0x22370, 0x225d0)),
        buffers=dict(A='X25, column4 low / column5 upper', B='X20, column6 low / column7 upper',
            C='X19, column8 low / column9 upper',
            upper_condition='signed32(k)>5 and bit(M32[AP0x158609bc]&0xffff,k&31)==1',
            B_formula='SXTW(u32(0x02073600+descriptor.offset)) + SXTW(u32(u32(columns<<2)*row)), X64 wrap',
            row='k on low path; u32(k-6) on upper path'),
        copies=[dict(backup='0x224f4', restore='0x2258c', buffer='A', frame_offset=96, bytes=160),
            dict(backup='0x22504', restore='0x2259c', buffer='B', frame_offset=256, bytes=72),
            dict(backup='0x22518', restore='0x225b0', buffer='C', frame_offset=328,
                 bytes='4*M8[nominal(0x31688)], reloaded separately before backup/restore')],
        copy_helper=dict(entry='0x1fcc4', words=9, forward_byte_order=True,
            signed_W_guard=True, overlap_is_not_memmove=True,
            X0_X1_X2_and_X19_through_X30_not_written=True, partial_stores_not_rolled_back=True),
        intervening_calls=[dict(pc='0x22538', initial_slot=19, effect='selected slot38 byte edit'),
            dict(pc='0x22558', cell='0x31048', W0=4, W1=0, opaque=True),
            dict(pc='0x2256c', cell='0x314a8', W0='k', W1=0, opaque=True),
            dict(pc='0x2257c', cell='0x31048', W0=4, W1='saved bit23 of M32[M64(0x30fc0)+176]', opaque=True)],
        initial_bindings=bindings,
        slot20=dict(code=['0x2f488', '0x2f4b0'], call='0x2f498',
            target='M64[M64[nominal(0x31998)]+56]', arguments=dict(W0='k', W1=0),
            tail='0x2f4ac through initial cell0x31040 with W0=4 after normal return',
            dynamic_method_and_transitive_effects_resolved=False),
        survey=footprint_survey(data),
        conclusions=dict(B_copied_before_mask_check=True, rejected_slot38_result_does_not_abort_wrapper=True,
            B_original_bytes_restored_if_backups_bases_and_counts_preserved=True,
            preservation_of_intermediate_hardware_effects_not_excluded=True,
            whole_transaction_memory_safety_proved=False, global_slot47_alias_exclusion=False),
        conditions=['nominal fixed record base AP0x02073600, complete construction and preserved metadata/payloads',
            'u8 k comes from the five selected initial slot22/slot19/slot38 paths; other callers not covered',
            'construction gate choices and wrapper control bits are separate supplied host possibilities',
            'normal intermediate returns, preserved bases/callee-saved registers and private valid stack',
            'backup bytes and early/late C count preserved; no uncontrolled writer changes restored bytes afterward'],
        limits=['only computed B windows excluded from selected nominal slots/cache/binding',
            'stack destinations, other buffers and opaque callees do not inherit that exclusion',
            '32-bit arithmetic and fixed-base assumptions cannot be replaced with arbitrary live descriptors',
            'the 2752 failed host plans do not prove that partially built records cannot be consumed',
            'slot47 caller/X0 and runtime bindings remain unresolved'],
        gnu=dict(version=subprocess.check_output(cmd + ['--version'], text=True).splitlines()[0],
            words=len(lines), relative_targets=relatives, selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(pc), word=f'{w:08x}', op=op, args=args)
                   for pc, (w, op, args) in sorted(lines.items())],
        firmware_executed=False, qemu_scope_extended=False, incoming_X0_of_slot47_resolved=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        report = inspect(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'inspect_newtime_slot38_buffers_hzc2: {exc}\n')
    print(json.dumps(report, indent=2))
