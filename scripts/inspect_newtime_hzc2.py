#!/usr/bin/env python3
"""Bounded ECT/NEWTIME decoding and the first-store prefix of HZC2 BL2.

Embedded selectors are candidates, not observations of a phone. Host bounds
checks do not describe validation performed by the original firmware.
"""
import argparse
import hashlib
import json
import struct

from inspect_bl2_geometry_query import adrp_add
from inspect_bl2_geometry_record import expect, wide64
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_boot_metadata_hzc2 import c_string
from inspect_descriptor_provenance import copy_loop
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_monitor_preparation import word

REGISTRY, ENTRY = 0x309d0, 0x30b30
START, STORE, AFTER_STORE, ERROR = 0x193fc, 0x19694, 0x19698, 0x199fc
TEMPLATES = (
    (0x16278, '58000880 580008a1 580008c2 a8c11003 a8811043 eb01001f 54ffffab d5033f9f d5033fdf d65f03c0'),
    (0x193fc, 'a9ae7bfd 910003fd a90153f3 a9025bf5 a90363f7 a9046bf9 a90573fb f90047a0 910003e0 f90037a0 d2813780 f2a2b0c0 f90087a0 f94047a0 eb1f001f 540000aa f94047a0 92407c00 f9004fa0 14000003 f94047a0 f9004fa0 d00000a0 91352000 94000c40 f90083a0 f94083a0 eb1f001f 54000061 52800060 14000162 d2822221 f2a22221 f94083a0 94000cee f9007fa0 f9407fa0 eb1f001f 54000061 52800040 14000158 f9407fa0 b9401000 2a0003e1 b90087a1 93407c20 d1000400 f9007ba0 93407c20 f9003ba0 f9003fbf a9470ba1 aa0103e3 d37afc60 aa0203e3 d37ae478 aa180018 aa0103e0 d37ae417 f9407fa0 b9401000 f9407fa0 f9400c00 f90077a0 f9407fa0 b9401000 51000400 93407c01 d1000421 f90073a1 93407c01 aa0103fb d280001c d37aff61 d37ae796 aa160036 d37ae775 93407c01 aa0103f9 d280001a d37aff21 d37ae754 aa140034 d37ae733 93407c00 d37df000 91001c00 91003c00 d344fc00 d37cec00 cb2063ff 910003e0 91001c00 d343fc00 d37df000 f9006fa0 f9406fa0 f90057a0 b9011fbf 1400002e b9811fa1 b98087a0 9b007c20 d37df000 f94077a1 8b000020 52800001 94000be6 f90053a0 f94053a1 f9404fa0 eb00003f 540003c1 b9011bbf 52800020 b90117a0 14000014 f94057a1 b9811ba0 d37df000 8b000033 b9811fa1 b98087a0 9b007c20 d37df000 f94077a1 8b000020 b94117a1 94000bd1 f9000260 b9411ba0 11000400 b9011ba0 b94117a0 11000400 b90117a0 f9407fa0 b9401001 b94117a0 6b00003f 54fffd2c 14000009 b9411fa0 11000400 b9011fa0 f9407fa0 b9401401 b9411fa0 6b00003f 54fff9ec f9407fa0 b9401000 51000400 b900b3a0 f94053a1 f9404fa0 eb00003f 54000060 52800020 140000e1 f00000a0 91148000 f9400000 f9006ba0 f9406ba0 f94047a1 f9000001'),
    (0x1b37c, 'aa0003e5 d2800003 386368a4 38636822 4b020082 13001c40 35000060 91000463 35ffff44 d65f03c0'),
    (0x1b3d8, 'd00000a1 f9460420 f2400802 54000080 cb020000 91002000 f9060420 d65f03c0 d00000a1 a9bf7bfd 910003fd f9460423 8b204060 f9060420 97fffff2 aa0303e0 a8c17bfd d65f03c0 f9400002 b9400042 b9000022 f9400001 91001021 f9000001 d65f03c0'),
    (0x1c3dc, 'a9bd7bfd 910003fd f9000fa0 b40008c0 aa0003ea aa0103e6 52800300 97fffc00 aa0003e4 b5000060 12800020 1400003f aa0003e1 910063a0 97fffc03 91001081 910063a0 97fffc00 91002081 910063a0 97fffbfd b9800880 531b6800 97fffbf0 f9000880 d2800003 b4fffe00 b9400880 6b03001f 5400026d f9400fa2 d37be868 f9400889 910063a0 aa0203e5 91002042 8b080121 91002021 b84044a7 f9000fa5 b85fc045 f9000fa2 2a0703e2 aa058042 f8286922 97fffbe4 91000463 17ffffec d2800005 b9400880 6b05001f 5400026d f9400883 9100a3a0 8b051463 b9400861 8b010141 f90017a1 91003061 97fffbd6 91004061 9100a3a0 97fffbd3 91005061 9100a3a0 97fffbd0 910004a5 f94017a0 f9000c60 17ffffec 52800000 f9000cc4 14000002 12800000 a8c37bfd d65f03c0'),
    (0x1c540, '531f7821 93407c21 91000422 b8627802 b8617800 aa028000 d65f03c0 a9bf7bfd aa0003e9 d2800006 900000aa 910003fd f10030df 2a0603e7 54000180 d37be8c0 91274148 f8686801 aa0903e0 97fffb7c 910004c6 35fffee0 937b7ce7 8b070107 f9400ce0 14000002 d2800000 a8c17bfd d65f03c0'),
    (0x1c83c, 'b40001c0 b9400806 d2800003 6b0300df 5400014d d37be864 f9400805 91000463 8b0400a2 f86468a4 eb01009f 54ffff01 aa0203e0 d65f03c0 d2800000 d65f03c0'),
    (0x1ca68, 'b00000a0 d2860001 91302002 f2a042a1 f9060401 f9000441 a8c17bfd 17ffff7e'),
    (0x1c92c, '900000b5 52800017 912742b5 910642b8'),
    (0x1c9ac, '91302281 b9404fa0 f9400262 f9400423 d1004261 8b000060 d63f0040 35fff6e0'),
)


