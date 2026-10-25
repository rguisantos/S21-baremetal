#!/usr/bin/env python3
"""Extract only allowlisted DRAM/build facts from the exact supplied private ZIP.

Never emits a full log line, cmdline, arbitrary property, or app/history text.
The archive remains outside Git. A public report contains only typed fields,
known technical labels, section/line references and hashes for reproduction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

SIZE = 35232190
SHA256 = 'd7d494cc5ceca1d8315afe415097e04fc94cf6802d6165678f96cd9ee6346c34'
MEMBER = 'dumpstate-2026-10-24-21-01-59.txt'
KERNEL = re.compile(r'Linux version (5\.4\.242-30958140-abG998BXXSJHZ(?:C2|A6))\b')
SECTIONS = re.compile(r'------ (KERNEL LOG|LAST KMSG|PRINT RECOVERY LOG|SYSTEM PROPERTIES)(?=[ (])')


def technical_fields(lines):
    section, records = 'HEADER', []
    kernel_stats = dict(lines=0, utf8_bytes=0, npu_lines=0, devfreq_dram_lines=0)
    for number, line in enumerate(lines, 1):
        if line.startswith('------ '):
            match = SECTIONS.match(line)
            section = match.group(1) if match else 'OTHER'
            continue
        fields = {}
        if section == 'HEADER':
            match = KERNEL.search(line)
            if match:
                fields['kernel'] = match.group(1)
            if re.search(r'\bdram_info=01,08,00,12G\b', line):
                fields['dram_info'] = '01,08,00,12G'
            if re.search(r'\blog_buf_len=256K\b', line):
                fields['log_buf_len_argument'] = '256K'
        elif section == 'SYSTEM PROPERTIES':
            if re.fullmatch(r'\[ro.product.model\]: \[SM-G998B\]\s*', line):
                fields['model'] = 'SM-G998B'
            if re.fullmatch(r'\[ro.build.version.release\]: \[15\]\s*', line):
                fields['android_release'] = '15'
        elif section == 'LAST KMSG':
            if re.search(r'\b0001000850500130\b', line):
                fields['bootloader_word'] = '0001000850500130'
            if re.search(r'\bG998BXXSJHZC2\b', line):
                fields['bootloader_build'] = 'G998BXXSJHZC2'
            if re.search(r'DRAM Manufacturer\s*=\s*Samsung\b', line):
                fields['manufacturer_label'] = 'Samsung'
            if re.search(r'DRAM Process ver\s*=\s*D1Z\b', line):
                fields['process_label'] = 'D1Z'
            if re.search(r'DRAM Size\s*=\s*12\.000000GB\b', line):
                fields['size_label'] = '12.000000GB'
        elif section == 'PRINT RECOVERY LOG':
            match = KERNEL.search(line)
            if match:
                fields['recovery_kernel'] = match.group(1)
        elif section == 'KERNEL LOG':
            kernel_stats['lines'] += 1
            kernel_stats['utf8_bytes'] += len(line.encode('utf-8'))
            kernel_stats['npu_lines'] += 'npu' in line.lower()
            kernel_stats['devfreq_dram_lines'] += bool(re.search(r'DEVFREQ\s*:\s*dram\s*:', line))
        if fields:
            records.append(dict(line=number, section=section, fields=fields))
    return dict(records=records, kernel_log=kernel_stats,
        raw_lines_or_identifiers_emitted=False, last_kmsg_is_not_a_live_register_snapshot=True,
        current_boot_identity_does_not_date_every_persistent_message=True)


def inspect(path):
    path = Path(path)
    if path.stat().st_size != SIZE:
        raise ValueError('unsupported archive size')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024*1024):
            digest.update(block)
    if digest.hexdigest() != SHA256:
        raise ValueError('unsupported archive hash')
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) != 306 or archive.getinfo(MEMBER).file_size != 172281782:
            raise ValueError('unsupported archive layout')
        member_hash = hashlib.sha256()

        def lines():
            with archive.open(MEMBER) as stream:
                for raw in stream:
                    member_hash.update(raw)
                    yield raw.decode('utf-8', 'replace')

        result = technical_fields(lines())
    values = {k:v for row in result['records'] for k,v in row['fields'].items()}
    required = dict(kernel='5.4.242-30958140-abG998BXXSJHZC2', dram_info='01,08,00,12G',
        bootloader_word='0001000850500130', manufacturer_label='Samsung',
        process_label='D1Z', size_label='12.000000GB')
    if any(values.get(k) != v for k,v in required.items()):
        raise ValueError('required technical observations missing')
    return dict(mode='allowlisted_private_bugreport_dram', archive_bytes=SIZE, archive_sha256=SHA256,
        member=MEMBER, member_sha256=member_hash.hexdigest(), fields=result,
        collection_method='bugreportz via rish/Shizuku, reported by user; not executed by this tool',
        direct_02073600_or_02038848_read=False, smc_or_uart_measurement=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bugreport')
    args = parser.parse_args()
    try:
        result = inspect(args.bugreport)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        parser.exit(2, 'inspect_bugreport_dram: unsupported archive or missing technical fields\n')
    print(json.dumps(result, indent=2))
