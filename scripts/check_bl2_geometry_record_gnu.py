#!/usr/bin/env python3
"""Independent GNU text checks for record addresses, fields and copy literals."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from check_bl2_geometry_query_gnu import dump_bytes
from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_bl2_geometry_record import RANGES, inspect
from inspect_lk_final_edges import flow


def text_wide(lines, offsets, register):
    value = None
    for pc in offsets:
        _, op, operands = lines[pc]
        m = re.fullmatch(r'x'+str(register)+r', #(0x[0-9a-f]+)(?:, lsl #(\d+))?', operands)
        if m is None or (value is None and op != 'mov') or (value is not None and op != 'movk'):
            raise ValueError('unsupported GNU move-wide text')
        literal, shift = m.groups()
        shift = 0 if shift is None else int(shift)
        immediate = int(literal, 0) << shift
        value = immediate if value is None else (value & ~(65535 << shift)) | immediate
    if value is None:
        raise ValueError('empty GNU producer sequence')
    return value


def verify(path):
    report = inspect(path)
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command+['--version'], text=True).splitlines()[0]

    def run(flag, a, b):
        return subprocess.check_output(command+[flag, '-b', 'binary', '-m', 'aarch64',
            f'--start-address={a}', f'--stop-address={b}', str(Path(path).resolve())], text=True)

    lines = {}
    for a, b in RANGES:
        lines.update(parse_lines(run('-D', a, b)))
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
            raise ValueError('unclassified GNU branch')
    selected = {
        0x2d368: ('adrp', 'x2, 0x31000'), 0x2d374: ('add', 'x2, x2, #0x688'),
        0x2d378: ('ldr', 'x1, [x1]'), 0x2d37c: ('str', 'x1, [x2, #752]'),
        0x2d384: ('ubfx', 'x3, x3, #4, #4'), 0x2d388: ('strb', 'w3, [x2, #689]'),
        0x2d5ac: ('adrp', 'x6, 0x31000'), 0x2d6d0: ('add', 'x19, x6, #0x688'),
        0x2d7e0: ('ldr', 'x0, [x0]'), 0x2d7e4: ('str', 'x0, [x19, #752]'),
        0x2d7f8: ('ubfx', 'x0, x0, #4, #4'), 0x2d7fc: ('strb', 'w0, [x19, #689]'),
        0x1e2c4: ('str', 'x0, [x21, #752]'), 0x1e2d4: ('mov', 'w1, #0xc'),
        0x1e2dc: ('mov', 'w0, w1'), 0x2f75c: ('mov', 'w2, #0x2c'),
        0x2f760: ('mov', 'w1, #0x0'), 0x2f7f8: ('ldrb', 'w0, [x19, #734]'),
    }
    if any(lines[pc][1:] != instruction for pc, instruction in selected.items()):
        raise ValueError('GNU selected operands differ')
    for offsets, register, expected_value in (
            ((0x2d364, 0x2d36c), 1, report['record']['address']),
            ((0x2d7d0, 0x2d7d4), 0, report['record']['address']),
            ((0x1e2c0,), 0, report['marker']['value']),
            ((0x2f774, 0x2f778), 0, report['conditional_clear']['destination'])):
        if hex(text_wide(lines, offsets, register)) != expected_value:
            raise ValueError('GNU record/marker/clear address differs')
    for pc, field in zip(range(0x2f800, 0x2f890, 24), report['conditional_field_restore']['fields']):
        if lines[pc+8][1:] != ('ldr', 'w1, [x0]') or lines[pc+20][1:] != ('str', 'w1, [x0]'):
            raise ValueError('GNU field transfer differs')
        if hex(text_wide(lines, (pc, pc+4), 0)) != field['source'] or hex(text_wide(lines, (pc+12, pc+16), 0)) != field['destination']:
            raise ValueError('GNU field addresses differ')
    pointers = 0
    for binding in report['nominal_callbacks']['bindings']:
        cell = int(binding['cell'], 16)
        pointer = int.from_bytes(dump_bytes(run('-s', cell, cell+8), cell, 8), 'little')
        if hex(pointer) != binding['pointer']:
            raise ValueError('GNU callback pointer differs')
        pointers += 1
    for copy in report['selected_copies']:
        for i, (offset, value) in enumerate(zip(copy['literal_offsets'], copy['source']+[copy['destination'][0]])):
            cell, pc = int(offset, 16), int(copy['start'], 16)+4*i
            if lines[pc][1:] != ('ldr', f'x{i}, {cell:#x}'):
                raise ValueError('GNU copy literal reference differs')
            literal = int.from_bytes(dump_bytes(run('-s', cell, cell+8), cell, 8), 'little')
            if hex(literal) != value:
                raise ValueError('GNU copy literal differs')
            pointers += 1
    packed = b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))
    return dict(mode='GNU_text_crosscheck', sboot_sha256=report['input']['sha256'], gnu_version=version,
                words_matched=len(lines), relative_targets_matched=branches, selected_operands_matched=len(selected),
                record_marker_clear_producers_matched=4, field_copies_matched=6,
                callback_and_copy_literals_matched=pointers,
                instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
                method='GNU MOV/MOVK/load/store text and hexdump; no binary record address decoder reused',
                firmware_executed=False, record_bytes_observed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    print(json.dumps(verify(args.sboot), indent=2))