def parse_newtime(block):
    """Parse only the supported 32/64-bit table dialect with strict host bounds."""
    if len(block) < 12 or len(block) > 0x14000:
        raise ValueError('NEWTIME block length outside host bounds')
    parser_version, version, count = struct.unpack_from('<I4sI', block)
    if parser_version != 1 or not 1 <= count <= 256 or 12+12*count > len(block):
        raise ValueError('unsupported NEWTIME version or descriptor count')
    entries, spans = [], []
    for i in range(count):
        key, offset = struct.unpack_from('<QI', block, 12+i*12)
        if offset % 4 or offset < 12+12*count or offset+12 > len(block):
            raise ValueError('NEWTIME body overlaps directory or exceeds block')
        mode, columns, rows = struct.unpack_from('<III', block, offset)
        if mode not in (1, 2) or not 1 <= columns <= 512 or not 1 <= rows <= 512:
            raise ValueError('unsupported NEWTIME mode or dimensions')
        width = 4 if mode == 1 else 8
        end = offset+12+columns*rows*width
        if end > len(block) or any(offset < b and a < end for a, b in spans):
            raise ValueError('NEWTIME cells exceed block or overlap another body')
        if any(item['key'] == key for item in entries):
            raise ValueError('duplicate NEWTIME key')
        spans.append((offset, end))
        cells = struct.unpack_from('<'+('I' if width == 4 else 'Q')*(columns*rows), block, offset+12)
        entries.append(dict(key=key, offset=offset, mode=mode, columns=columns, rows=rows,
                            cells=cells, end=end))
    return dict(parser_version=parser_version, version=version, entries=entries)


def embedded(data):
    copy = copy_loop(data, 0x16278, 16)
    first, last = (int(v, 16)-NOMINAL_DELTA for v in copy['source'])
    if (first, last) != (0x69000, 0x7d000):
        raise ValueError('ECT source mapping changed')
    raw = data[first:last]
    if raw[:8] != b'PARA007n':
        raise ValueError('ECT signature/version changed')
    total, count = struct.unpack_from('<II', raw, 8)
    if not 1 <= count <= 32 or not 16 <= total+4 <= len(raw):
        raise ValueError('ECT directory bounds invalid')
    cursor, directory = 16, []
    for _ in range(count):
        if cursor+4 > total+4:
            raise ValueError('truncated ECT name length')
        length = word(raw, cursor); cursor += 4
        if not 1 <= length <= 32 or cursor+length+1 > total+4:
            raise ValueError('ECT name bounds invalid')
        name = raw[cursor:cursor+length].decode('ascii')
        if raw[cursor+length] != 0:
            raise ValueError('ECT name not terminated')
        cursor += (length+4) & ~3
        if cursor+4 > total+4:
            raise ValueError('truncated ECT block offset')
        offset = word(raw, cursor); cursor += 4
        if offset % 4 or not cursor <= offset < total+4:
            raise ValueError('ECT block offset outside declared extent')
        directory.append((name, offset))
    offsets = [off for _, off in directory]
    if len(set(offsets)) != count or len({n for n, _ in directory}) != count or min(offsets) < cursor:
        raise ValueError('ECT directory has duplicates or overlap')
    blocks = {name: (off, min([v for v in offsets if v > off]+[total+4])) for name, off in directory}
    if 'NEWTIME' not in blocks:
        raise ValueError('ECT NEWTIME block missing')
    off, end = blocks['NEWTIME']
    block = raw[off:end]
    return dict(copy=copy, source_file=first, header_total=total, directory=directory,
                block_file=first+off, block_end=first+end, raw_block=block,
                parsed=parse_newtime(block))


