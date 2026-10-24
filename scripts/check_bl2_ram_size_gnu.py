#!/usr/bin/env python3
"""Independently disassemble the selected BL2 RAM-size witnesses with GNU."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_bl2_ram_size import WITNESSES, inspect
from inspect_lk_final_edges import flow


def verify(path):
    report = inspect(path)
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command + ['--version'], text=True).splitlines()[0]
    lines = {}
    for start, end in WITNESSES:
        output = subprocess.check_output(command + ['-D', '-b', 'binary', '-m', 'aarch64',
            f'--start-address={start}', f'--stop-address={end}', str(Path(path).resolve())], text=True)
        lines.update(parse_lines(output))
    expected = {int(pc, 16): int(raw, 16) for pc, raw in report['words'].items()}
    if set(lines) != set(expected):
        raise ValueError('GNU witness coverage differs')
    relative = 0
    for pc, (raw, mnemonic, operands) in lines.items():
        if raw != expected[pc] or mnemonic in ('.inst', 'udf'):
            raise ValueError(f'GNU instruction mismatch at {pc:#x}')
        kind, target = flow(raw, pc)
        gnu_target = direct_target(mnemonic, operands)
        if kind in ('b', 'bl', 'conditional'):
            if target != gnu_target:
                raise ValueError(f'GNU branch mismatch at {pc:#x}')
            relative += 1
        elif gnu_target is not None:
            raise ValueError('unclassified GNU branch')
    selected = {
        0x18004: ('mov', 'x1, #0x8848'),
        0x18008: ('movk', 'x1, #0x203, lsl #16'),
        0x1800c: ('str', 'x0, [x1]'),
        0x1dc94: ('adrp', 'x19, 0x31000'),
        0x1e860: ('str', 'x0, [x25, #696]'),
        0x1f9cc: ('ldr', 'x0, [x19, #696]'),
        0x1d860: ('ldr', 'x0, [x0, #856]'),
        0x2caec: ('adrp', 'x0, 0x31000'),
        0x2cb00: ('adrp', 'x9, 0x30000'),
        0x2cb04: ('ldr', 'x1, [x1, #752]'),
        0x2cb68: ('ldrh', 'w3, [x3, w1, uxtw #1]'),
        0x2cb94: ('lsl', 'x0, x7, #20'),
    }
    for pc, instruction in selected.items():
        if lines[pc][1:] != instruction:
            raise ValueError(f'GNU selected operand mismatch at {pc:#x}')
    packed = b''.join(struct.pack('<II', pc, expected[pc]) for pc in sorted(expected))
    return dict(mode='GNU_text_crosscheck', sboot_sha256=report['input']['sha256'],
                gnu_version=version, words_matched=len(lines),
                relative_targets_matched=relative, selected_operands_matched=len(selected),
                instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
                firmware_executed=False, physical_device_tested=False,
                limit='Selected witnesses only; nominal pointer binding and live geometry unverified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    print(json.dumps(verify(args.sboot), indent=2))
