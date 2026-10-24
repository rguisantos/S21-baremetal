#!/usr/bin/env python3
"""GNU operand/target verification of NEWTIME suffix plus existing prefix."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from check_newtime_gnu import verify as verify_prefix
from inspect_lk_final_edges import flow
from inspect_newtime_record_hzc2 import TEMPLATES, inspect


def verify(path):
    report, prefix = inspect(path), verify_prefix(path)
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for pc, text in TEMPLATES:
        output = subprocess.check_output(command+['-D', '-b', 'binary', '-m', 'aarch64',
            f'--start-address={pc}', f'--stop-address={pc+4*len(text.split())}',
            str(Path(path).resolve())], text=True)
        lines.update(parse_lines(output))
    expected = {pc+i*4: int(w, 16) for pc, text in TEMPLATES for i, w in enumerate(text.split())}
    if set(lines) != set(expected):
        raise ValueError('GNU suffix coverage differs')
    branches = 0
    for pc, (raw, op, operands) in lines.items():
        if raw != expected[pc] or op in ('.inst', 'udf'):
            raise ValueError('GNU suffix instruction differs')
        kind, target = flow(raw, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, operands) != target:
                raise ValueError('GNU suffix target differs')
            branches += 1
    selected = {
        0x196c8: ('strb', 'w1, [x0, #8]'), 0x196ec: ('strb', 'w1, [x0, #12]'),
        0x1970c: ('add', 'x0, x0, #0x20'), 0x19710: ('add', 'x1, x0, #0x180'),
        0x19718: ('str', 'x1, [x0, #32]'), 0x1972c: ('lsl', 'x0, x0, #4'),
        0x19748: ('lsl', 'w0, w0, #28'), 0x1974c: ('sub', 'w0, w0, w1'),
        0x19750: ('lsl', 'w0, w0, #4'), 0x19754: ('add', 'w0, w0, #0x2, lsl #12'),
        0x19758: ('add', 'w0, w0, #0x260'), 0x19774: ('ldr', 'w0, [x0]'),
        0x19778: ('ubfx', 'x0, x0, #31, #1'), 0x1978c: ('cmp', 'w0, #0x8'),
        0x197d8: ('add', 'x1, x1, #0x3'), 0x19808: ('sub', 'x1, x1, #0x3'),
        0x19840: ('mov', 'w0, #0x4'), 0x19858: ('mul', 'w0, w1, w0'),
        0x1985c: ('lsl', 'w0, w0, #2'), 0x198bc: ('str', 'w1, [x0, #4]'),
        0x198dc: ('str', 'w1, [x0, #8]'), 0x198fc: ('str', 'w1, [x0, #12]'),
        0x19968: ('str', 'w1, [x0]'), 0x199f4: ('str', 'w1, [x0, #16]'),
        0x18060: ('stp', 'x0, x1, [x2, #16]'),
        0x18078: ('add', 'x0, x1, w0, sxtw'), 0x18080: ('and', 'x0, x0, #0xfffffffffffffffc'),
        0x18084: ('str', 'x0, [x2, #16]'), 0x1808c: ('b.cs', '0x18094'),
        0x18090: ('b', '0x18090'),
        0x2f6e8: ('cmp', 'w0, #0x1'), 0x2f6f4: ('mov', 'w0, #0x1b'),
        0x2f6f8: ('b', '0x1fdb8'), 0x2f708: ('mov', 'w0, #0x5'),
        0x2f70c: ('b', '0x1fdb8'), 0x2f710: ('sub', 'w0, w0, #0x3'),
        0x2f718: ('b.ls', '0x2f6f0'),
    }
    if any(lines[pc][1:] != text for pc, text in selected.items()):
        raise ValueError('GNU suffix selected operand differs')
    digest = hashlib.sha256(b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))).hexdigest()
    if digest != report['instructions']['suffix_index_sha256']:
        raise ValueError('GNU suffix instruction index differs')
    return dict(mode='GNU_newtime_record_crosscheck', sboot_sha256=report['sboot_sha256'],
        gnu_version=prefix['gnu_version'], prefix_words_matched=prefix['words_matched'],
        new_words_matched=len(lines), total_words_matched=prefix['words_matched']+len(lines),
        new_relative_targets_matched=branches, new_selected_operands_matched=len(selected),
        prefix_instruction_index_sha256=prefix['instruction_index_sha256'], suffix_instruction_index_sha256=digest,
        firmware_executed=False, hardware_gate_or_record_observed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = verify(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'check_newtime_record_gnu: {exc}\n')
    print(json.dumps(result, indent=2))
