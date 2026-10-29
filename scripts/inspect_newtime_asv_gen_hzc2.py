#!/usr/bin/env python3
"""Independent bounded ASV/GEN audit: n, W19 and correction-loop positions."""
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
from inspect_newtime_jump_tables_hzc2 import u32
from inspect_newtime_margin_hzc2 import name_skip, parse_margin

RANGES = ((0x16428, 0x1643c), (0x19070, 0x19124), (0x19d04, 0x19e74),
          (0x1a26c, 0x1a5b0), (0x1a668, 0x1a73c), (0x1aab4, 0x1add4),
          (0x1ae0c, 0x1ae30), (0x1aff0, 0x1b148), (0x1b6c0, 0x1b900),
          (0x1c19c, 0x1c2bc), (0x1c690, 0x1c700), (0x1c770, 0x1c7e4))
SELECTED = {
    0x16430: ('smc', '#0x0'), 0x16434: ('mov', 'x0, x2'),
    0x190f4: ('mov', 'x1, x26'), 0x19108: ('mov', 'x2, x25'),
    0x1911c: ('bl', '0x1aab4'),
    0x19d10: ('mov', 'x1, #0xffffffffc400ffff'), 0x19d14: ('movk', 'x1, #0x2400'),
    0x19d8c: ('bl', '0x16428'), 0x19db0: ('ubfx', 'x1, x0, #16, #4'),
    0x19db4: ('strb', 'w1, [x19, #15]'), 0x19db8: ('ubfx', 'x1, x0, #20, #4'),
    0x19dbc: ('strb', 'w1, [x19, #16]'),
    0x19dcc: ('mov', 'x1, #0xffffffffc400ffff'), 0x19dd4: ('movk', 'x1, #0x2401'),
    0x19e18: ('mov', 'x1, #0xffffffffc400ffff'), 0x19e20: ('movk', 'x1, #0x2402'),
    0x19e2c: ('bl', '0x16428'), 0x19e60: ('lsr', 'w2, w0, #16'),
    0x19e64: ('bfxil', 'w1, w2, #0, #4'), 0x19e68: ('lsr', 'w2, w0, #20'),
    0x19e6c: ('bfi', 'w1, w2, #4, #4'), 0x19e70: ('strb', 'w1, [x19, #29]'),
    0x1ab94: ('bl', '0x1c690'), 0x1aba0: ('ldr', 'w23, [x0, #16]'),
    0x1ac14: ('add', 'x3, x22, x0'), 0x1ac18: ('ldr', 'w3, [x3, x1, lsl #2]'),
    0x1ac1c: ('str', 'w3, [x22, x1, lsl #2]'),
    0x1ac58: ('ldr', 'w3, [x3, x1, lsl #2]'), 0x1ac5c: ('str', 'w3, [x5, x1, lsl #2]'),
    0x1ace8: ('ldr', 'w0, [x22, #4]'), 0x1acec: ('str', 'w0, [x29, #152]'),
    0x1acf0: ('ldr', 'w0, [x22, #16]'), 0x1acf8: ('ldr', 'w0, [x27, #12]'),
    0x1acfc: ('cmp', 'w0, #0x6'), 0x1ad00: ('b.le', '0x1ad20'),
    0x1ad24: ('stp', 'wzr, w0, [x29, #132]'),
    0x1adb8: ('ldrb', 'w19, [x0, #15]'), 0x1adbc: ('ldrb', 'w0, [x0, #29]'),
    0x1adc0: ('sbfx', 'x0, x0, #0, #4'), 0x1adc4: ('add', 'w19, w19, w0'),
    0x1ae1c: ('ldrb', 'w19, [x0, #16]'), 0x1ae20: ('ldrb', 'w0, [x0, #29]'),
    0x1ae24: ('sbfx', 'x0, x0, #4, #4'), 0x1ae28: ('add', 'w19, w19, w0'),
    0x1b020: ('ldr', 'w0, [x2, x0]'), 0x1b030: ('ldr', 'w4, [x3, #4]'),
    0x1b034: ('cbnz', 'w4, 0x1b1a8'), 0x1b044: ('ldr', 'w4, [x28, #20]'),
    0x1b0bc: ('csel', 'w19, w19, w4, eq'),
    0x1b0dc: ('cbz', 'x26, 0x1b148'), 0x1b0e0: ('mov', 'w6, w23'),
    0x1b100: ('madd', 'w4, w4, w1, w19'), 0x1b104: ('ldrb', 'w8, [x8, x4]'),
    0x1b13c: ('cmp', 'x1, x6'),
    0x1b7d4: ('add', 'x1, x4, #0x10'), 0x1b7dc: ('bl', '0x1b420'),
    0x1b8a0: ('stp', 'xzr, x2, [x3, #24]'),
    0x1c278: ('add', 'x1, x3, #0xc'), 0x1c290: ('add', 'x1, x3, #0x10'),
    0x1c2a0: ('ldr', 'x0, [x29, #56]'), 0x1c2a4: ('str', 'x0, [x3, #24]'),
}


