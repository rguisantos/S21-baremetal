#!/usr/bin/env python3
"""Cross-check callback instructions, bitfields and pointer bytes via GNU text."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_bl2_geometry_query import RANGES, inspect
from inspect_lk_final_edges import flow


def dump_bytes(output, start, size):
    cells = {}
    for line in output.splitlines():
        tokens = line.split()
        if not tokens or not re.fullmatch('[0-9a-f]+', tokens[0]):
            continue
        address = int(tokens[0], 16)
        for group in tokens[1:5]:
            if not re.fullmatch('[0-9a-f]{8}', group):
                break
            for value in bytes.fromhex(group):
                if address in cells:
                    raise ValueError('duplicate GNU dump byte')
                cells[address] = value
                address += 1
    if set(cells) != set(range(start, start+size)):
        raise ValueError('GNU pointer dump coverage differs')
    return bytes(cells[pc] for pc in range(start, start+size))


def verify(path):
    report = inspect(path)
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command + ['--version'], text=True).splitlines()[0]

    def run(flags, start, end):
        return subprocess.check_output(command + flags + ['-b', 'binary', '-m', 'aarch64',
            f'--start-address={start}', f'--stop-address={end}', str(Path(path).resolve())], text=True)

    lines = {}
    for start, end in RANGES:
        lines.update(parse_lines(run(['-D'], start, end)))
    expected = {int(pc, 16): int(raw, 16) for pc, raw in report['words'].items()}
    if set(lines) != set(expected):
        raise ValueError('GNU instruction coverage differs')
    branches = 0
    for pc, (raw, mnemonic, operands) in lines.items():
        if raw != expected[pc] or mnemonic in ('.inst', 'udf'):
            raise ValueError(f'GNU instruction mismatch at {pc:#x}')
        kind, target = flow(raw, pc)
        textual = direct_target(mnemonic, operands)
        if kind in ('b', 'bl', 'conditional'):
            if target != textual:
                raise ValueError(f'GNU branch mismatch at {pc:#x}')
            branches += 1
        elif textual is not None:
            raise ValueError('unclassified GNU branch')
    selected = {
        0x28484: ('uxtb', 'w2, w2'),
        0x28490: ('add', 'x3, x3, #0xf98'),
        0x28494: ('ldr', 'x3, [x3, w0, uxtw #3]'),
        0x284b0: ('ldr', 'x3, [x3, #3992]'),
        0x284b4: ('ldr', 'w3, [x3]'),
        0x284c8: ('ldr', 'x0, [x1, w0, uxtw #3]'),
        0x284cc: ('mov', 'w1, #0x1'),
        0x284d0: ('str', 'w3, [x0]'),
        0x284d4: ('str', 'w1, [x0, #4]'),
        0x284d8: ('ldr', 'w3, [x0, #12]'),
        0x2a258: ('add', 'x1, x1, #0xfc0'),
        0x2a278: ('ldr', 'x1, [x1, #4032]'),
        0x2a27c: ('ldr', 'w1, [x1, #80]'),
        0x2a284: ('orr', 'w1, w1, #0x1000000'),
        0x2a290: ('str', 'w1, [x0, #80]'),
        0x2a294: ('and', 'w1, w1, #0xfeffffff'),
        0x2a298: ('str', 'w1, [x0, #80]'),
    }
    for pc, instruction in selected.items():
        if lines[pc][1:] != instruction:
            raise ValueError(f'GNU operand mismatch at {pc:#x}')
    for pc, name in ((0x284b8, 'term_field'), (0x284c4, 'selector_field')):
        _, mnemonic, operands = lines[pc]
        match = re.fullmatch(r'w3, w([12]), #(\d+), #(\d+)', operands)
        if mnemonic != 'bfi' or match is None:
            raise ValueError('GNU BFI field missing')
        source, lsb, width = map(int, match.groups())
        fields = dict(destination=3, source=source, lsb=lsb, width=width, mask=((1 << width)-1) << lsb)
        if fields != report['query'][name]:
            raise ValueError('GNU BFI fields differ')
    pointers = 0
    for item in (report['query'], report['preparation']):
        start = int(item['table_offset'], 16)
        raw = dump_bytes(run(['-s'], start, start+40), start, 40)
        actual = [hex(int.from_bytes(raw[i:i+8], 'little')) for i in range(0, 40, 8)]
        if actual != item['bases']:
            raise ValueError('GNU base table differs')
        pointers += 5
    for binding in report['nominal_callbacks']['bindings']:
        start = int(binding['cell'], 16)
        pointer = int.from_bytes(dump_bytes(run(['-s'], start, start+8), start, 8), 'little')
        if hex(pointer) != binding['pointer'] or pointer-int(report['nominal_callbacks']['delta'], 16) != int(binding['nominal_target'], 16):
            raise ValueError('GNU callback pointer differs')
        pointers += 1
    packed = b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))
    return dict(mode='GNU_text_crosscheck', sboot_sha256=report['input']['sha256'],
                gnu_version=version, words_matched=len(lines), relative_targets_matched=branches,
                selected_operands_matched=len(selected), bfi_fields_matched=2, pointers_matched=pointers,
                instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
                pointer_method='GNU hex dump bytes; no binary pointer reader reused',
                firmware_executed=False, hardware_response_observed=False,
                limit='Static correspondence only; nominal binding and live registers remain unverified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    print(json.dumps(verify(args.sboot), indent=2))
