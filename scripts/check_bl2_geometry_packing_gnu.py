#!/usr/bin/env python3
"""GNU cross-check of BL2 marker/reload, packing, query and size witnesses."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_lk_final_edges import flow
from inspect_bl2_geometry_packing import TEMPLATES, inspect


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
        raise ValueError('GNU packing coverage differs')
    branches = 0
    for pc, (raw, op, operands) in lines.items():
        if raw != expected[pc] or op in ('.inst', 'udf'):
            raise ValueError('GNU packing instruction differs')
        kind, target = flow(raw, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, operands) != target:
                raise ValueError('GNU packing target differs')
            branches += 1
    selected = {
        0x1e2c0: ('mov', 'x0, #0xcafe'), 0x1e2c4: ('str', 'x0, [x21, #752]'),
        0x1d83c: ('ldr', 'x0, [x19, #248]'), 0x1d844: ('ldr', 'x1, [x19, #336]'),
        0x1d860: ('ldr', 'x0, [x0, #856]'), 0x2d598: ('cmp', 'w0, w1'),
        0x2d59c: ('b.le', '0x2d5a8'), 0x2d7e0: ('ldr', 'x0, [x0]'),
        0x2d7e4: ('str', 'x0, [x19, #752]'),
        0x2f168: ('str', 'xzr, [x0, x1, lsl #3]'),
        0x2f1dc: ('str', 'w0, [x26, x10, lsl #2]'),
        0x2f1e4: ('cbnz', 'w0, 0x2f1f8'),
        0x2f204: ('mov', 'w21, #0x3'), 0x2f280: ('csinc', 'w21, w21, wzr, ne'),
        0x2f2a8: ('bfi', 'x4, x0, #4, #4'),
        0x2f2c0: ('bfi', 'x5, x0, #16, #4'),
        0x2f2d4: ('bfi', 'x4, x0, #20, #4'),
        0x2f2f0: ('bfi', 'x5, x4, #24, #4'),
        0x2f304: ('bfi', 'x4, x0, #28, #4'),
        0x2f320: ('bfi', 'x4, x0, #8, #8'),
        0x2f33c: ('bfi', 'x4, x0, #32, #8'),
        0x2f358: ('bfi', 'x4, x0, #40, #8'),
        0x2f36c: ('bfi', 'x4, x0, #48, #4'),
        0x2f3e4: ('mov', 'w2, #0x31'), 0x2f3ec: ('mov', 'w1, #0x3'),
        0x2f400: ('bfi', 'x1, x0, #56, #4'),
        0x2f424: ('and', 'x0, x0, #0xfffffffffffff'),
        0x2f440: ('b.gt', '0x2f450'),
        0x2f448: ('and', 'x0, x0, #0xf0ffffffffffffff'),
        0x2f46c: ('strb', 'w21, [x22, #689]'),
        0x2e3dc: ('ubfx', 'x0, x0, #20, #4'),
        0x284d8: ('ldr', 'w3, [x0, #12]'),
        0x2cb04: ('ldr', 'x1, [x1, #752]'),
    }
    if any(lines[pc][1:] != value for pc, value in selected.items()):
        raise ValueError('GNU selected packing operand differs')
    index = b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))
    digest = hashlib.sha256(index).hexdigest()
    if digest != report['instructions']['index_sha256']:
        raise ValueError('GNU packing instruction index differs')
    return dict(mode='GNU_bl2_geometry_packing_crosscheck',
        gnu_version=subprocess.check_output(command+['--version'], text=True).splitlines()[0],
        sboot_sha256=report['sboot_sha256'], instruction_index_sha256=digest,
        words_matched=len(lines), relative_targets_matched=branches,
        selected_operands_matched=len(selected), nominal_pointers_matched=len(report['nominal_bindings']),
        firmware_executed=False, runtime_responses_observed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = verify(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'check_bl2_geometry_packing_gnu: {exc}\n')
    print(json.dumps(result, indent=2))
