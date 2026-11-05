#!/usr/bin/env python3
"""Audit declared module dependencies and optional stock load-control files.

The default uses a pinned, previously measured inventory, not module binaries.
No module is loaded and the proposed order is never written into a ramdisk.
"""
import argparse
import json
from pathlib import Path
import re
import stat
import struct
import zlib

from capture_a0_formats import layout, require
from capture_a0_inputs import read_checked, unique_object
from capture_a0_modules import cpio, gunzip, module

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT/'docs/references/capture-a0-modules-hzc2.json'
INVENTORY_PIN = dict(bytes=415440, sha256='76fbc6e96cd0310fdc83e501acc39ae1eec955714cbb2e6698b7ff7240267e0b')


def canonical(name):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]{0,127}', name),
            'invalid module identity')
    return name.replace('-', '_')


def audit(modules, load=None, dep=None):
    require(isinstance(modules, dict) and 0 < len(modules) <= 4096, 'module count/type')
    require((load is None) == (dep is None), 'control files must be paired')
    by_name = {}
    for path, row in modules.items():
        require(re.fullmatch(r'lib/modules/[A-Za-z0-9_.-]+\.ko', path), 'module path')
        name = canonical(row['name'])
        require(name not in by_name, 'ambiguous normalized identity')
        by_name[name] = path
    edges = {}; missing = []
    for path, row in sorted(modules.items()):
        require(isinstance(row['depends'], list) and len(row['depends']) <= 4096, 'dependency list')
        names = [canonical(n) for n in row['depends']]
        require(len(names) == len(set(names)), 'duplicate normalized dependency')
        edges[path] = sorted(by_name[n] for n in names if n in by_name)
        missing.extend(dict(module=path, dependency=n) for n in names if n not in by_name)
    remaining = {p:set(ds) for p,ds in edges.items()}; order = []
    while remaining:
        ready = sorted(p for p,ds in remaining.items() if not ds)
        if not ready: break
        order.extend(ready)
        for p in ready: del remaining[p]
        for ds in remaining.values(): ds.difference_update(ready)
    result = dict(module_count=len(modules), declared_dependency_edges=sum(map(len, edges.values())),
        missing_declared_dependencies=missing, cycle_or_blocked_dependents=sorted(remaining),
        declared_graph_closed_and_acyclic=not missing and not remaining,
        proposed_dependency_first_order=order if not missing and not remaining else None,
        control_files_supplied=load is not None, control_files_checks_passed=None,
        symbol_import_dependencies_evaluated=False, userspace_loader_semantics_validated=False,
        runtime_loading_validated=False, module_abi_established=False, a0_complete=False,
        physical_action=False)
    if load is None: return result
    def lines(data):
        require(type(data) is bytes and len(data) <= 1024*1024, 'control file budget/type')
        return data.decode('ascii').splitlines()
    requested = []
    for name in lines(load):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+\.ko', name), 'modules.load syntax')
        path = 'lib/modules/'+name
        require(path in modules and path not in requested, 'modules.load missing/duplicate file')
        requested.append(path)
    require(requested, 'empty modules.load')
    table = {}
    for line in lines(dep):
        key, sep, tail = line.partition(':')
        require(sep and key.startswith('/') and key[1:] in modules and key[1:] not in table,
                'modules.dep key')
        ds = tail.split()
        require(all(p.startswith('/') and p[1:] in modules for p in ds), 'modules.dep target')
        ds = [p[1:] for p in ds]
        require(len(ds) == len(set(ds)), 'modules.dep duplicate target')
        table[key[1:]] = ds
    absent = sorted(set(modules)-table.keys())
    dep_pending = {p:set(ds) for p,ds in table.items()}
    while dep_pending:
        ready = {p for p,ds in dep_pending.items() if not ds}
        if not ready: break
        for name in ready: del dep_pending[name]
        for ds in dep_pending.values(): ds.difference_update(ready)
    omitted = [dict(module=p, dependency=d) for p,ds in edges.items() for d in ds
               if d not in table.get(p, [])]
    # This checks literal sequencing only. modprobe may resolve dependencies
    # recursively; a later entry is not, by itself, a runtime failure.
    rank = {p:i for i,p in enumerate(requested)}
    later = [dict(module=p, dependency=d) for p in requested for d in edges[p]
             if d not in rank or rank[d] >= rank[p]]
    result.update(control_files_checks_passed=not (missing or remaining or absent or omitted or dep_pending),
        modules_dep_missing_keys=absent, modules_dep_missing_declared_edges=omitted,
        modules_dep_cycle_or_blocked_dependents=sorted(dep_pending),
        modules_load_entries=len(requested), modules_load_unlisted=sorted(set(modules)-rank.keys()),
        literal_load_order_dependency_violations=later,
        literal_load_order_dependency_first=not later,
        literal_order_is_runtime_failure=False)
    return result


def inspect(vendor_boot=None):
    reference = json.loads(read_checked(INVENTORY, INVENTORY_PIN), object_pairs_hook=unique_object)
    modules = reference['modules']; controls = (None, None)
    mode = 'pinned_inventory_metadata_only'
    if vendor_boot is not None:
        pins = json.loads((INVENTORY.parent/'capture-a0-pins-hzc2.json').read_text())
        raw = read_checked(vendor_boot, pins['stock_raw']['vendor_boot.img'])
        inv = layout(raw)
        require(inv['kind'] == 'vendor_boot_v3', 'vendor boot v3 required')
        part = next(p for p in inv['parts'] if p['name'] == 'ramdisk')
        entries = cpio(gunzip(raw[part['start']:part['end']]))
        def regular(name):
            require(name in entries and entries[name]['kind'] == stat.S_IFREG, 'nonregular/missing entry')
            return entries[name]['data']
        actual = {p:module(regular(p))[0] for p in entries if p.endswith('.ko')}
        require(actual == modules, 'measured module inventory differs')
        controls = tuple(regular('lib/modules/'+n) for n in ('modules.load', 'modules.dep'))
        mode = 'pinned_stock_buffer_and_control_files'
    return dict(schema='S21-A0-MODULE-LOAD-PLAN-v1', mode=mode,
        inventory_pin=INVENTORY_PIN, vendor_boot_sha256=reference['vendor_boot_sha256'],
        result=audit(modules, *controls))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vendor-boot', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        result = inspect(a.vendor_boot)
        with a.output.open('x') as file: file.write(json.dumps(result, indent=2)+'\n')
    except (OSError, ValueError, KeyError, struct.error, zlib.error) as exc:
        p.exit(1, 'LOAD PLAN REFUSED: '+str(exc)+'\n')
    print('Declared graph closed/acyclic:', result['result']['declared_graph_closed_and_acyclic'])
    print('Control files checked:', result['result']['control_files_supplied'])
    return 0 if result['result']['declared_graph_closed_and_acyclic'] and result['result']['control_files_checks_passed'] is True else 2


if __name__ == '__main__': raise SystemExit(main())
