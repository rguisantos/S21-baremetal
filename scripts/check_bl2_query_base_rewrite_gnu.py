#!/usr/bin/env python3
"""Check conditional table writes by independently walking GNU constructor text."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from check_bl2_geometry_query_gnu import dump_bytes
from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_bl2_query_base_rewrite import RANGES, WRITE_START, WRITE_END, inspect
from inspect_lk_final_edges import flow


def text_stores(lines):
    registers, stores = {}, []
    for pc in range(WRITE_START, WRITE_END, 4):
        _, op, args = lines[pc]
        if op == 'adrp' and (m := re.fullmatch(r'(x\d+), (0x[0-9a-f]+)', args)):
            destination, literal = m.groups()
            registers[destination] = int(literal, 0)
        elif op in ('mov', 'movk') and (m := re.fullmatch(r'(x\d+), #(0x[0-9a-f]+)(?:, lsl #(\d+))?', args)):
            destination, literal, shift = m.groups()
            shift = 0 if shift is None else int(shift)
            value = int(literal, 0) << shift
            if op == 'movk':
                value |= registers[destination] & ~(65535 << shift)
            registers[destination] = value
        elif op == 'add' and (m := re.fullmatch(r'(x\d+), (x\d+), #(0x[0-9a-f]+)(?:, lsl #(\d+))?', args)):
            destination, source, literal, shift = m.groups()
            registers[destination] = registers[source] + (int(literal, 0) << (0 if shift is None else int(shift)))
        elif op == 'str' and (m := re.fullmatch(r'(x\d+), \[(x\d+), #(\d+)\]', args)):
            source, base, displacement = m.groups()
            stores.append(dict(pc=hex(pc), destination=hex(registers[base]+int(displacement)),
                               value=hex(registers[source]), width_bits=64))
        else:
            raise ValueError('unsupported GNU constructor text')
    return stores


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
    expected = {int(p, 16): int(v, 16) for p, v in report['words'].items()}
    if set(lines) != set(expected):
        raise ValueError('GNU coverage differs')
    branches = 0
    for pc, (raw, op, args) in lines.items():
        if raw != expected[pc] or op in ('.inst', 'udf'):
            raise ValueError('GNU word differs')
        kind, target = flow(raw, pc)
        textual = direct_target(op, args)
        if kind in ('b', 'bl', 'conditional'):
            if textual != target:
                raise ValueError('GNU branch differs')
            branches += 1
        elif textual is not None:
            raise ValueError('unclassified GNU branch')
    if text_stores(lines) != report['table']['conditional_stores']:
        raise ValueError('GNU constructor stores differ')
    selected = {0x1e0dc: ('add', 'x0, x20, #0x408'), 0x1e0e0: ('ldr', 'x0, [x0, #32]'),
                0x2d280: ('cmp', 'w0, #0x1'), 0x2e3d0: ('mov', 'x0, #0x10'),
                0x2e3d4: ('movk', 'x0, #0x1000, lsl #16'),
                0x2e3d8: ('ldr', 'w0, [x0]'), 0x2e3dc: ('ubfx', 'x0, x0, #20, #4')}
    if any(lines[pc][1:] != instruction for pc, instruction in selected.items()):
        raise ValueError('GNU selected operands differ')
    table = int(report['table']['offset'], 16)
    raw = dump_bytes(run('-s', table, table+40), table, 40)
    if [hex(int.from_bytes(raw[i:i+8], 'little')) for i in range(0, 40, 8)] != report['table']['initial_file_bases']:
        raise ValueError('GNU initial table differs')
    for binding in report['nominal_callbacks']['bindings']:
        cell = int(binding['cell'], 16)
        raw = dump_bytes(run('-s', cell, cell+8), cell, 8)
        if hex(int.from_bytes(raw, 'little')) != binding['pointer']:
            raise ValueError('GNU callback pointer differs')
    packed = b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))
    return dict(mode='GNU_text_crosscheck', sboot_sha256=report['input']['sha256'], gnu_version=version,
                words_matched=len(lines), relative_targets_matched=branches, selected_operands_matched=len(selected),
                constructor_stores_matched=5, initial_and_callback_pointers_matched=7,
                instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
                method='GNU ADRP/MOV/MOVK/ADD/STR text; pointer hexdump; no binary constructor reused',
                firmware_executed=False, register_runtime_observed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    print(json.dumps(verify(args.sboot), indent=2))
