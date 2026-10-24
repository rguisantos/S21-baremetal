#!/usr/bin/env python3
"""Cross-check EPBL words, relative targets and literal MMIO against GNU text.

The independent text walker knows no stack data or hardware outputs. Uses
only the hash-bound source file; no firmware instruction is executed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_epbl_protocol import MMIO, RANGES, evidence
from inspect_lk_final_edges import flow


def parse_lines(output):
    result = {}
    for line in output.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*)$', line)
        if match:
            pc, raw, mnemonic, operands = match.groups()
            if int(pc, 16) in result:
                raise ValueError('duplicate GNU PC')
            result[int(pc, 16)] = (int(raw, 16), mnemonic, operands.split('//')[0].strip())
    return result


def direct_target(mnemonic, operands):
    if mnemonic == 'b' or mnemonic == 'bl' or mnemonic.startswith('b.') or mnemonic in ('tbz', 'tbnz', 'cbz', 'cbnz'):
        return int(operands.split(',')[-1].strip(), 0)
    return None


def text_mmio(lines):
    targets = {direct_target(m, o) for _, m, o in lines.values()}
    registers, result = {}, []
    for pc, (_, mnemonic, operands) in sorted(lines.items()):
        if pc in targets:
            registers.clear()
        args = [part.strip() for part in operands.split(',')]
        if mnemonic in ('mov', 'movk') and re.fullmatch('[xw][0-9]+', args[0]):
            number, bits = int(args[0][1:]), 32 if args[0][0] == 'w' else 64
            if args[1].startswith('#'):
                value = int(args[1][1:], 0) & ((1 << bits) - 1)
                if mnemonic == 'movk':
                    shift = int(args[2].split('#')[1], 0) if len(args) == 3 else 0
                    old = registers.get(number)
                    value = None if old is None else (old & ~(0xffff << shift)) | (value << shift)
                registers[number] = None if value is None else value & ((1 << bits) - 1)
            else:
                registers[number] = None
            continue
        if mnemonic in ('ldr', 'str', 'ldrb', 'strb'):
            match = re.fullmatch(r'([xw](?:[0-9]+|zr)), \[x([0-9]+)(?:, #([^\]]+))?\]', operands)
            if match:
                register, base, displacement = match.groups()
                address = registers.get(int(base))
                if address is not None:
                    address += 0 if displacement is None else int(displacement, 0)
                    if MMIO <= address < MMIO + 0x2000:
                        operation = 'read' if mnemonic.startswith('ld') else 'write'
                        width = 1 if mnemonic.endswith('b') else 8 if register.startswith('x') else 4
                        result.append((pc, operation, width, address))
            if mnemonic.startswith('ld') and re.fullmatch('[xw][0-9]+', args[0]):
                registers[int(args[0][1:])] = None
            continue
        if direct_target(mnemonic, operands) is not None or mnemonic in ('br', 'blr', 'ret', 'eret'):
            registers.clear()
        elif args and re.fullmatch('[xw][0-9]+', args[0]) and mnemonic not in ('cmp', 'tst'):
            registers[int(args[0][1:])] = None
    return result


def verify(sboot, *, save_disassembly=None):
    root = Path(__file__).resolve().parent.parent
    objdump = root / 'tools/root/usr/bin/aarch64-linux-gnu-objdump'
    command = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root'), str(objdump)]
    version = subprocess.check_output(command + ['--version'], text=True).splitlines()[0]
    data = read_exact(sboot, *IMAGES['sboot'])
    report = evidence(sboot)
    lines, bodies = {}, []
    for first, last in RANGES:
        output = subprocess.check_output(command + ['-D', '-b', 'binary', '-m', 'aarch64',
            f'--start-address={first}', f'--stop-address={last}', str(Path(sboot).resolve())], text=True)
        lines.update(parse_lines(output))
        bodies.extend(line for line in output.splitlines() if re.match(r'^\s*[0-9a-f]+:', line))
    wanted = [pc for a, b in RANGES for pc in range(a, b, 4)]
    if sorted(lines) != wanted:
        raise ValueError('GNU code coverage mismatch')
    relative = 0
    for pc in wanted:
        raw, mnemonic, operands = lines[pc]
        if raw != struct.unpack_from('<I', data, pc)[0] or mnemonic in ('.inst', 'udf'):
            raise ValueError(f'GNU word/instruction mismatch at {pc:#x}')
        kind, target = flow(raw, pc)
        gnu_target = direct_target(mnemonic, operands)
        if kind in ('b', 'bl', 'conditional'):
            if gnu_target != target:
                raise ValueError(f'GNU relative target mismatch at {pc:#x}')
            relative += 1
        elif gnu_target is not None:
            raise ValueError('unclassified GNU branch')
    expected = [(int(a['pc'], 16), a['operation'], a['width_bytes'], int(a['address'], 16)) for a in report['mmio_inventory']]
    actual = text_mmio(lines)
    if actual != expected:
        raise ValueError(f'GNU MMIO mismatch: missing={set(expected)-set(actual)}, extra={set(actual)-set(expected)}')
    packed = b''.join(struct.pack('<II', pc, lines[pc][0]) for pc in wanted)
    if save_disassembly:
        Path(save_disassembly).write_text('\n'.join(bodies) + '\n')
    return dict(mode='GNU_text_crosscheck', sboot_sha256=IMAGES['sboot'][1], gnu_version=version,
        words_matched=len(wanted), relative_targets_matched=relative, mmio_addresses_widths_operations_matched=len(actual),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        independent_mmio_method='Parse GNU mov/movk/load/store text with control-flow cuts; no binary address decoder reused',
        stack_dataflow_independently_executed=False, firmware_executed=False, physical_device_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    parser.add_argument('--save-disassembly')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.sboot, save_disassembly=args.save_disassembly), indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(2, 'GNU protocol check failed: ' + str(exc) + '\n')