def named_directory(block):
    if len(block) < 12:
        raise ValueError('host short named block')
    version, text, count = struct.unpack_from('<I4sI', block)
    if not 0 < count <= 128:
        raise ValueError('host directory count')
    cursor, entries = 12, {}
    for _ in range(count):
        if cursor + 4 > len(block):
            raise ValueError('host truncated name length')
        length, = struct.unpack_from('<I', block, cursor); cursor += 4
        if not 0 < length <= 64 or cursor + name_skip(length) + 4 > len(block):
            raise ValueError('host name bounds')
        if block[cursor + length] != 0:
            raise ValueError('host name termination')
        name = block[cursor:cursor + length].decode('ascii')
        cursor += name_skip(length)
        offset, = struct.unpack_from('<I', block, cursor); cursor += 4
        if name in entries:
            raise ValueError('host duplicate name')
        entries[name] = offset
    if len(set(entries.values())) != count or any(v < cursor or v % 4 or v >= len(block) for v in entries.values()):
        raise ValueError('host body offset bounds/duplicate')
    return version, text, entries


def gen_table(block, offset):
    if offset < 0 or offset + 8 > len(block):
        raise ValueError('host GEN header bounds')
    columns, rows = struct.unpack_from('<II', block, offset)
    end = offset + 8 + columns * rows * 4
    if not 1 <= columns <= 128 or not 1 <= rows <= 128 or end > len(block):
        raise ValueError('host GEN dimensions/bounds')
    cells = struct.unpack_from('<' + 'I' * (columns * rows), block, offset + 8)
    return dict(columns=columns, rows=rows, data_offset=offset + 8,
                cells=[list(cells[i * columns:(i + 1) * columns]) for i in range(rows)])


def selected_gen(m, v, key, compact=False):
    """Exact-name matched tables, stable metadata; optional selected MIF prefix."""
    if type(key) is not int or not 0 <= key <= 255:
        raise ValueError('expected host byte key')
    mm, vv = [list(r) for r in m], [list(r) for r in v]
    if not mm or not vv or any(len(r) < 5 for r in mm) or any(len(r) < 2 for r in vv):
        raise ValueError('short host GEN rows')
    if compact:
        if len(mm) < 4 or key != 0:
            raise ValueError('selected compaction needs MIF key0 and row3')
        mm[0][1:] = mm[3][1:]
        vv[0][1:] = vv[-1][1:]
    mr = next((r for r in mm if r[0] == key), mm[-1])
    vr = next((r for r in vv if r[0] == key), None)
    return dict(F152=mr[1], out_X4=mr[4], enabled=vr is not None and vr[1] != 0,
                selected_M=mr, selected_V=vr)


def w19(column_nibble, adjustment_nibble):
    if any(type(v) is not int or not 0 <= v <= 15 for v in (column_nibble, adjustment_nibble)):
        raise ValueError('expected two nibble fixtures')
    adjust = adjustment_nibble - 16 if adjustment_nibble & 8 else adjustment_nibble
    return (column_nibble + adjust) & 0xffffffff


