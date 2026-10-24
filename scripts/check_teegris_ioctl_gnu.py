#!/usr/bin/env python3
"""GNU cross-check for the selected HZC2 ELF import/provider/SVC boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from check_tzar_crypto_gnu import gnu_runner
from inspect_el2_hzc2 import read_exact
from inspect_tzar_hzc2 import SIZE, SHA256, inner_archive, archive_entries
from inspect_teegris_ioctl import evidence


def gnu_version_indices(text):
    array = text.split('Version definition section', 1)[0].split('Version needs section', 1)[0]
    result = {}
    for line in array.splitlines():
        row = re.match(r'\s*([0-9a-f]+):\s+(.*)', line)
        if row:
            for n, value in enumerate(re.findall(r'(\d+)(h?)\s*\(([^)]+)\)', row[2])):
                result[int(row[1], 16) + n] = (int(value[0]), bool(value[1]), value[2])
    return result


def check(path):
    report = evidence(path)
    entries = archive_entries(inner_archive(read_exact(path, SIZE, SHA256))[0])
    run = gnu_runner()
    link = report['declared_link']
    output = dict(input_sha256=SHA256, GNU_readelf=run('readelf', '--version')[0].splitlines()[0],
                  GNU_objdump=run('objdump', '--version')[0].splitlines()[0], libraries={})
    with tempfile.TemporaryDirectory(prefix='hzc2-ioctl-gnu-') as tmp:
        for role, name, index, version_index, hidden, witness_key in (
            ('caller', link['caller'], link['relocation_symbol_index'], link['required_version_index'], link['requirement_hidden'], 'caller_witnesses'),
            ('provider', link['provider'], link['provider_symbol_index'], link['provided_version_index'], link['definition_hidden'], 'provider_witnesses')):
            binary = Path(tmp) / (role + '.elf')
            binary.write_bytes(entries[name]['data'])
            versions, warning = run('readelf', '-VW', str(binary))
            if gnu_version_indices(versions).get(index) != (version_index, hidden, link['version']):
                raise ValueError('GNU symbol version index/label differs')
            dynamic, dynamic_warning = run('readelf', '-dW', str(binary))
            if role == 'caller':
                needed = re.findall(r'Shared library: \[([^]]+)\]', dynamic)
                if needed != link['caller_needed']:
                    raise ValueError('GNU NEEDED list differs')
                need_lines = versions.split('Version needs section', 1)[1].splitlines()
                library, matched = None, None
                for line in need_lines:
                    file = re.search(r'File: (\S+)', line)
                    if file:
                        library = file[1]
                        library_line = line.strip()
                    entry = re.search(r'Name: (\S+)\s+Flags:.*Version: (\d+)', line)
                    if entry and int(entry[2]) == version_index:
                        if (library, entry[1]) != (link['provider_soname'], link['version']):
                            raise ValueError('GNU version provider differs')
                        matched = line.strip()
                        output['version_need_library_line'] = library_line
                if matched is None:
                    raise ValueError('GNU required version missing')
                relocs, reloc_warning = run('readelf', '-rW', str(binary))
                lines = [line.strip() for line in relocs.splitlines() if re.search(r'\bioctl@', line)]
                if len(lines) != 1:
                    raise ValueError('GNU ioctl relocation is not unique')
                fields = lines[0].split()
                if (int(fields[0], 16), int(fields[1], 16) >> 32, fields[2], fields[4], fields[-1]) != (
                    int(link['relocation_slot'], 16), index, 'R_AARCH64_JUMP_SLOT', 'ioctl@' + link['version'], '0'):
                    raise ValueError('GNU JUMP_SLOT differs')
                output['version_need_line'], output['relocation_line'] = matched, lines[0]
            else:
                if re.findall(r'Library soname: \[([^]]+)\]', dynamic) != [link['provider_soname']]:
                    raise ValueError('GNU provider SONAME differs')
                symbols, _ = run('readelf', '--dyn-syms', '--wide', str(binary))
                selected = [line.strip() for line in symbols.splitlines() if 'ioctl@@' + link['version'] in line]
                if len(selected) != 1:
                    raise ValueError('GNU provider ioctl symbol missing/ambiguous')
                fields = selected[0].split()
                if (int(fields[0][:-1]), int(fields[1], 16), int(fields[2]), fields[3]) != (index, 0x8654, 72, 'FUNC'):
                    raise ValueError('GNU provider symbol extent differs')
                output['provider_symbol_line'] = selected[0]
                reloc_warning = ''
            disassembly, objdump_warning = run('objdump', '-d', str(binary))
            decoded = {}
            for line in disassembly.splitlines():
                match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)', line)
                if match:
                    decoded[int(match[1], 16)] = (match[2], match[3], line.strip())
            selected, targets, word_index = [], 0, []
            for item in report[witness_key]:
                pc = int(item['elf_address'], 16)
                word, asm, line = decoded[pc]
                if word != item['word']:
                    raise ValueError('GNU instruction differs')
                if item['relative_target'] is not None:
                    target = re.search(r'(?:^|[\s,])([0-9a-f]+)\s+<', asm)
                    if not target or int(target[1], 16) != int(item['relative_target'], 16):
                        raise ValueError('GNU branch target differs')
                    targets += 1
                selected.append(line)
                word_index.append(f'{pc:x}:{word}\n')
            output['libraries'][role] = dict(path=name, instruction_count=len(selected), relative_target_count=targets,
                symbol_version_index=version_index, symbol_index=index, instruction_lines=selected,
                instruction_index_sha256=hashlib.sha256(''.join(word_index).encode()).hexdigest(),
                warnings=[x for x in (warning, dynamic_warning, reloc_warning, objdump_warning) if x])
    output['firmware_executed'] = False
    output['limit'] = 'Static link metadata and selected instruction words/targets; no runtime resolution or SVC execution'
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tzar')
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.tzar), indent=2))
    except (ValueError, OSError, KeyError, IndexError, subprocess.SubprocessError) as error:
        parser.exit(2, f'{error}\n')
