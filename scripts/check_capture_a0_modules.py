#!/usr/bin/env python3
"""Inventory version requirements from pinned HZC2 vendor_boot, entirely offline."""
import argparse
import json
from pathlib import Path
import re
import stat
import zlib

from capture_a0_formats import digest, layout, require
from capture_a0_modules import cpio, gunzip, module, requirements, compare_symvers
from check_capture_a0 import PINS, verify_file, source_members

SOURCE_NAMES = ('include/linux/module.h', 'include/linux/moduleparam.h', 'scripts/mod/modpost.c',
                'kernel/module.c', 'include/linux/vermagic.h')


def inventory(data):
    inv = layout(data)
    require(inv['kind'] == 'vendor_boot_v3' and inv['avb'] and inv['avb']['all_hashes_match'],
            'requires hash-consistent vendor boot v3')
    part = next(p for p in inv['parts'] if p['name'] == 'ramdisk')
    compressed = data[part['start']:part['end']]; raw = gunzip(compressed); entries = cpio(raw)
    def regular(name):
        require(name in entries and entries[name]['kind'] == stat.S_IFREG,
                'required ramdisk entry missing/non-regular: '+name)
        return entries[name]['data']
    modules = {}; version_sets = {}
    for name in sorted(entries):
        if name.endswith('.ko'):
            require(name.startswith('lib/modules/') and name.count('/') == 2, 'unexpected module path')
            modules[name], version_sets[name] = module(regular(name))
    require(modules, 'no stock modules found')
    load_raw = regular('lib/modules/modules.load')
    load = load_raw.decode('utf-8').splitlines()
    require(load and all(re.fullmatch(r'[A-Za-z0-9_.-]+\.ko', n) for n in load)
            and len(load) == len(set(load)), 'invalid/duplicate modules.load entry')
    listed = {'lib/modules/'+name for name in load}
    deps_raw = regular('lib/modules/modules.dep'); deps = {}
    for line in deps_raw.decode('utf-8').splitlines():
        name, sep, tail = line.partition(':')
        require(sep and name.startswith('/lib/modules/') and name[1:] in modules
                and name not in deps, 'invalid/duplicate modules.dep key')
        deps[name] = tail.split()
        require(all(n.startswith('/lib/modules/') and n[1:] in modules for n in deps[name]),
                'modules.dep references missing module')
    needed = requirements(version_sets)
    return dict(schema='S21-CAPTURE-A0-MODULES-v1', firmware='G998BXXSJHZC2',
        vendor_boot_sha256=inv['sha256'], ramdisk_compressed_sha256=digest(compressed),
        ramdisk_cpio_sha256=digest(raw), ramdisk_cpio_bytes=len(raw),
        cpio_entries=len(entries), modules=modules, module_count=len(modules),
        modules_load=dict(sha256=digest(load_raw), entries=len(load),
            missing_files=sorted(listed-modules.keys()), unlisted_files=sorted(modules.keys()-listed)),
        modules_dep=dict(sha256=digest(deps_raw), entries=len(deps),
            all_modules_have_entry={n[1:] for n in deps} == set(modules),
            all_referenced_files_present=True),
        vermagic_values=sorted({m['vermagic'] for m in modules.values()}),
        version_records=sum(map(len, version_sets.values())), unique_versioned_symbols=len(needed),
        requirements=needed, crc_conflicts=[n for n,v in needed.items() if len(v['crcs']) != 1],
        candidate_comparison=dict(supplied=False, crc_coverage_passed=False, module_abi_established=False),
        runtime_loaded_modules_established=False, symbol_provider_resolution_established=False,
        signature_verified=False, a0_complete=False, physical_action=False)


def inspect(image, source, symvers=None):
    pins = json.loads(PINS.read_text())
    verify_file(image, pins['stock_raw']['vendor_boot.img'])
    verify_file(source, pins['samsung_source_archive'])
    members = source_members(source, SOURCE_NAMES)
    header = members['include/linux/module.h'].decode()
    require('#define MODULE_NAME_LEN MAX_PARAM_PREFIX_LEN' in header
            and 'unsigned long crc;' in header and 'char name[MODULE_NAME_LEN];' in header,
            'source modversion contract differs')
    require('#define MAX_PARAM_PREFIX_LEN (64 - sizeof(unsigned long))' in
            members['include/linux/moduleparam.h'].decode(), 'source version record width differs')
    result = inventory(image.read_bytes())
    result['source_archive_sha256'] = pins['samsung_source_archive']['sha256']
    result['source_members'] = {n:dict(bytes=len(b), sha256=digest(b)) for n,b in sorted(members.items())}
    if symvers is not None:
        require(symvers.stat().st_size <= 16*1024*1024, 'symvers size exceeds bound')
        result['candidate_comparison'] = compare_symvers(result['requirements'], symvers.read_text())
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vendor-boot', required=True, type=Path)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--symvers', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        result = inspect(a.vendor_boot, a.source, a.symvers)
        with a.output.open('x') as f: f.write(json.dumps(result, indent=2)+'\n')
    except (ValueError, OSError, zlib.error) as exc:
        p.exit(1, 'MODULE INVENTORY REFUSED: '+str(exc)+'\n')
    print('Stock modules:', result['module_count'], '; distinct version requirements:', result['unique_versioned_symbols'])
    print('A0 remains open; CRC coverage is not ABI/boot approval')
    return 0 if result['candidate_comparison']['crc_coverage_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