def position_survey(rows, columns, matrix_file, data, ect_field_end):
    u32(rows); u32(columns)
    size = rows * columns
    if not 0 < rows <= 128 or not 0 < columns <= 128 or not 0 <= matrix_file <= len(data) - size:
        raise ValueError('host matrix extent')
    patterns = sorted({w19(a, b) for a in range(16) for b in range(16)})
    counts, inside, adjacent = Counter(), set(), []
    for value in patterns:
        for i in range(rows):
            index = (columns * i + value) & 0xffffffff
            if index < size:
                counts['in_matrix'] += 1; inside.add(index)
            elif index >= 0x80000000:
                counts['far_unsigned_offset'] += 1
            else:
                counts['past_matrix'] += 1
                at = matrix_file + index
                adjacent.append(dict(W19=value, i=i, index=index, source_file=hex(at),
                    byte=hex(data[at]) if at < len(data) else None,
                    within_header_total_plus4=at < ect_field_end + 4))
    return dict(n=rows, columns=columns, matrix_file=hex(matrix_file), matrix_bytes=size,
        possible_W19_patterns=[hex(v) for v in patterns], per_fixed_W19_reads=rows,
        union_distinct_inside_bytes=len(inside), pair_counts=dict(counts),
        adjacent=adjacent, actual_W19_observed=False)


