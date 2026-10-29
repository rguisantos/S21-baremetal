#!/usr/bin/env python3
"""Bounded MARGIN audit: symbolic handles, actual name table and case filtering."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_hzc2 import embedded
from inspect_newtime_jump_tables_hzc2 import DELTA, adr_target, adrp_add_base, case_walk, cmp_w0_limit, entries, u32

MASK64 = (1 << 64) - 1
RANGES = ((0x16094, 0x160c0), (0x1825c, 0x18270), (0x19038, 0x19120),
          (0x1a668, 0x1a73c), (0x1aab4, 0x1ab84), (0x1ad60, 0x1aea8),
          (0x1b0dc, 0x1b148), (0x1b37c, 0x1b3a4), (0x1b3d8, 0x1b4a0),
          (0x1b96c, 0x1bab4), (0x1c55c, 0x1c5b4), (0x1c700, 0x1c770),
          (0x1c87c, 0x1c9f4), (0x1ca44, 0x1ca98))
SELECTED = {
    0x160a0: ('bl', '0x1ca44'), 0x160bc: ('bl', '0x17e14'),
    0x1825c: ('adrp', 'x1, 0x30000'),
    0x18260: ('add', 'x1, x1, #0x520'),
    0x18264: ('add', 'x1, x1, #0x410'),
    0x18268: ('add', 'x0, x1, w0, uxtw #3'),
    0x19070: ('adrp', 'x22, 0x2f000'),
    0x19080: ('add', 'x19, x22, #0xd50'),
    0x190ac: ('add', 'x0, x19, #0x80'),
    0x190b4: ('bl', '0x1c55c'), 0x190c0: ('mov', 'x27, x0'),
    0x19104: ('mov', 'x3, x27'), 0x1911c: ('bl', '0x1aab4'),
    0x1ab0c: ('mov', 'x23, x3'),
    0x1ab1c: ('bl', '0x1825c'), 0x1ab24: ('str', 'x0, [x29, #144]'),
    0x1ab74: ('ldr', 'x1, [x29, #144]'),
    0x1ab7c: ('bl', '0x1c700'),
    0x1ab80: ('mov', 'x26, x0'),
    0x1ad68: ('bl', '0x1c55c'), 0x1ad6c: ('cbz', 'x0, 0x1ad7c'),
    0x1ad70: ('ldr', 'x1, [x29, #144]'),
    0x1ad74: ('bl', '0x1c700'), 0x1ad78: ('mov', 'x26, x0'),
    0x1ad84: ('cmp', 'w0, #0x13'),
    0x1adac: ('mov', 'w27, #0xff'), 0x1ae10: ('mov', 'w27, #0xff'),
    0x1b0dc: ('cbz', 'x26, 0x1b148'),
    0x1b0ec: ('ldr', 'w4, [x26, #12]'),
    0x1b0f8: ('ldr', 'x8, [x26, #32]'),
    0x1b100: ('madd', 'w4, w4, w1, w19'),
    0x1b114: ('b.eq', '0x1b138'),
    0x1b134: ('strb', 'w3, [x2, #3]'),
    0x1b408: ('add', 'x0, x3, w0, uxtw'),
    0x1b47c: ('and', 'w1, w0, #0xfffffffc'),
    0x1b480: ('add', 'w1, w1, #0x4'),
    0x1b48c: ('add', 'x0, x2, w0, uxtw'),
    0x1b988: ('mov', 'x8, x1'), 0x1b994: ('mov', 'x6, x0'),
    0x1b9c0: ('ldrsw', 'x0, [x6, #8]'),
    0x1b9c8: ('mul', 'w0, w1, w0'),
    0x1ba24: ('str', 'x3, [x2, x1]'),
    0x1ba2c: ('str', 'w1, [x0, #8]'),
    0x1ba68: ('add', 'x1, x3, #0xc'),
    0x1ba70: ('add', 'x1, x3, #0x10'),
    0x1ba7c: ('cmp', 'w10, #0x1'),
    0x1ba84: ('b.le', '0x1ba94'),
    0x1ba88: ('stp', 'xzr, x1, [x3, #24]'),
    0x1ba8c: ('str', 'w7, [x3, #40]'),
    0x1ba94: ('stp', 'x1, xzr, [x3, #24]'),
    0x1baa4: ('str', 'x6, [x8, #24]'),
    0x1c728: ('cmp', 'w10, w8'), 0x1c72c: ('b.le', '0x1c758'),
    0x1c8fc: ('ldr', 'w0, [x0, #8]'),
    0x1c97c: ('ldur', 'w2, [x19, #-8]'),
    0x1c9b0: ('ldr', 'w0, [x29, #76]'),
    0x1c9b4: ('ldr', 'x2, [x19]'),
    0x1c9bc: ('sub', 'x1, x19, #0x10'),
    0x1c9c0: ('add', 'x0, x3, x0'), 0x1c9c4: ('blr', 'x2'),
    0x1ca78: ('str', 'x1, [x0, #3080]'),
    0x1ca7c: ('str', 'x1, [x2, #8]'),
}


def s32(value):
    u32(value)
    return value - (1 << 32) if value & 0x80000000 else value


def name_skip(length):
    """1b45c/1b480 both write W registers before the final X addition."""
    u32(length)
    counter = (length + 1) & 0xffffffff
    return counter if counter % 4 == 0 else ((counter & 0xfffffffc) + 4) & 0xffffffff


def bump_step(cursor, size):
    if type(cursor) is not int or not 0 <= cursor <= MASK64:
        raise ValueError('expected u64 cursor')
    u32(size)
    after_add = (cursor + size) & MASK64
    return cursor, ((after_add + 7) & MASK64) & ~7


def record_request(count):
    u32(count)
    return (48 * count) & 0xffffffff


def record_layout(version, data_pointer):
    if type(data_pointer) is not int or not 0 <= data_pointer <= MASK64:
        raise ValueError('expected u64 data pointer')
    return {24: 0, 32: data_pointer, 40: 6250} if s32(version) > 1 else {24: data_pointer, 32: 0}


def cbytes(value):
    if isinstance(value, str):
        value = value.encode('ascii')
    if not isinstance(value, bytes):
        raise ValueError('expected host string fixture')
    return value.split(b'\0', 1)[0]


def lookup_record(count, records, name):
    """Host fixture for strcmp/count; fixture bounds are not firmware guards."""
    if records is None or name is None or s32(count) <= 0:
        return None
    if len(records) < count:
        raise ValueError('host record fixture shorter than positive count')
    for i in range(count):
        if cbytes(records[i]) == cbytes(name):
            return i
    return None


def parse_margin(block):
    """Only the selected version-2 byte matrices, with independent host bounds."""
    if not 12 <= len(block) <= 0x10000:
        raise ValueError('host MARGIN extent')
    version, text, count = struct.unpack_from('<I4sI', block)
    if version != 2 or count > 64:
        raise ValueError('unsupported host MARGIN version/count')
    cursor, directory = 12, []
    for _ in range(count):
        if cursor + 4 > len(block):
            raise ValueError('truncated MARGIN name length')
        length, = struct.unpack_from('<I', block, cursor)
        cursor += 4
        skip = name_skip(length)
        if not 1 <= length <= 32 or cursor + skip + 4 > len(block) or block[cursor+length] != 0:
            raise ValueError('host MARGIN name bounds/termination')
        name = block[cursor:cursor+length].decode('ascii')
        name_at = cursor
        cursor += skip
        offset, = struct.unpack_from('<I', block, cursor)
        cursor += 4
        directory.append((name, name_at, offset))
    records, spans = [], []
    for name, name_at, offset in directory:
        if offset % 4 or offset < cursor or offset + 8 > len(block):
            raise ValueError('host MARGIN record offset')
        columns, rows = struct.unpack_from('<II', block, offset)
        end = offset + 8 + columns * rows
        if not 1 <= columns <= 512 or not 1 <= rows <= 512 or end > len(block):
            raise ValueError('host MARGIN dimensions/extent')
        if any(offset < b and a < end for a, b in spans) or any(r['name'] == name for r in records):
            raise ValueError('host MARGIN overlap/duplicate')
        spans.append((offset, end))
        raw = block[offset+8:end]
        records.append(dict(name=name, name_offset=name_at, offset=offset, columns=columns,
            rows=rows, data_offset=offset+8, end=end, data_hex=raw.hex(),
            data_sha256=hashlib.sha256(raw).hexdigest(),
            byte_counts={str(v): n for v, n in sorted(Counter(raw).items())}))
    return dict(version=version, version_text=text.decode('ascii'), count=count,
                directory_end=cursor, records=records)


def case_filter(command_names, record_names, tags):
    present = [i for i, name in enumerate(command_names) if lookup_record(len(record_names), record_names, name) is not None]
    if any(i not in tags or not tags[i] for i in present):
        raise ValueError('matched case tag not established')
    secondary = [i for i in present if any(t != 255 for t in tags[i])]
    return dict(present=present, secondary=secondary,
                fast_alias_intersection=sorted(set(present) & {2, 3}))


def margin_index(columns, row, column, size):
    for value in (columns, row, column, size):
        u32(value)
    index = (columns * row + column) & 0xffffffff
    return dict(index=index, in_host_matrix=index < size)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    cmd = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
           str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(cmd + ['--version'], text=True).splitlines()[0]
    lines = {}
    for lo, hi in RANGES:
        lines.update(parse_lines(subprocess.check_output(cmd + ['-D', '-z', '-b', 'binary', '-m',
            'aarch64', f'--start-address={lo}', f'--stop-address={hi}', str(Path(path).resolve())], text=True)))
    if set(lines) != {p for lo, hi in RANGES for p in range(lo, hi, 4)}:
        raise ValueError('GNU coverage differs')
    relative = 0
    for pc, (word, op, args) in lines.items():
        if word != struct.unpack_from('<I', data, pc)[0] or op in ('.inst', 'udf'):
            raise ValueError('GNU word/instruction differs')
        kind, target = flow(word, pc)
        if kind in ('b', 'bl', 'conditional'):
            if target != direct_target(op, args):
                raise ValueError('GNU relative target differs')
            relative += 1
    for pc, want in SELECTED.items():
        if lines[pc][1:] != want:
            raise ValueError(f'GNU selected operands differ at {pc:#x}')
    callback = case_walk(data, [0x1b96c], 0x1b96c, 0x1bab4)
    if callback['exits'] != [dict(pc='0x1bab0', reason='ret')]:
        raise ValueError('callback local frontier differs')
    leaf = case_walk(data, [0x1a668], 0x1a668, 0x1a73c)
    if leaf['calls'] or leaf['exits'] != [dict(pc='0x1a738', reason='ret')] or any(
            re.search(r'\b[wx]27\b', lines[p][2]) for p in range(0x1a668, 0x1a73c, 4)):
        raise ValueError('case0 leaf tag preservation differs')
    if any(re.search(r'\b[wx](?:[6-9]|10)\b', lines[p][2]) for p in range(0x1b3d8, 0x1b4a0, 4)):
        raise ValueError('helpers reference held callback registers')
    ect = embedded(data)
    origin, directory, total = ect['source_file'], ect['directory'], ect['header_total']
    margin_offset = dict(directory)['MARGIN']
    end_offset = min([o for _, o in directory if o > margin_offset] + [total])
    start, end = origin + margin_offset, origin + end_offset
    parsed = parse_margin(data[start:end])
    registry = 0x30a30
    name_pointer, = struct.unpack_from('<Q', data, registry)
    length, = struct.unpack_from('<I', data, registry+8)
    pointer, handle = struct.unpack_from('<QQ', data, registry+16)
    if data[name_pointer-DELTA:name_pointer-DELTA+length] != b'MARGIN' or pointer-DELTA != 0x1b96c:
        raise ValueError('selected registry differs')
    names_base = adrp_add_base(lines[0x1825c][0], lines[0x18260][0], 0x1825c) + 0x410
    maximum = cmp_w0_limit(lines[0x1ad84][0])
    names = [data[names_base+8*i:names_base+8*(i+1)].split(b'\0', 1)[0].decode('ascii') for i in range(maximum+1)]
    switch_array = adrp_add_base(lines[0x1ad8c][0], lines[0x1ad94][0], 0x1ad8c)
    anchor = adr_target(lines[0x1ad9c][0], 0x1ad9c)
    targets = entries(data[switch_array:switch_array+2*(maximum+1)], 16, anchor, anchor, 0x1aff0)
    record_names = [r['name'] for r in parsed['records']]
    tags, tag_proofs = {}, []
    for index, name in enumerate(names):
        if lookup_record(len(record_names), record_names, name) is None:
            continue
        pc = targets[index]['target'] + 4
        if pc not in lines:
            raise ValueError('matched case outside selected tag witnesses')
        word = lines[pc][0]
        if word & 0xffe0001f != 0x5280001b:
            raise ValueError('matched tag definition differs')
        tags[index] = {(word >> 5) & 65535}
        tag_proofs.append(dict(index=index, case=hex(targets[index]['target']), pc=hex(pc), value=(word >> 5) & 65535))
    selected = case_filter(names, record_names, tags)
    driver_name = adrp_add_base(lines[0x19070][0], lines[0x19080][0], 0x19070) + 0x80
    if data[driver_name:data.index(0, driver_name)] != b'MARGIN':
        raise ValueError('driver lookup name differs')
    return dict(mode='static_newtime_margin_hzc2', sboot_sha256=IMAGES['sboot'][1],
        nominal_delta=hex(DELTA), ect=dict(origin_file=hex(origin), header_total=hex(total),
            directory=[dict(name=n, offset=hex(o)) for n, o in directory]),
        registry=dict(entry_file=hex(registry), callback_initial=hex(pointer), handle_cell='0x30a48',
            initial_handle=hex(handle), length_read_width=4),
        margin=dict(block_file=hex(start), block_end=hex(end), bytes=end-start, parsed=parsed),
        dispatcher=dict(pc='0x1c9c4', X0=hex(origin+DELTA+margin_offset), X1=hex(registry+DELTA), X2=hex(pointer),
            conditions='MARGIN directory entry reached; earlier callbacks returned success; registry/blob/mapping preserved',
            matching='registry-length byte comparison; not proof of full directory-name equality for malformed inputs'),
        callback=dict(local_walk=callback, header_object='H=alloc(24), runtime address unknown',
            records_object='R=alloc(u32(48*count)), runtime address unknown',
            fields={'H+0': 'u32 version=2', 'H+4': 'four version bytes', 'H+8': 'u32 count=2', 'H+16': 'R'},
            records=[dict(name=r['name'], record=f'R+{48*i}', field0=hex(start+DELTA+r['name_offset']),
                field8=r['offset'], field12=r['columns'], field16=r['rows'],
                layout=record_layout(parsed['version'], start+DELTA+r['data_offset'])) for i, r in enumerate(parsed['records'])],
            handle_publication='0x1baa4: M64[entry+24]=H on success; no concrete H/R inferred by omitting earlier allocations'),
        names=dict(source_pc='0x1825c', base_file=hex(names_base), names=names,
            previous_0x31930_claim_correct=False, static_bytes_not_runtime_observations=True),
        driver=dict(MARGIN_name_file=hex(driver_name), call='0x190b4',
            carried='X27 -> X3@0x19104 -> X23@0x1ab0c -> initial lookup at 0x1ab7c'),
        case_filter=dict(**selected, tags={str(i): sorted(t) for i, t in tags.items()}, tag_proofs=tag_proofs,
            no_Q_store_in_selected_preserved_MARGIN_path=not selected['secondary'],
            conditions='driver/registry handles are zero or refer to constructed MARGIN objects; switch and lookups use preserved bytes/names/records; frame and tags survive calls'),
        implications=['MIF/INTSCI are cases 0/19 with tag255; other selected names have no MARGIN record',
            'Q=B model at cases2/3 remains valid code, but its E-loop condition is absent in this selected preserved MARGIN dataset',
            'this does not establish global unreachability after mutation, other callers, aliases or hardware execution'],
        ordering=dict(earlier_call='0x160a0', later_call='0x160bc',
            proof='syntactic program order if both calls are reached and return normally',
            callback_execution_and_handle_preservation_observed=False),
        consumer=dict(record_fields=['+12 columns=12', '+32 matrix pointer'],
            index='u32(12*i + W19)', host_matrix_bytes=156,
            n_and_W19_bounds_proved=False, dimensions='13 rows x 12 columns'),
        external_audit=['0x31930 is a different zeroed area, not the table selected by 0x1825c',
            'positive-count lookup must stop at count, even if the host fixture has extra records',
            'name skip needs W32 wrap and allocator needs X64 wrap',
            'omitting eight preceding callbacks makes numeric object allocation addresses synthetic'],
        gnu=dict(version=version, words=len(lines), relative_targets=relative, selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(p), word=f'{w:08x}', op=op, args=args) for p, (w, op, args) in sorted(lines.items())],
        limits=['host bounds reject unsupported fixtures; they are not claimed firmware guards',
            'init gates, callback successes, object addresses, runtime n/W19 and mutations remain open',
            'slot47 caller, X0 origin and global binding preservation are not established'],
        firmware_executed=False, qemu_scope_extended=False, incoming_X0_of_slot47_resolved=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        report = inspect(args.sboot)
    except (OSError, ValueError, struct.error, UnicodeError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(report, indent=2))
