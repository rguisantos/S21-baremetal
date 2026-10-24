#!/usr/bin/env python3
"""GNU cross-check for the selected NEWTIME parser and first-store prefix."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_bl2_geometry_query_gnu import dump_bytes
from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_hzc2 import TEMPLATES, REGISTRY, embedded, inspect


def verify(path):
    report = inspect(path)
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command+['--version'], text=True).splitlines()[0]

    def run(flag, first, last):
        return subprocess.check_output(command+[flag, '-b', 'binary', '-m', 'aarch64',
            f'--start-address={first}', f'--stop-address={last}', str(Path(path).resolve())], text=True)

    lines = {}
    for pc, template in TEMPLATES:
        lines.update(parse_lines(run('-D', pc, pc+len(template.split())*4)))
    expected = {pc+i*4: int(w, 16) for pc, t in TEMPLATES for i, w in enumerate(t.split())}
    if set(lines) != set(expected):
        raise ValueError('GNU instruction coverage differs')
    branches = 0
    for pc, (raw, op, operands) in lines.items():
        if raw != expected[pc] or op in ('.inst', 'udf'):
            raise ValueError('GNU instruction differs')
        kind, target = flow(raw, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, operands) != target:
                raise ValueError('GNU relative target differs')
            branches += 1
    selected = {
        0x19418: ('str', 'x0, [x29, #136]'), 0x19438: ('b.ge', '0x1944c'),
        0x19440: ('and', 'x0, x0, #0xffffffff'), 0x19444: ('str', 'x0, [x29, #152]'),
        0x194a4: ('ldr', 'w0, [x0, #16]'), 0x194f4: ('ldr', 'x0, [x0, #24]'),
        0x19564: ('sub', 'sp, sp, x0'), 0x195a8: ('bl', '0x1c540'),
        0x19600: ('str', 'x0, [x19]'), 0x19644: ('ldr', 'w1, [x0, #20]'),
        0x19684: ('ldr', 'x0, [x0]'), 0x19690: ('ldr', 'x1, [x29, #136]'),
        0x19694: ('str', 'x1, [x0]'), 0x1c43c: ('str', 'x0, [x4, #16]'),
        0x1c48c: ('str', 'x2, [x9, x8]'), 0x1c4ec: ('str', 'x0, [x3, #24]'),
        0x1c4f8: ('str', 'x4, [x6, #24]'),
        0x1c54c: ('ldr', 'w2, [x0, x2, lsl #2]'),
        0x1c550: ('ldr', 'w0, [x0, x1, lsl #2]'),
        0x1c554: ('orr', 'x0, x0, x2, lsl #32'),
        0x1c5a0: ('ldr', 'x0, [x7, #24]'), 0x1c864: ('cmp', 'x4, x1'),
        0x1ca7c: ('str', 'x1, [x2, #8]'), 0x1c9c4: ('blr', 'x2'),
    }
    if any(lines[pc][1:] != text for pc, text in selected.items()):
        raise ValueError('GNU selected operand differs')
    raw = embedded(data)
    spans = [(REGISTRY, 12*32), (0x3047c, 72), (0x2fd48, 8),
             (raw['source_file'], 0x94), (raw['block_file'], len(raw['raw_block']))]
    spans += [(int(at, 16), 8) for at in raw['copy']['literal_offsets']]
    for pc, size in spans:
        if dump_bytes(run('-s', pc, pc+size), pc, size) != data[pc:pc+size]:
            raise ValueError('GNU selected data differs')
    packed = b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))
    digest = hashlib.sha256(packed).hexdigest()
    if digest != report['instructions']['index_sha256']:
        raise ValueError('GNU instruction index differs')
    return dict(mode='GNU_newtime_crosscheck', sboot_sha256=IMAGES['sboot'][1],
        gnu_version=version, words_matched=len(lines), relative_targets_matched=branches,
        selected_operands_matched=len(selected), data_spans_matched=len(spans),
        complete_newtime_bytes_matched=len(raw['raw_block']), instruction_index_sha256=digest,
        firmware_executed=False, phone_record_or_memory_map_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = verify(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'check_newtime_gnu: {exc}\n')
    print(json.dumps(result, indent=2))
