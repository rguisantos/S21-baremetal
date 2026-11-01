#!/usr/bin/env python3
"""Offline A0 inventory. Successful analysis is not approval of a repacked image."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

from capture_a0_formats import (MAX_IMAGE, compare, config_diff, config_values,
    digest, ikconfig, layout, reassemble, require)

PINS = Path(__file__).resolve().parents[1] / 'docs/references/capture-a0-pins-hzc2.json'


def verify_file(path, pin):
    require(path.is_file() and path.stat().st_size == pin['bytes'], 'input size differs: '+path.name)
    require(digest(path.read_bytes()) == pin['sha256'], 'input hash differs: '+path.name)


def source_members(path, names):
    """Read selected bounded regular files, never extract arbitrary archive paths."""
    result = {}
    with tarfile.open(path, 'r|gz') as archive:
        for member in archive:
            name = member.name.removeprefix('./')
            if name not in names:
                continue
            require(name not in result and member.isfile() and member.size <= 2*1024*1024,
                    'duplicate/non-regular/oversize source member')
            result[name] = archive.extractfile(member).read()
    require(set(result) == set(names), 'source members missing')
    return result


def source_report(members, kernel):
    texts = {k: v.decode('utf-8') for k, v in members.items()}
    make = texts['Makefile']
    components = [re.search(r'^'+k+r' = (\d+)$', make, re.M)
                  for k in ('VERSION', 'PATCHLEVEL', 'SUBLEVEL')]
    require(all(components), 'kernel version fields missing')
    version = '.'.join(m.group(1) for m in components)
    config = ikconfig(kernel)
    source_config = texts['arch/arm64/configs/exynos2100-p3sxxx_defconfig']
    values = config_values(config.decode())
    checks = ('CONFIG_EFI', 'CONFIG_LTO_CLANG', 'CONFIG_CFI_CLANG',
              'CONFIG_MODVERSIONS', 'CONFIG_COMPAT_VDSO', 'CONFIG_TRIM_UNUSED_KSYMS')
    head = texts['arch/arm64/kernel/head.S'].splitlines()
    starts = [i for i, line in enumerate(head) if line.strip() == 'ENTRY(stext)']
    ends = [i for i, line in enumerate(head) if line.strip() == 'ENDPROC(stext)']
    require(len(starts) == len(ends) == 1 and starts[0] < ends[0], 'primary entry scope differs')
    evidence = {}
    for instruction in ('ENTRY(stext)', 'bl\tpreserve_boot_args', 'bl\tel2_setup'):
        lines = [i+1 for i in range(starts[0], ends[0]+1)
                 if head[i].split('//', 1)[0].strip() == instruction]
        require(len(lines) == 1, 'entry source anchor missing/ambiguous')
        evidence[instruction] = lines[0]
    require(list(evidence.values()) == sorted(evidence.values()), 'entry source order differs')
    # Publish only named public settings and hashes, not the embedded build-host paths.
    return dict(version=version, members={k: dict(bytes=len(v), sha256=digest(v))
        for k, v in sorted(members.items())}, stock_ikconfig=dict(bytes=len(config),
        sha256=digest(config), selected_settings={k: values.get(k) for k in checks}),
        config_differences=config_diff(source_config, config.decode()),
        entry_source='arch/arm64/kernel/head.S',
        entry_source_lines=evidence,
        source_entry_order=['EFI MZ/add x13,x18,#0x16', 'b stext',
                            'ENTRY(stext)', 'bl preserve_boot_args', 'bl el2_setup'],
        final_elf_checked=False, capture_implemented=False,
        stock_binary_equivalence_established=False, module_abi_established=False)


def run_tool(tool, args, cwd, allowed=(0,)):
    result = subprocess.run([str(tool), *map(str, args)], cwd=cwd,
        env={'PATH': os.defpath, 'LC_ALL': 'C'}, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=120)
    (cwd / ('tool-%02d.log' % len(list(cwd.glob('tool-*.log'))))).write_bytes(result.stdout)
    require(result.returncode in allowed, 'magiskboot operation failed; see private output log')
    return result.returncode


def analyse(stock_dir, source, apk, output, pins):
    # Check every private input before executing native tools or creating output.
    paths = {name: stock_dir / name for name in pins['stock_lz4']}
    for name, path in paths.items():
        verify_file(path, pins['stock_lz4'][name])
    verify_file(source, pins['samsung_source_archive'])
    verify_file(apk, pins['magisk']['apk'])
    members = source_members(source, pins['source_members'])
    for name, data in members.items():
        require(digest(data) == pins['source_members'][name]['sha256'], 'source member hash differs')
    with zipfile.ZipFile(apk) as z:
        name = 'lib/x86_64/libmagiskboot.so'
        require(z.namelist().count(name) == 1, 'ambiguous native tool entry')
        info = z.getinfo(name)
        require(info.file_size == pins['magisk']['host_binary']['bytes'], 'native tool size differs')
        executable = z.read(info)
    require(digest(executable) == pins['magisk']['host_binary']['sha256'], 'native tool hash differs')
    output.mkdir(parents=True, exist_ok=False)
    tool = output.resolve() / 'magiskboot'
    tool.write_bytes(executable)
    tool.chmod(0o700)
    report = dict(schema='S21-CAPTURE-A0-v1', inputs_verified=True, images={},
        magisk=pins['magisk'], toolchain_candidate=pins['toolchain'],
        analysis_completed=False, a0_complete=False, physical_action_authorized=False)
    for compressed, path in paths.items():
        name = compressed.removesuffix('.lz4')
        original = output.resolve() / name
        run_tool(tool, ['decompress', path.resolve(), original], output)
        verify_file(original, pins['stock_raw'][name])
        data = original.read_bytes()
        require(len(data) <= MAX_IMAGE, 'decompressed image too large')
        inventory = layout(data)
        require(inventory['avb'] and inventory['avb']['all_hashes_match'], 'stock AVB hashes differ')
        pieces = [data[p['start']:p['end']] for p in inventory['parts']]
        item = dict(inventory=inventory)
        if name in ('boot.img', 'vendor_boot.img'):
            work = output / (name + '.work')
            work.mkdir()
            # v30.7 returns 3 for successful vendor unpack, not an error.
            rc = run_tool(tool, ['unpack', '-n', '-h', original], work,
                          (0,) if name == 'boot.img' else (3,))
            for i, part in enumerate(inventory['parts']):
                if part['kind'] == 'payload':
                    filename = 'ramdisk.cpio' if part['name'] == 'ramdisk' else part['name']
                    extracted = (work / filename).read_bytes()
                    require(extracted == pieces[i], 'native unpack payload differs from independent layout')
                    pieces[i] = extracted
            repacked = output.resolve() / ('magisk-roundtrip-' + name)
            run_tool(tool, ['repack', '-n', original, repacked], work)
            item.update(unpack_returncode=rc, magisk_no_change=compare(data, repacked.read_bytes()))
            if name == 'boot.img':
                kernel = next(p for p in inventory['parts'] if p['name'] == 'kernel')
                report['source'] = source_report(members, data[kernel['start']:kernel['end']])
        rebuilt = reassemble(inventory['parts'], pieces, len(data))
        require(rebuilt == data, 'lossless inventory reassembly differs')
        (output / ('lossless-control-' + name)).write_bytes(rebuilt)
        item['lossless_inventory_control'] = dict(byte_identical=True, sha256=digest(rebuilt),
            opaque_bytes_preserved=True, modified_payloads_supported=False)
        report['images'][name] = item
    report['analysis_completed'] = True
    report['magisk_no_change_gate_passed'] = all(item['magisk_no_change']['no_change_gate_passed']
        for item in report['images'].values() if 'magisk_no_change' in item)
    report['remaining_gates'] = ['compatible modified-image packer', 'complete kernel build profile',
        'module/KMI compatibility', 'final ELF section/entry proof (A1)',
        'ramdisk and read-policy delivery', 'installation and recovery route (A3)']
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock-dir', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--magisk-apk', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = analyse(args.stock_dir, args.source, args.magisk_apk, args.output_dir,
                         json.loads(PINS.read_text()))
    except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile,
            subprocess.SubprocessError) as exc:
        parser.exit(1, 'A0 ANALYSIS REFUSED: '+str(exc)+'\n')
    print('A0 analysis completed; Magisk no-change gate:',
          'PASS' if report['magisk_no_change_gate_passed'] else 'FAIL; A0 remains blocked')
    # Deliberately nonzero for a completed analysis whose no-change gate failed.
    return 0 if report['magisk_no_change_gate_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
