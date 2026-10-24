#!/usr/bin/env python3
"""Cross-check selected NEWTIME error/debug instructions with GNU."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_lk_final_edges import flow
from inspect_newtime_error_hzc2 import TEMPLATES, inspect


def verify(path):
    report = inspect(path)
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for pc, template in TEMPLATES:
        output = subprocess.check_output(command+['-D', '-b', 'binary', '-m', 'aarch64',
            f'--start-address={pc}', f'--stop-address={pc+4*len(template.split())}',
            str(Path(path).resolve())], text=True)
        lines.update(parse_lines(output))
    expected = {pc+i*4: int(w, 16) for pc, t in TEMPLATES for i, w in enumerate(t.split())}
    if set(lines) != set(expected):
        raise ValueError('GNU error/debug coverage differs')
    branches = 0
    for pc, (raw, op, operands) in lines.items():
        if raw != expected[pc] or op in ('.inst', 'udf'):
            raise ValueError('GNU error/debug instruction differs')
        kind, target = flow(raw, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, operands) != target:
                raise ValueError('GNU error/debug target differs')
            branches += 1
    selected = {
        0x1fdd8: ('cbz', 'x0, 0x1fdfc'), 0x1fddc: ('bl', '0x21574'),
        0x1fde4: ('bl', '0x20958'), 0x1fdf4: ('bl', '0x204d4'),
        0x1fdf8: ('bl', '0x20200'), 0x1fe1c: ('wfi', ''), 0x1fe28: ('ret', ''),
        0x2096c: ('lsl', 'w1, w1, w0'), 0x20970: ('ldr', 'w2, [x3]'),
        0x20974: ('orr', 'w1, w1, w2'), 0x20978: ('str', 'w1, [x3]'),
        0x20570: ('and', 'w22, w25, #0xf'), 0x20578: ('add', 'w24, w22, w24'),
        0x20580: ('sub', 'w22, w25, w22'), 0x2058c: ('cmp', 'w21, w24'),
        0x20590: ('b.cs', '0x206e4'), 0x20654: ('ldr', 'w0, [x0, x1]'),
        0x20688: ('cmp', 'w25, w26'), 0x20694: ('b.ls', '0x206ac'),
        0x206d8: ('add', 'w21, w21, #0x4'), 0x20720: ('ret', ''),
        0x20220: ('ldr', 'w24, [x0]'), 0x20240: ('ldr', 'w2, [x0], #4'),
        0x20338: ('strb', 'wzr, [x0, #880]'),
        0x204ac: ('cbz', 'x0, 0x20344'), 0x204bc: ('b', '0x20344'),
        0x1ff3c: ('blr', 'x4'), 0x200d8: ('strb', 'w0, [x19, #7]'),
        0x20104: ('ldr', 'w0, [x0, x1]'),
        0x1d438: ('strb', 'wzr, [x3, x2]'),
        0x1d45c: ('strb', 'w0, [x4, #-1]!'),
        0x1d4d4: ('tbz', 'w0, #1, 0x1d4d0'),
        0x1d4f4: ('str', 'w4, [x0]'), 0x1d554: ('strb', 'w4, [x2]'),
    }
    if any(lines[pc][1:] != value for pc, value in selected.items()):
        raise ValueError('GNU error/debug selected operand differs')
    indexed = b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))
    digest = hashlib.sha256(indexed).hexdigest()
    if digest != report['instructions']['index_sha256']:
        raise ValueError('GNU error/debug index differs')
    version = subprocess.check_output(command+['--version'], text=True).splitlines()[0]
    return dict(mode='GNU_newtime_error_debug_crosscheck', gnu_version=version,
        sboot_sha256=report['sboot_sha256'], instruction_index_sha256=digest,
        words_matched=len(lines), relative_targets_matched=branches,
        selected_operands_matched=len(selected), nominal_console_pointers_matched=3,
        strings_matched=len(report['strings']), firmware_executed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = verify(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'check_newtime_error_gnu: {exc}\n')
    print(json.dumps(result, indent=2))