def request_tag(first, second):
    if first & 0xff80001f != 0x92800001 or second & 0xff80001f != 0xf2800001:
        raise ValueError('expected MOVN/MOVK X1 pair')
    value = ~(((first >> 5) & 65535) << (((first >> 21) & 3) * 16)) & ((1 << 64) - 1)
    shift = ((second >> 21) & 3) * 16
    return (value & ~(65535 << shift)) | (((second >> 5) & 65535) << shift)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    cmd = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
           str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for lo, hi in RANGES:
        lines.update(parse_lines(subprocess.check_output(cmd + ['-D', '-z', '-b', 'binary', '-m',
            'aarch64', f'--start-address={lo}', f'--stop-address={hi}', str(Path(path).resolve())], text=True)))
    if set(lines) != {p for lo, hi in RANGES for p in range(lo, hi, 4)}:
        raise ValueError('GNU coverage differs')
    relative = 0
    for pc, (word, op, args) in lines.items():
        if word != struct.unpack_from('<I', data, pc)[0] or op in ('.inst', 'udf'):
            raise ValueError('GNU word differs')
        kind, target = flow(word, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, args) != target:
                raise ValueError('GNU relative target differs')
            relative += 1
    for pc, expected in SELECTED.items():
        if lines[pc][1:] != expected:
            raise ValueError(f'GNU operand differs at {pc:#x}')
    for lo, hi in ((0x1a26c, 0x1a294), (0x1a294, 0x1a5b0), (0x1a668, 0x1a73c)):
        if any(re.search(r'\b[wx]19\b', lines[pc][2]) or flow(lines[pc][0], pc)[0] in ('bl', 'blr')
               for pc in range(lo, hi, 4)):
            raise ValueError('selected callee W19 preservation differs')
    ect = embedded(data); origin = ect['source_file']; directory = dict(ect['directory'])
    blocks = {name: data[origin + off:origin + min([v for v in directory.values() if v > off] + [ect['header_total']])]
              for name, off in directory.items()}
    gv, _, gen = named_directory(blocks['GEN']); av, _, asv = named_directory(blocks['ASV'])
    if (gv, av) != (1, 3):
        raise ValueError('unsupported selected GEN/ASV version')
    margin = parse_margin(blocks['MARGIN'])
    domains = {}
    for name in ('MIF', 'INTSCI'):
        m = gen_table(blocks['GEN'], gen['M' + name]); v = gen_table(blocks['GEN'], gen['V' + name])
        a = asv[name]; columns, n, sub_count = struct.unpack_from('<III', blocks['ASV'], a)
        if not 0 < n <= 128 or not 0 < columns <= 128 or not 0 < sub_count <= 8:
            raise ValueError('unsupported host ASV dimensions')
        cursor = a + 12 + n * 4; subkeys = []
        for _ in range(sub_count):
            if cursor + 12 + n*4 + n*columns > len(blocks['ASV']):
                raise ValueError('host ASV matrix extent')
            subkeys.append(struct.unpack_from('<I', blocks['ASV'], cursor)[0])
            cursor += 12 + n*4 + n*columns
            cursor = (cursor + 3) & ~3
        normal = [selected_gen(m['cells'], v['cells'], key) for key in range(256)]
        mr = next(r for r in margin['records'] if r['name'] == name)
        if n != mr['rows']:
            raise ValueError('this bounded audit requires matching ASV and MARGIN rows')
        mat_file = origin + directory['MARGIN'] + mr['data_offset']
        domains[name] = dict(n=n, asv_columns=columns, asv_body_file=hex(origin + directory['ASV'] + a),
            asv_subkeys=subkeys, GEN_M=m, GEN_V=v,
            F132=0 if m['columns'] <= 6 else 'unknown in this audit',
            enabled_byte_keys=[k for k, s in enumerate(normal) if s['enabled']],
            F152_for_byte_key={str(k): s['F152'] for k, s in enumerate(normal)},
            MIF_optional_key0_compaction=selected_gen(m['cells'], v['cells'], 0, True) if name == 'MIF' else None,
            positions=position_survey(n, mr['columns'], mat_file, data, origin + ect['header_total']))
    word = lambda p: struct.unpack_from('<I', data, p)[0]
    return dict(mode='independent_ASV_GEN_MARGIN_audit_hzc2', sboot_sha256=IMAGES['sboot'][1],
        GEN=dict(header_bytes=8, directory_version=gv, count=len(gen), callback='0x1c19c',
                 pointer_store='0x1c2a4', pointer='body+8, not body+12'),
        ASV=dict(directory_version=av, count=len(asv), callback='0x1b6c0', record_stride=40),
        domains=domains,
        w19=dict(MIF='u32(G[23]+sext4(G[37]&15))', INTSCI='u32(G[24]+sext4(G[37]>>4))',
            signed_range_if_selected_initializer_bytes_preserved=[-8, 22], runtime_value_known=False,
            calls=[dict(pc=hex(pc), X0='0xffffffffffffff9b', X1=hex(request_tag(word(a), word(b))),
                   result='X2 returned in X0, unknown') for pc, a, b in (
                       (0x19d8c, 0x19d10, 0x19d14), (0x19ddc, 0x19dcc, 0x19dd4), (0x19e2c, 0x19e18, 0x19e20))]),
        ect_extent=dict(header_field_end=hex(origin + ect['header_total']),
            parser_reservation_total_plus4_end=hex(origin + ect['header_total'] + 4), copied_source_end='0x7d000'),
        corrections=['GEN cells start after two u32 fields, not three; enabled branch not excluded',
            'F152 uses GEN column1 (ASV subkey), not column2 (421/141)',
            'MOVK replaces low16 in the selected MOVN X1, not the high part of the literal',
            '11 adjacent candidate addresses 156..166; a fixed W19 reads 13 bytes, union may cover 156',
            'NULL ASV record can be dereferenced before n=0 would skip the correction loop'],
        conditions=['successful selected callback publication, stable handles, names, metadata, stack and payloads',
            'G initializer nibble stores reached and preserved; matching magic alone does not establish those bytes',
            'calls return normally and do not mutate selected memory through aliases',
            'GPRs holding selected addresses survive SMC/helper calls; physical clobbers not established',
            'GEN MIF optional first-row compaction is modeled separately; arbitrary other writers remain open'],
        limits=['no assertion of globally unreachable enabled path, safe NULL input, all G writers or hardware OOB',
            'nibble combinations conservatively overapproximate unknown responses; physical feasibility not shown',
            'total+4 is the parser allocation formula, not a demonstrated read-bound guard',
            'source ASV analyzer and its claimed95 tests were not among current attachments',
            'no incoming X0 or caller of slot47 established'],
        gnu=dict(version=subprocess.check_output(cmd + ['--version'], text=True).splitlines()[0],
                 words=len(lines), relative_targets=relative, selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(pc), word=f'{w:08x}', op=op, args=args)
                   for pc, (w, op, args) in sorted(lines.items())],
        firmware_executed=False, qemu_scope_extended=False, incoming_X0_of_slot47_resolved=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('sboot'); args = p.parse_args()
    try:
        report = inspect(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        p.exit(2, f'inspect_newtime_asv_gen_hzc2: {exc}\n')
    print(json.dumps(report, indent=2))
