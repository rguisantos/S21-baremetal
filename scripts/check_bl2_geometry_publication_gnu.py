#!/usr/bin/env python3
"""GNU verification of the second NEWTIME publication path and existing prefix."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_lk_final_edges import flow
from inspect_bl2_geometry_publication import TEMPLATES, inspect


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
        raise ValueError('GNU publication coverage differs')
    branches = 0
    for pc, (raw, op, operands) in lines.items():
        if raw != expected[pc] or op in ('.inst', 'udf'):
            raise ValueError('GNU publication instruction differs')
        kind, target = flow(raw, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, operands) != target:
                raise ValueError('GNU publication target differs')
            branches += 1
    selected = {
        0x1dcac: ('mov', 'w23, w1'), 0x1dcb0: ('mov', 'w24, w2'),
        0x1ea1c: ('ldr', 'w0, [x22, #3112]'), 0x1ea20: ('add', 'x20, x20, #0x408'),
        0x1ea28: ('add', 'w0, w0, #0x1'), 0x1ea2c: ('add', 'x19, x19, #0x688'),
        0x1ea30: ('str', 'w0, [x22, #3112]'), 0x1ea38: ('ldr', 'x3, [x20, #264]'),
        0x1ea3c: ('str', 'w0, [x1]'), 0x1ea44: ('ldr', 'x0, [x19, #752]'),
        0x1ea48: ('blr', 'x3'), 0x1ea4c: ('ldr', 'x0, [x20, #136]'),
        0x1ea54: ('ldr', 'x2, [x20, #192]'),
        0x2f6cc: ('str', 'x0, [x1]'), 0x2f6d8: ('ldr', 'x0, [x1, #752]'),
        0x2f6dc: ('ldr', 'x1, [x1, #784]'), 0x2f6e0: ('ldr', 'x1, [x1, #40]'),
        0x2f6e4: ('blr', 'x1'),
        0x19418: ('str', 'x0, [x29, #136]'),
        0x19684: ('ldr', 'x0, [x0]'), 0x19690: ('ldr', 'x1, [x29, #136]'),
        0x19694: ('str', 'x1, [x0]'),
        0x2ef98: ('ldr', 'w0, [x0]'), 0x2ef9c: ('tbnz', 'w0, #31, 0x2efec'),
        0x2efd0: ('ldr', 'w2, [x1]'), 0x2efd8: ('str', 'w2, [x1]'),
        0x2efe8: ('str', 'w0, [x1]'),
        0x2d7e0: ('ldr', 'x0, [x0]'), 0x2d7e4: ('str', 'x0, [x19, #752]'),
    }
    if any(lines[pc][1:] != value for pc, value in selected.items()):
        raise ValueError('GNU selected publication operand differs')
    index = b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))
    digest = hashlib.sha256(index).hexdigest()
    if digest != report['instructions']['index_sha256']:
        raise ValueError('GNU publication instruction index differs')
    return dict(mode='GNU_bl2_geometry_publication_crosscheck',
        gnu_version=subprocess.check_output(command+['--version'], text=True).splitlines()[0],
        sboot_sha256=report['sboot_sha256'], instruction_index_sha256=digest,
        words_matched=len(lines), relative_targets_matched=branches,
        selected_operands_matched=len(selected), nominal_pointers_matched=len(report['nominal_pointers']),
        firmware_executed=False, runtime_publication_observed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = verify(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'check_bl2_geometry_publication_gnu: {exc}\n')
    print(json.dumps(result, indent=2))
