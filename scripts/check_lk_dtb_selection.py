#!/usr/bin/env python3
"""Read-only HZC2 DT table selection and DPM target audit; no merge or flash."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from check_lk_v3_layout import align, checked_slice, read_input, require
from inspect_proton import fdt_nodes, wire
from inspect_sboot_hzc2 import inspect

DPM_SHA256 = 'e4f80e53094bdcadb3e379cdf91a37bd295979c8ea251505a311a8294eec0f8d'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_table(data):
    require(len(data) >= 32, 'short Android DT table')
    magic, total, header, stride, count, entries, page, version = struct.unpack_from('>8I', data)
    # The traced loop starts at header_size and advances by 32, not arbitrary stride.
    require(magic == 0xd7b7ab1e and 32 <= total <= len(data), 'invalid DT table bounds/magic')
    require(header == entries == stride == 32 and version == 0,
            'DT table outside traced 32-byte v0 profile')
    require(0 < count <= 128 and count*stride <= total-entries, 'invalid DT entry count')
    result = []
    for index in range(count):
        pos = entries+index*stride
        size, offset, ident, rev, lo_be, hi_be, custom2, custom3 = struct.unpack_from('>8I', data, pos)
        require(entries+count*stride <= offset <= total and size <= total-offset,
                'DT entry outside table data')
        blob = bytes(checked_slice(data, offset, size, 'DT entry'))
        wire.validate_dtb(blob)
        # 0x148df0 compares REV(custom1) with 0xff. The other branch uses raw
        # little-endian loads for both limits; reproduce that behavior exactly.
        encoding = 'big' if hi_be <= 0xff else 'little'
        lo, hi = (int.from_bytes(data[pos+n:pos+n+4], encoding) for n in (16, 20))
        require(lo <= hi, 'inverted effective revision range')
        result.append(dict(index=index, file_offset=offset, size=size,
                           revision_min=lo, revision_max=hi, range_encoding=encoding,
                           id=ident, rev=rev, custom2=custom2, custom3=custom3,
                           sha256=digest(blob)))
    return dict(total_size=total, page_size=page, entries=result)


def select(table, revision):
    require(0 <= revision <= 0xffffffff, 'revision must fit unsigned 32 bits')
    for entry in table['entries']:
        if entry['revision_min'] <= revision <= entry['revision_max']:
            return entry
    raise ValueError('no DT entry matches revision scenario '+hex(revision))


def entry_blob(data, entry):
    return bytes(checked_slice(data, entry['file_offset'], entry['size'], 'selected DT'))


def audit(vendor, dtbo, dpm, revision):
    require(len(vendor) >= 2112 and vendor[:8] == b'VNDRBOOT', 'invalid vendor header')
    require(struct.unpack_from('<II', vendor, 8) == (3, 4096)
            and struct.unpack_from('<I', vendor, 2096)[0] == 2112,
            'requires vendor v3 with 4096-byte pages')
    ramdisk = struct.unpack_from('<I', vendor, 24)[0]
    size = struct.unpack_from('<I', vendor, 2100)[0]
    offset = align(2112)+align(ramdisk)
    region = bytes(checked_slice(vendor, offset, size, 'vendor DT region'))
    base_table, overlay_table = parse_table(region), parse_table(dtbo)
    base, overlay = select(base_table, revision), select(overlay_table, revision)
    nodes = fdt_nodes(entry_blob(region, base))
    require(len(dpm) >= 40, 'short DPM')
    dpm_size = struct.unpack_from('>I', dpm, 4)[0]
    dpm_nodes = fdt_nodes(bytes(checked_slice(dpm, 0, dpm_size, 'DPM FDT')))
    symbols = nodes.get('/__symbols__', {})
    targets = {}
    for symbol, locations in dpm_nodes.get('/__fixups__', {}).items():
        raw = symbols.get(symbol, b'')
        require(raw.endswith(b'\0') and raw.count(b'\0') == 1, 'missing/invalid base symbol: '+symbol)
        path = raw[:-1].decode('ascii')
        require(path in nodes, 'base symbol path missing: '+symbol)
        require(locations.endswith(b'\0'), 'unterminated DPM fixup')
        targets[symbol] = dict(base_target=path,
                               fixups=locations[:-1].decode('ascii').split('\0'))
    return dict(mode='static_selection_model', runtime_observed=False,
                revision_scenario=hex(revision), selection_rule='first inclusive match',
                inputs={name:dict(size=len(data), sha256=digest(data)) for name, data in
                        (('vendor_boot', vendor), ('dtbo', dtbo), ('dpm', dpm))},
                vendor_region_offset=hex(offset), base_table=base_table,
                overlay_table=overlay_table, selected_base=base, selected_overlay=overlay,
                dpm=dict(fdt_size=dpm_size, target_symbols=targets),
                overlay_merge_performed=False, is_final_fdt=False,
                limits=['Explicit revision scenario, not a device revision reading',
                        'Conservative table/FDT bounds checks differ from firmware checks',
                        'No UFDT execution, DPM signature or later dynamic edits verified'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    parser.add_argument('vendor_boot', type=Path, help='raw vendor_boot.img')
    parser.add_argument('dtbo', type=Path, help='raw dtbo.img')
    parser.add_argument('dpm', type=Path, help='raw HZC2 dpm.img from BL')
    parser.add_argument('--revision', required=True, type=lambda s: int(s, 0),
                        help='explicit revision scenario, not detected from the phone')
    args = parser.parse_args()
    try:
        firmware = inspect(args.sboot)
        vendor, dtbo, dpm = (read_input(p) for p in (args.vendor_boot, args.dtbo, args.dpm))
        require(digest(dpm) == DPM_SHA256, 'requires exact HZC2 DPM image')
        report = audit(vendor, dtbo, dpm, args.revision)
        report['firmware_sha256'] = firmware['sha256']
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(1, f'check_lk_dtb_selection: {exc}\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