def selection(table, value):
    if type(value) is not int or not 0 <= value < 1 << 64:
        raise ValueError('selection input must be an unsigned u64')
    key = value & 0xffffffff if value >> 63 else value
    for row in range(table['rows']):
        cells = table['cells'][row*table['columns']:(row+1)*table['columns']]
        if cells[0] == key:
            return dict(row=row, comparison_key=key, stored_input=value, tail=cells[1:])
    return None


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    for pc, template in TEMPLATES:
        expect(data, pc, template)
    raw = embedded(data)
    parsed = raw['parsed']
    tables = parsed['entries']
    special = [t for t in tables if t['key'] == 0x11111111]
    if len(special) != 1 or (special[0]['mode'], special[0]['columns'], special[0]['rows']) != (2, 17, 22):
        raise ValueError('selected table shape changed')
    table = special[0]
    names = [c_string(data, struct.unpack_from('<Q', data, REGISTRY+i*32)[0]-NOMINAL_DELTA) for i in range(12)]
    pointer = struct.unpack_from('<Q', data, ENTRY+16)[0]
    if names[-1] != 'NEWTIME' or pointer-NOMINAL_DELTA != 0x1c3dc or word(data, ENTRY+8) != 7:
        raise ValueError('NEWTIME registry binding changed')
    source = wide64(data, (0x1ca6c, 0x1ca74), 1)
    if source-NOMINAL_DELTA != raw['source_file'] or adrp_add(data, 0x1c568, 0x1c580) != REGISTRY:
        raise ValueError('ECT input or registry derivation changed')
    row0 = selection(table, 0xcafe)
    row10 = selection(table, 0x1000860000110)
    if row0 is None or row10 is None or (row0['row'], row10['row']) != (0, 10):
        raise ValueError('selected embedded rows changed')
    pcs = sorted(pc for a, t in TEMPLATES for pc in range(a, a+4*len(t.split()), 4))
    indexed = b''.join(struct.pack('<II', pc, word(data, pc)) for pc in pcs)
    return dict(mode='static_newtime_embedded_selection', sboot_sha256=IMAGES['sboot'][1],
        ect=dict(copy=raw['copy'], nominal_parser_source=hex(source), source_file=hex(raw['source_file']),
                 header_total_size=raw['header_total'], directory=[dict(name=n, offset=hex(o)) for n, o in raw['directory']],
                 live_source_and_parser_initialization_verified=False),
        registry=dict(file=hex(REGISTRY), count=12, stride=32, names=names, entry=hex(ENTRY),
                      parser_nominal='0x1c3dc', initial_handle=hex(struct.unpack_from('<Q', data, ENTRY+24)[0]),
                      name_lookup='0x1c55c', key_lookup='0x1c83c', parsed_entry_stride=32),
        newtime=dict(file_interval=[hex(raw['block_file']), hex(raw['block_end'])],
            sha256=hashlib.sha256(raw['raw_block']).hexdigest(), parser_version=parsed['parser_version'],
            version=parsed['version'].decode('ascii'), table_count=len(tables),
            table_keys=[hex(t['key']) for t in tables],
            special=dict(key='0x11111111', mode=table['mode'], columns=table['columns'], rows=table['rows'],
                body_file=hex(raw['block_file']+table['offset']), data_file=hex(raw['block_file']+table['offset']+12),
                selectors=[hex(table['cells'][r*table['columns']]) for r in range(table['rows'])],
                row_zero=dict(selector='0xcafe', tail_keys=[hex(v) for v in row0['tail']]),
                row_ten=dict(selector='0x1000860000110', tail_keys=[hex(v) for v in row10['tail']]),
                selected_row_on_phone_observed=False)),
        first_store=dict(prefix=[hex(START), hex(AFTER_STORE)], pc=hex(STORE),
            input_save='0x19418: frame+136', comparison_key='input_low32_if_bit63_set_else_input_u64',
            comparison_spill='frame+152', row_copy='16 u64 cells after a matching first column for this table',
            scratch_bytes=144, original_input_reloaded='0x19690', destination_pointer_cell='0x30520',
            error_codes=dict(name_missing=3, key_missing=2, row_miss=1),
            zero_row_or_corrupt_table_behavior_modelled=False,
            arbitrary_runtime_aliases_and_callees_verified=False,
            later_callback_effects_modelled=False),
        instructions=dict(words=len(indexed)//8, index_sha256=hashlib.sha256(indexed).hexdigest()),
        firmware_executed=False, phone_record_or_memory_map_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        parser.exit(2, f'inspect_newtime_hzc2: {exc}\n')
    print(json.dumps(result, indent=2))
