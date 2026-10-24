#!/usr/bin/env python3
"""GNU text and literal checks for the selected boot-metadata witnesses."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_bl2_geometry_query_gnu import dump_bytes
from check_bl2_geometry_record_gnu import text_wide
from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_boot_metadata_hzc2 import RANGES, inspect
from inspect_lk_final_edges import flow


def verify(path):
    report = inspect(path)
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command+['--version'], text=True).splitlines()[0]

    def run(flag, first, last):
        return subprocess.check_output(command+[flag, '-b', 'binary', '-m', 'aarch64',
            f'--start-address={first}', f'--stop-address={last}', str(Path(path).resolve())], text=True)

    lines = {}
    for first, last in RANGES:
        lines.update(parse_lines(run('-D', first, last)))
    expected = {int(pc, 16): int(raw, 16) for pc, raw in report['words'].items()}
    if set(lines) != set(expected):
        raise ValueError('GNU coverage differs')
    branches = 0
    for pc, (raw, op, operands) in lines.items():
        if raw != expected[pc] or op in ('.inst', 'udf'):
            raise ValueError('GNU instruction differs')
        kind, target = flow(raw, pc)
        textual = direct_target(op, operands)
        if kind in ('b', 'bl', 'conditional'):
            if textual != target:
                raise ValueError('GNU relative target differs')
            branches += 1
        elif textual is not None:
            raise ValueError('unclassified GNU target')
    selected = {
        0x17fbc: ('adrp', 'x4, 0x30000'), 0x17fc0: ('add', 'x3, x4, #0x520'),
        0x17fc4: ('add', 'x3, x3, #0x2c0'),
        0x17a00: ('mov', 'w1, #0x9000'), 0x17a04: ('movk', 'w1, #0x203, lsl #16'),
        0x17a08: ('add', 'w1, w0, w1'), 0x17a0c: ('str', 'x1, [x19, #8]'),
        0x179f8: ('ldr', 'w0, [x21]'),
        0x17fcc: ('add', 'x2, x1, #0x1, lsl #12'),
        0x17fe0: ('add', 'x2, x2, #0x800'), 0x17fe8: ('str', 'x2, [x4, #1312]'),
        0x1dcbc: ('str', 'x3, [x0, #784]'),
        0x2f6d8: ('ldr', 'x0, [x1, #752]'), 0x2f6dc: ('ldr', 'x1, [x1, #784]'),
        0x2f6e0: ('ldr', 'x1, [x1, #40]'), 0x2f6e4: ('blr', 'x1'),
        0x19418: ('str', 'x0, [x29, #136]'),
        0x1967c: ('adrp', 'x0, 0x30000'), 0x19680: ('add', 'x0, x0, #0x520'),
        0x19684: ('ldr', 'x0, [x0]'), 0x19690: ('ldr', 'x1, [x29, #136]'),
        0x19694: ('str', 'x1, [x0]'),
        0x149830: ('adrp', 'x2, 0xcd3000'), 0x149834: ('mov', 'w1, w1'),
        0x149838: ('add', 'x2, x2, #0x568'),
        0x14983c: ('str', 'x1, [x2, w0, uxtw #3]'),
        0x149850: ('ldr', 'x0, [x1, w0, uxtw #3]'),
        0xee6a4: ('mov', 'w1, #0x64'), 0xee6a8: ('mov', 'w0, #0x0'),
        0xee6d0: ('mov', 'w0, #0x1'), 0xeec1c: ('mov', 'w0, #0x2'),
        0xeed3c: ('mov', 'w0, #0x2'), 0x111c40: ('mrs', 'x0, cntpct_el0'),
    }
    for base in (0xee6b0, 0xeebfc, 0xeed1c):
        selected[base+16] = ('add', 'x19, x19, x0')
    for pc in (0x1452b4, 0x1452cc, 0x1452e4):
        selected[pc] = ('mov', 'x1, x0')
    if any(lines[pc][1:] != value for pc, value in selected.items()):
        raise ValueError('GNU selected operand differs')
    producers = (
        ((0x179e8, 0x179ec), 21, 0x15900108),
        ((0x19478, 0x1947c), 1, 0x11111111),
        ((0xee6c4, 0xee6cc, 0xee6d4, 0xee6d8), 1, 0x20c49ba5e353f7cf),
    )
    for offsets, register, value in producers:
        if text_wide(lines, offsets, register) != value:
            raise ValueError('GNU selected wide value differs')
    literals = [(0x30520, struct.pack('<Q', 0x2075600)),
                (0x30808, struct.pack('<Q', 0x21033fc)), (0x2fd48, b'NEWTIME\0')]
    literals += [(int(row['format_offset'], 16), row['format'].encode()+b'\0')
                 for row in report['bootstat']['formats']]
    for address, expected_data in literals:
        # The shared strict dump reader accepts complete four-byte groups.
        size = (len(expected_data)+3) & ~3
        actual = dump_bytes(run('-s', address, address+size), address, size)
        if actual[:len(expected_data)] != expected_data:
            raise ValueError('GNU literal differs')
    packed = b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))
    return dict(mode='GNU_text_crosscheck', sboot_sha256=report['input']['sha256'],
                gnu_version=version, words_matched=len(lines), relative_targets_matched=branches,
                selected_operands_matched=len(selected), wide_producers_matched=len(producers),
                pointers_and_strings_matched=len(literals),
                instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
                firmware_executed=False, live_record_destination_verified=False,
                counter_or_register_values_observed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = verify(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'check_boot_metadata_gnu: {exc}\n')
    print(json.dumps(result, indent=2))
