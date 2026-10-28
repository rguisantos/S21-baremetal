#!/usr/bin/env python3
"""Static channel-pointer writer and conditional archive-descriptor provenance.

No firmware instructions are executed. The fresh-directory examples below
are arithmetic models with explicit preservation/normal-return conditions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_consumers_hzc2 import branch_candidates, occurrences
from inspect_newtime_copy_arguments_hzc2 import DELTA, assess_source

CHANNEL_BASE = 0x02075a00
CHANNEL_SIZE = 0xfb0
ARCHIVE_BASE = 0x0223f000
CURSOR_LIMIT = 0x02257fdf
NAMES = ('phy_trn_ch0', 'phy_trn_ch1', 'phy_trn_ch2', 'phy_trn_ch3')
RANGES = (
    (0x1f400, 0x1f424), (0x1f9e8, 0x1fa0c), (0x1fc58, 0x1fcc4),
    (0x1fdb8, 0x1fe2c), (0x21cd4, 0x22014), (0x22098, 0x221bc),
    (0x23ec4, 0x23ee0), (0x2d468, 0x2d4a0), (0x2f724, 0x2f7f4),
)


def registration_prefix(cursor, count, length):
    """Deductions through the first bounds-error request, without calling it.

    Name-copy/duplicate-check success, stable archive base and valid accesses
    are conditions. Metadata writes precede the end/count comparisons.
    This function does not claim bounds safety or model the error handler.
    """
    if any(type(v) is not int or not 0 <= v < 1 << 32 for v in (cursor, count, length)):
        raise ValueError('cursor, count and length require unsigned W bits')
    next_cursor = (cursor + length) & 0xffffffff
    next_count = (count + 1) & 0xffffffff
    first_error = ('cursor_limit_at_0x21e30' if next_cursor > CURSOR_LIMIT else
                   'count_limit_at_0x21e48' if next_count > 15 else None)
    return dict(name_address=ARCHIVE_BASE + 0x34 + 24 * count,
                source_field_address=ARCHIVE_BASE + 0x44 + 24 * count,
                length_field_address=ARCHIVE_BASE + 0x48 + 24 * count,
                stored_source=cursor, stored_length=length,
                stored_next_cursor=next_cursor, stored_next_count=next_count,
                metadata_written_before_bounds_error=True, first_bounds_error_request=first_error,
                valid_accesses_or_normal_error_return_proved=False)


def fresh_archive(include_characterization=False):
    if type(include_characterization) is not bool:
        raise ValueError('explicit boolean profile required')
    entries = [('header', 0x1a0, None)]
    if include_characterization:
        entries.append(('charac_lvcc', 52, 0x021ab6a4))
    entries.extend((name, CHANNEL_SIZE, CHANNEL_BASE + i * CHANNEL_SIZE) for i, name in enumerate(NAMES))
    cursor, count, result = ARCHIVE_BASE, 0, []
    for name, length, source in entries:
        step = registration_prefix(cursor, count, length)
        if step['first_bounds_error_request'] is not None:
            raise ValueError('fresh conditional profile reached an error request')
        result.append(dict(name=name, index=count, archive_address=hex(cursor), bytes=length,
                           copy_source=None if source is None else hex(source),
                           action='register existing header' if source is None else 'register then copy',
                           archive_source_assessment=assess_source(cursor, length),
                           registration=step))
        cursor, count = step['stored_next_cursor'], step['stored_next_count']
    return dict(profile='fresh_with_characterization' if include_characterization else 'fresh_without_characterization',
                initial_cursor=hex(ARCHIVE_BASE), final_cursor=hex(cursor), final_count=count,
                entries=result, conditional_model_only=True,
                conditions=['initial archive base and table/cell bindings preserved',
                            '0x21ec8 starts the directory and registers header successfully',
                            'optional characterization record is the selected distinct-name path',
                            'no other registration, metadata mutation or alias between selected calls',
                            'callees return normally and preserve required state; valid memory accesses'],
                runtime_directory_observed=False)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    scan = {target: branch_candidates(data, target, last=0xec000)
            for target in (0x2d468, 0x2f724, 0x21cd4, 0x21d3c, 0x21dc0, 0x22098, 0x22120)}
    pcs = {p for a, b in RANGES for p in range(a, b, 4)}
    pcs |= {int(c['pc'], 16) for calls in scan.values() for c in calls}
    runs = []
    for p in sorted(pcs):
        if runs and runs[-1][1] == p:
            runs[-1][1] = p + 4
        else:
            runs.append([p, p + 4])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root'),
               str(root / 'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command + ['--version'], text=True).splitlines()[0]
    lines = {}
    for a, b in runs:
        lines.update(parse_lines(subprocess.check_output(command + [
            '-D', '-b', 'binary', '-m', 'aarch64', f'--start-address={a}',
            f'--stop-address={b}', str(Path(path).resolve())], text=True)))
    if set(lines) != pcs:
        raise ValueError('GNU coverage differs')
    relative = 0
    for p, (word, op, args) in lines.items():
        if word != struct.unpack_from('<I', data, p)[0] or op in ('.inst', 'udf'):
            raise ValueError(f'GNU instruction differs at {p:#x}')
        kind, target = flow(word, p)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, args) != target:
                raise ValueError('GNU branch target differs')
            relative += 1
        elif direct_target(op, args) is not None:
            raise ValueError('unclassified GNU branch')
    selected = {
        0x2d468: ('adrp', 'x0, 0x31000'), 0x2d46c: ('mov', 'x1, #0x5a00'),
        0x2d470: ('add', 'x0, x0, #0x688'), 0x2d474: ('movk', 'x1, #0x207, lsl #16'),
        0x2d478: ('str', 'x1, [x0, #640]'), 0x2d47c: ('add', 'x1, x1, #0xfb0'),
        0x2d480: ('str', 'x1, [x0, #648]'), 0x2d484: ('add', 'x1, x1, #0xfb0'),
        0x2d488: ('str', 'x1, [x0, #656]'), 0x2d48c: ('add', 'x1, x1, #0xfb0'),
        0x2d490: ('str', 'x1, [x0, #664]'), 0x2d494: ('add', 'x1, x1, #0xfb0'),
        0x2d498: ('str', 'x1, [x0, #672]'), 0x2d49c: ('ret', ''),
        0x2f724: ('adrp', 'x0, 0x31000'), 0x2f730: ('ldr', 'x0, [x0, #1176]'),
        0x2f73c: ('blr', 'x0'), 0x2f740: ('bl', '0x2e4fc'),
        0x2f744: ('cbz', 'w0, 0x2f758'), 0x2f754: ('b', '0x2f7f4'),
        0x2f7d4: ('mov', 'w2, #0xfb0'), 0x2f7dc: ('bl', '0x1f9e8'),
        0x2f7e0: ('ldr', 'x0, [x20], #8'), 0x2f7f0: ('b.ne', '0x2f7d0'),
        0x21d54: ('mov', 'x23, #0x18'), 0x21d78: ('add', 'x0, x0, #0x14'),
        0x21d7c: ('bl', '0x1fc9c'), 0x21d98: ('cmp', 'w20, #0xf'),
        0x21de4: ('mov', 'w2, #0x10'), 0x21df4: ('add', 'x0, x0, #0x34'),
        0x21e00: ('ldp', 'w3, w1, [x0, #44]'),
        0x21e10: ('stp', 'w3, w20, [x2, #68]'),
        0x21e14: ('add', 'w20, w3, w20'), 0x21e18: ('stp', 'w20, w1, [x0, #44]'),
        0x21e1c: ('mov', 'w0, #0x7fdf'), 0x21e20: ('movk', 'w0, #0x225, lsl #16'),
        0x21e24: ('cmp', 'w20, w0'), 0x21e28: ('b.ls', '0x21e34'),
        0x21e30: ('bl', '0x1fdb8'), 0x21e3c: ('cmp', 'w0, #0xf'),
        0x21e48: ('bl', '0x1fdb8'), 0x21e6c: ('ldr', 'w0, [x0, #68]'),
        0x21edc: ('ldr', 'x0, [x0, #2936]'), 0x21f64: ('str', 'wzr, [x0, #48]'),
        0x21e88: ('mov', 'x0, #0xf000'), 0x21e94: ('movk', 'x0, #0x223, lsl #16'),
        0x21f60: ('mov', 'w1, #0xf000'), 0x21f68: ('movk', 'w1, #0x223, lsl #16'),
        0x21f6c: ('str', 'w1, [x0, #44]'), 0x21f74: ('mov', 'w1, #0x1a0'),
        0x21f7c: ('add', 'x0, x0, #0x2ae'), 0x22004: ('ldp', 'w1, w2, [x0, #16]'),
        0x21f80: ('b', '0x21dc0'), 0x21e8c: ('mov', 'w2, #0x1a0'),
        0x2213c: ('mov', 'w2, #0xfb0'), 0x22150: ('mov', 'w2, #0xfb0'),
        0x22160: ('mov', 'w2, #0xfb0'), 0x22170: ('mov', 'w2, #0xfb0'),
        0x22140: ('add', 'x0, x19, #0x1f'), 0x22154: ('add', 'x0, x19, #0x2b'),
        0x22164: ('add', 'x0, x19, #0x37'), 0x22174: ('add', 'x0, x19, #0x43'),
        0x1fe1c: ('wfi', ''), 0x1fe28: ('ret', ''),
    }
    for p, expected in selected.items():
        if lines[p][1:] != expected:
            raise ValueError(f'operand differs at {p:#x}')
    cells = {p: struct.unpack_from('<Q', data, p)[0]
             for p in (0x30b78, 0x31488, 0x31498, 0x31580, 0x31908, 0x31910, 0x31918, 0x31920, 0x31928)}
    if cells[0x30b78] != ARCHIVE_BASE or cells[0x31498] != DELTA + 0x2d468 or cells[0x31488] != DELTA + 0x2f724:
        raise ValueError('initial nominal binding differs')
    names = []
    for i, name in enumerate(NAMES):
        off = 0x302cd + i * 12
        if data[off:off + len(name) + 1] != name.encode() + b'\0':
            raise ValueError('channel label differs')
        names.append(dict(name=name, file=hex(off)))
    packed = b''.join(struct.pack('<II', p, lines[p][0]) for p in sorted(lines))
    return dict(mode='static_newtime_channel_origins', schema_version=1,
        sboot_sha256=IMAGES['sboot'][1], sboot_bytes=len(data), nominal_delta=hex(DELTA),
        initial_cells={hex(p): hex(v) for p, v in cells.items()}, labels=names,
        initializer=dict(entry='0x2d468', table='0x31408', index=18, cell='0x31498',
            conditional_caller=dict(entry='0x2f724', load='0x2f730', call='0x2f73c',
                                    caller_table_index=16, caller_pointer_cell='0x31488'),
            writes=[dict(pc=hex(0x2d478 + i * 8), cell_file=hex(0x31908 + i * 8),
                         cell_nominal=hex(DELTA + 0x31908 + i * 8), value=hex(CHANNEL_BASE + CHANNEL_SIZE * i))
                    for i in range(5)],
            writes_are_nominal_static_not_observed=True, all_other_writers_excluded=False),
        channel_copy_spans=[dict(channel=i, source=hex(CHANNEL_BASE + i * CHANNEL_SIZE),
                                 end_exclusive=hex(CHANNEL_BASE + (i + 1) * CHANNEL_SIZE),
                                 bytes=CHANNEL_SIZE, assessment=assess_source(CHANNEL_BASE + i * CHANNEL_SIZE, CHANNEL_SIZE))
                            for i in range(4)],
        zeroing_path=dict(gate_call='0x2f740 -> 0x2e4fc, opaque here',
            W0_zero='clear four buffers through current 0x31908/10/18/20, 4016 bytes each',
            W0_nonzero='skip this clearing branch; initializer was called before the gate',
            intervening_memory_preservation_is_condition=True),
        directory=dict(base_cell_file='0x30b78', initial_base=hex(ARCHIVE_BASE),
            cursor_u32_offset=44, count_u32_offset=48, name_offset=52,
            record_stride=24, name_bytes=16, source_u32_offset=68, length_u32_offset=72,
            source_and_length_offsets_relative_to_name=[16, 20],
            lookup_scans_slots=15, lookup_uses_count_to_bound_scan=False,
            duplicate_check_uses_current_count=True, runtime_directory_observed=False,
            metadata_and_cursor_written_before_bounds_checks=True, cursor_arithmetic_bits=32,
            end_comparison_unsigned_limit=hex(CURSOR_LIMIT), accepted_count_upper_bound=15,
            error_request='0x1fdb8; WFI then a syntactic RET exists, no no-return proof',
            guard_proves_no_overflow_or_valid_source=False),
        conditional_fresh_profiles=[fresh_archive(False), fresh_archive(True)],
        direct_reference_scan=dict(first='0x16000', end_exclusive='0xec000',
            sites={hex(t): calls for t, calls in scan.items()}, reachability_proved=False),
        nominal_pointer_occurrences={hex(t): [hex(p) for p in occurrences(data, struct.pack('<Q', DELTA + t))]
                                     for t in (0x2d468, 0x2f724)},
        gnu=dict(version=version, words=len(lines), relative_targets=relative,
                 selected_operands=len(selected), instruction_index_sha256=hashlib.sha256(packed).hexdigest()),
        ranges=[dict(first=hex(a), end_exclusive=hex(b), sha256=hashlib.sha256(data[a:b]).hexdigest()) for a, b in RANGES],
        witnesses=[dict(pc=hex(p), word=f'{w:08x}', op=op, args=args) for p, (w, op, args) in sorted(lines.items())],
        limits=['initial table/base bindings and their preservation are conditions, not runtime values',
                'only selected writer found; no complete alias, copy or external-writer exclusion',
                'fresh directory examples are conditional arithmetic deductions, not firmware execution',
                'preexisting metadata, intervening registrations and error-handler effects remain open',
                'no transport of cell 0x31580 or incoming X0 of its slot47 dispatch established'],
        transport_of_cell_found=False, incoming_X0_resolved=False,
        firmware_executed=False, qemu_scope_extended=False, physical_device_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(result, indent=2))
