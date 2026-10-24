#!/usr/bin/env python3
"""Independent GNU AArch64/Thumb text check of the ACPM witnesses."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from check_bl2_geometry_query_gnu import dump_bytes
from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_acpm_handshake_hzc2 import A64, THUMB, LITERALS, inspect, thumb_literal, thumb_target
from inspect_descriptor_provenance import copy_loop
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow


def parse_thumb(output):
    result = {}
    for line in output.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4}(?: [0-9a-f]{4})?)\s+([^\s]+)\s*(.*)$', line)
        if not m:
            continue
        pc, raw, op, operands = m.groups()
        pc = int(pc, 16)
        if pc in result:
            raise ValueError('duplicate GNU Thumb PC')
        result[pc] = (b''.join(struct.pack('<H', int(h, 16)) for h in raw.split()), op, operands)
    return result


def verify(sboot, dts):
    report = inspect(sboot, dts)
    data = read_exact(sboot, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command+['--version'], text=True).splitlines()[0]

    def run(flag, arch, first, last):
        args = command+[flag, '-b', 'binary', '-m', arch]
        if arch == 'arm':
            args += ['-M', 'force-thumb']
        return subprocess.check_output(args+[f'--start-address={first}', f'--stop-address={last}',
                                             str(Path(sboot).resolve())], text=True)

    a64, thumb = {}, {}
    for pc, template in A64:
        a64.update(parse_lines(run('-D', 'aarch64', pc, pc+4*len(template.split()))))
    for pc, template in THUMB:
        thumb.update(parse_thumb(run('-D', 'arm', pc, pc+2*len(template.split()))))
    expected = {int(pc, 16): int(raw, 16) for pc, raw in report['a64_words'].items()}
    if set(a64) != set(expected):
        raise ValueError('GNU AArch64 coverage differs')
    branches = 0
    for pc, (raw, op, operands) in a64.items():
        if raw != expected[pc] or op in ('.inst', 'udf'):
            raise ValueError('GNU AArch64 word differs')
        kind, target = flow(raw, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, operands) != target:
                raise ValueError('GNU AArch64 target differs')
            branches += 1
    covered, index = set(), bytearray()
    thumb_branches, literals = 0, 0
    for pc, (raw, op, operands) in sorted(thumb.items()):
        if raw != data[pc:pc+len(raw)] or op in ('.short', '.word', 'udf'):
            raise ValueError('GNU Thumb instruction differs')
        span = set(range(pc, pc+len(raw), 2))
        if covered & span:
            raise ValueError('GNU Thumb overlap')
        covered |= span
        index += struct.pack('<IB', pc, len(raw))+raw
        target = thumb_target(data, pc)
        is_branch = op in ('bl', 'b.n', 'beq.n', 'bne.n', 'bcc.n', 'cbz', 'cbnz')
        if (target is not None) != is_branch:
            raise ValueError('GNU Thumb branch classification differs')
        if target is not None:
            textual = int(operands.split('@')[0].split(',')[-1].strip(), 0)
            if target != textual:
                raise ValueError('GNU Thumb target differs')
            thumb_branches += 1
        literal = re.fullmatch(r'r([0-7]), \[pc, #\d+\]\s*@ \(0x([0-9a-f]+)\)', operands)
        if literal:
            if thumb_literal(data, pc, int(literal[1]))[0] != int(literal[2], 16):
                raise ValueError('GNU Thumb literal address differs')
            literals += 1
    if covered != {int(pc, 16) for pc in report['thumb_halfwords']}:
        raise ValueError('GNU Thumb halfword coverage differs')
    selected_thumb = {
        0x3826a: ('msr', 'MSP, r0'), 0x3826e: ('bl', '0x38c90'),
        0x38cb2: ('ldr', 'r3, [r3, #4]'), 0x38cb4: ('blx', 'r3'),
        0x38e58: ('ldr', 'r3, [r3, #0]'), 0x38e5a: ('blx', 'r3'),
        0x38e7c: ('ldrb', 'r2, [r3, r2]'), 0x38e80: ('ldr', 'r3, [r3, #4]'),
        0x38e90: ('blx', 'r8'), 0x39b52: ('str', 'r3, [r0, #0]'),
        0x399b8: ('str', 'r1, [r4, #4]'), 0x56e1e: ('bl', '0x56ee0'),
        0x56ef2: ('str', 'r2, [r3, #0]'), 0x56ef6: ('ldr', 'r3, [r2, #0]'),
        0x56ef8: ('cmp', 'r3, #0'), 0x56efa: ('bne.n', '0x56ef6'),
        0x56f00: ('str', 'r4, [r3, #0]'), 0x56f02: ('movw', 'r3, #6144'),
        0x56f06: ('adds', 'r2, r4, r3'), 0x56f0a: ('str', 'r2, [r3, #0]'),
        0x3f558: ('movw', 'r2, #42496'), 0x3f55c: ('movt', 'r2, #3'),
        0x3f560: ('ldr', 'r1, [r2, #0]'), 0x3f56a: ('ldr', 'r0, [r2, #0]'),
        0x3f576: ('cmp', 'r1, r2'), 0x3f584: ('cmp', 'r0, r2'),
    }
    for pc, expected_text in selected_thumb.items():
        _, op, operands = thumb[pc]
        if (op, operands.split('@')[0].strip()) != expected_text:
            raise ValueError(f'GNU selected Thumb operand differs at {pc:#x}')
    selected_a64 = {
        0x179a8: ('str', 'wzr, [x20]'), 0x179e4: ('ldr', 'w0, [x20]'),
        0x179f0: ('cbz', 'w0, 0x179e4'), 0x179f8: ('ldr', 'w0, [x21]'),
        0x17a08: ('add', 'w1, w0, w1'), 0x17a0c: ('str', 'x1, [x19, #8]'),
        0x17a50: ('str', 'wzr, [x21]'), 0x17fe8: ('str', 'x2, [x4, #1312]'),
    }
    if any(a64[pc][1:] != text for pc, text in selected_a64.items()):
        raise ValueError('GNU selected AArch64 operand differs')
    spans = [(pc, 4) for pc in LITERALS]+[(0x38000, 8)]
    for pc in (0x161b0, 0x16228, 0x16250):
        spans += [(int(v, 16), 8) for v in copy_loop(data, pc, 16)['literal_offsets']]
    for pc, size in spans:
        if dump_bytes(run('-s', 'aarch64', pc, pc+size), pc, size) != data[pc:pc+size]:
            raise ValueError('GNU literal bytes differ')
    return dict(mode='GNU_AArch64_Thumb_crosscheck', sboot_sha256=report['input']['sha256'],
        dts_sha256=report['public_dts']['sha256'], gnu_version=version,
        a64_words_matched=len(a64), a64_relative_targets_matched=branches,
        thumb_instructions_matched=len(thumb), thumb_halfwords_matched=len(covered),
        thumb_relative_targets_matched=thumb_branches, thumb_literal_xrefs_matched=literals,
        selected_operands_matched=len(selected_thumb)+len(selected_a64), literal_spans_matched=len(spans),
        thumb_instruction_index_sha256=hashlib.sha256(index).hexdigest(),
        firmware_executed=False, hardware_alias_or_handshake_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    parser.add_argument('dts')
    args = parser.parse_args()
    try:
        result = verify(args.sboot, args.dts)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'check_acpm_handshake_gnu: {exc}\n')
    print(json.dumps(result, indent=2))
