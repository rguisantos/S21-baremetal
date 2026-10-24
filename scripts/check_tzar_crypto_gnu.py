#!/usr/bin/env python3
"""Independently check selected TZAR ELF symbols/instructions with GNU tools."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from inspect_el2_hzc2 import read_exact
from inspect_tzar_hzc2 import SIZE, SHA256, archive_entries, evidence, inner_archive


def gnu_runner():
    """Use only the repository's GNU tools and their existing runtime wrapper."""
    root = Path(__file__).resolve().parents[1]
    runner = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root')]

    def run(tool, *args):
        result = subprocess.run(runner + [str(root / 'tools/root/usr/bin' / ('aarch64-linux-gnu-' + tool)), *args],
                                capture_output=True, text=True, check=True, timeout=30, cwd=root)
        return result.stdout, result.stderr.strip()
    return run


def check(path):
    report = evidence(path)
    archive, _ = inner_archive(read_exact(path, SIZE, SHA256))
    entries = archive_entries(archive)
    run = gnu_runner()

    output = dict(input_sha256=SHA256, GNU_objdump=run('objdump', '--version')[0].splitlines()[0],
                  GNU_readelf=run('readelf', '--version')[0].splitlines()[0], libraries={})
    with tempfile.TemporaryDirectory(prefix='hzc2-tzar-gnu-') as tmp:
        for label, name, witness_key in (('scrypto64', '/lib64/libscrypto.so', 'scrypto_SHA384_delegation'),
                                         ('teesl64', '/lib64/libteesl.so', 'teesl_crypto_boundary')):
            binary = Path(tmp) / (label + '.elf')
            binary.write_bytes(entries[name]['data'])
            symbols_text, warnings = run('readelf', '--dyn-syms', '--wide', str(binary))
            symbols = {}
            for line in symbols_text.splitlines():
                match = re.match(r'\s*\d+:\s+([0-9a-f]+)\s+(\d+)\s+(\S+)\s+\S+\s+\S+\s+(\S+)\s+(\S+)', line)
                if match:
                    address, size, typ, section, symbol = match.groups()
                    symbols[symbol.split('@')[0]] = (int(address, 16), int(size), typ, section != 'UND', line.strip())
            selected_symbols = []
            for symbol, expected in report['selected_dynamic_symbols'][label].items():
                actual = symbols[symbol]
                if actual[:4] != (int(expected['address'], 16), expected['size'], 'FUNC', expected['defined']):
                    raise ValueError('GNU dynamic symbol differs: ' + symbol)
                selected_symbols.append(actual[4])
            disassembly, disassembly_warnings = run('objdump', '-d', str(binary))
            instructions = {}
            for line in disassembly.splitlines():
                match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)', line)
                if match:
                    instructions[int(match[1], 16)] = (match[2], match[3], line.strip())
            selected_instructions, index, targets = [], [], 0
            for expected in report[witness_key]:
                pc = int(expected['elf_address'], 16)
                word, asm, line = instructions[pc]
                if word != expected['word']:
                    raise ValueError('GNU instruction word differs')
                if expected['relative_target'] is not None:
                    target = re.search(r'(?:^|[\s,])([0-9a-f]+)\s+<', asm)
                    if not target or int(target[1], 16) != int(expected['relative_target'], 16):
                        raise ValueError('GNU branch target differs')
                    targets += 1
                selected_instructions.append(line)
                index.append(f'{pc:x}:{word}\n')
            output['libraries'][label] = dict(path=name, sha256=hashlib.sha256(entries[name]['data']).hexdigest(),
                symbol_count=len(selected_symbols), instruction_count=len(selected_instructions), relative_target_count=targets,
                instruction_index_sha256=hashlib.sha256(''.join(index).encode()).hexdigest(),
                symbol_lines=selected_symbols, instruction_lines=selected_instructions,
                readelf_warnings=warnings, objdump_warnings=disassembly_warnings)
    output['firmware_executed'] = False
    output['limit'] = 'Selected metadata/words/relative targets only; no runtime or ioctl/MMIO responses'
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tzar')
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.tzar), indent=2))
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(2, f'{error}\n')
