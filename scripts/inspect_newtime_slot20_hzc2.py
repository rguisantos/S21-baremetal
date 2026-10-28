#!/usr/bin/env python3
"""Static slot20 callers, X5 buffer construction and bounded slot47 searches."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_consumers_hzc2 import branch_candidates
from inspect_newtime_slot47_hzc2 import load_offsets

FIRST, LAST = 0x16000, 0x2fd00
CELL = 0x31580
RANGES = (
    (0x195ac, 0x195c0), (0x19664, 0x19674), (0x22380, 0x2238c),
    (0x224f0, 0x224f4), (0x22534, 0x22570), (0x228f8, 0x228fc),
    (0x2352c, 0x23554), (0x24550, 0x24554), (0x2457c, 0x24598),
    (0x245c0, 0x245ec), (0x246f4, 0x247a0), (0x24814, 0x24a78),
    (0x24b7c, 0x24bac), (0x24cc0, 0x24d6c), (0x24f1c, 0x24f20),
    (0x254ec, 0x25574), (0x25620, 0x25688), (0x25fdc, 0x25fe0),
    (0x27248, 0x2726c), (0x27d3c, 0x27d4c), (0x28ebc, 0x28ec4),
    (0x2b498, 0x2b53c), (0x2b690, 0x2b6cc), (0x2b828, 0x2b85c),
    (0x1fcc4, 0x1fce8),
)


def check_word(word, pc):
    if type(word) is not int or not 0 <= word < 1 << 32 or type(pc) is not int or pc < 0 or pc % 4:
        raise ValueError('u32 instruction and aligned file PC required')


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def literal_x_target(word, pc):
    check_word(word, pc)
    return pc + 4 * signed((word >> 5) & 0x7ffff, 19) if word & 0xff000000 == 0x58000000 else None


def adr_target(word, pc):
    check_word(word, pc)
    form = word & 0x9f000000
    if form not in (0x10000000, 0x90000000):
        return None
    displacement = signed((((word >> 5) & 0x7ffff) << 2) | ((word >> 29) & 3), 21)
    return pc + displacement if form == 0x10000000 else (pc & ~0xfff) + (displacement << 12)


def adjacent_page_add(word, next_word, pc):
    check_word(word, pc)
    check_word(next_word, pc + 4)
    if word & 0x9f000000 != 0x90000000 or next_word & 0xff800000 != 0x91000000:
        return None
    if word & 31 == 31 or next_word & 31 == 31 or (next_word >> 5) & 31 != word & 31:
        return None
    return adr_target(word, pc) + (((next_word >> 10) & 4095) << (12 if next_word & (1 << 22) else 0))


def bias_word(counter, current, saved):
    if any(type(v) is not int or not 0 <= v < 1 << bits
           for v, bits in ((counter, 32), (current, 16), (saved, 16))):
        raise ValueError('one u32 counter and two u16 samples required')
    return (counter + current - saved) & 0xffffffff


def optional_words(values):
    if values is None:
        return (0,) * 16
    if len(values) != 16 or any(type(v) is not int or not 0 <= v < 1 << 32 for v in values):
        raise ValueError('exactly sixteen u32 words required')
    return tuple(values)


def bias_pair(values, channel, lane):
    if type(channel) is not int or channel not in range(4) or type(lane) is not int or lane not in range(2):
        raise ValueError('only selected four-channel, two-lane domain modeled')
    words = optional_words(values)
    index = 4 * channel + 2 * lane
    return words[index] & 0xffff, words[index + 1] & 0xffff


def stack_transfer(caller_sp):
    if type(caller_sp) is not int or caller_sp % 16 or not 176 <= caller_sp <= (1 << 64) - 256:
        raise ValueError('aligned nonwrapping host-model frame required')
    callee_sp = caller_sp - 176
    return dict(source=(caller_sp + 192, caller_sp + 256),
                destination=(callee_sp + 112, callee_sp + 176))


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    candidates = [p for p in range(FIRST, LAST, 4)
                  if 160 in load_offsets(struct.unpack_from('<I', data, p)[0])]
    stack = {0x195b0, 0x19664, 0x24f1c, 0x25fdc, 0x28ebc}
    other = {0x22560: 'nominal 0x31408 + 160, another table',
             0x2725c: 'nominal 0x31000 + 160, not cell 0x31088',
             0x27d40: 'received method base M64[0x31998]; alias/target unresolved'}
    specs = (
        (0x2354c, 0x23550, '0', 4, '2', '0x6', 'u8(S+736)', 'M64[S+640]'),
        (0x245cc, 0x245e8, '0', 'W21', 'W24', '0x2', 'u8(S+736)', 'M64[S+640]'),
        (0x24830, 0x24838, '0', 4, '2', '0x2000', 'W21', 'M64[S+640]'),
        (0x249f0, 0x24a00, 'SP+0xc0', 'W28, 0..3 on selected loop', '0', '0x2000', 'W21', 'M64[S+640]'),
        (0x24a3c, 0x24a44, 'SP+0xc0', 'W28, 0..3 on selected loop', '1', '0x2000', 'W21', 'M64[S+640]'),
        (0x24cd4, 0x24cec, '0', 4, '2', '0x1000', 'W19', 'M64[S+640]'),
        (0x24cd4, 0x24d68, '0', 4, '2', '0x4', 'W19', 'M64[S+640]'),
        (0x25560, 0x25570, '0', 'entry(0x254ec).W0', 'entry.W1', '0x2', 'u8(0x31968)', 'SP+0x70'),
        (0x25674, 0x25684, '0', 'entry(0x254ec).W0', 'entry.W1', '0x4', 'u8(0x31968)', 'SP+0x70'),
    )
    if set(candidates) != stack | set(other) | {p[0] for p in specs} or len(candidates) != 16:
        raise ValueError('candidate classification differs from full bounded scan')
    extra_offsets = {off: [p for p in range(FIRST, LAST, 4)
                           if off in load_offsets(struct.unpack_from('<I', data, p)[0])]
                     for off in (376, 1408, 5504)}
    literal, adr, pairs = [], [], []
    for p in range(FIRST, LAST, 4):
        w = struct.unpack_from('<I', data, p)[0]
        if literal_x_target(w, p) == CELL:
            literal.append(p)
        if w & 0x9f000000 == 0x10000000 and adr_target(w, p) == CELL:
            adr.append(p)
        if p + 8 <= LAST:
            target = adjacent_page_add(w, struct.unpack_from('<I', data, p + 4)[0], p)
            if target in (CELL, 0x31408):
                pairs.append(dict(pc=hex(p), target=hex(target)))
    direct = branch_candidates(data, 0x2b498, last=0xec000)
    pcs = {p for a, b in RANGES for p in range(a, b, 4)} | set(candidates) | set(literal) | set(adr)
    pcs |= {p for values in extra_offsets.values() for p in values}
    pcs |= {int(pair['pc'], 16) + d for pair in pairs for d in (0, 4)}
    pcs |= {int(c['pc'], 16) for c in direct}
    runs = []
    for p in sorted(pcs):
        if runs and runs[-1][1] == p:
            runs[-1][1] = p + 4
        else:
            runs.append([p, p + 4])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root'),
               str(root / 'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command + ['--version'], text=True).splitlines()[0]
    lines = {}
    for a, b in runs:
        lines.update(parse_lines(subprocess.check_output(command + ['-D', '-b', 'binary', '-m', 'aarch64',
            f'--start-address={a}', f'--stop-address={b}', str(Path(path).resolve())], text=True)))
    if set(lines) != pcs:
        raise ValueError('GNU coverage differs')
    relative = 0
    for p, (word, op, args) in lines.items():
        if word != struct.unpack_from('<I', data, p)[0] or op in ('.inst', 'udf'):
            raise ValueError('GNU instruction differs')
        kind, target = flow(word, p)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, args) != target:
                raise ValueError('GNU target differs')
            relative += 1
        elif direct_target(op, args) is not None:
            raise ValueError('unclassified GNU relative branch')
    selected = {
        0x228f8: ('adrp', 'x22, 0x30000'), 0x23530: ('add', 'x23, x22, #0xfe8'),
        0x24550: ('adrp', 'x28, 0x30000'), 0x2457c: ('add', 'x25, x28, #0xfe8'),
        0x24760: ('adrp', 'x20, 0x30000'), 0x24b7c: ('adrp', 'x20, 0x30000'),
        0x25534: ('adrp', 'x25, 0x30000'), 0x25640: ('adrp', 'x23, 0x30000'),
        0x246f4: ('sub', 'sp, sp, #0x320'), 0x24700: ('stp', 'x19, x20, [sp, #-96]!'),
        0x2486c: ('add', 'x0, sp, #0xc0'), 0x24870: ('bl', '0x1f9e8'),
        0x2487c: ('add', 'x7, sp, #0xc4'), 0x248c8: ('ldr', 'w9, [x0, #1664]'),
        0x248fc: ('add', 'x0, x0, #0x50'), 0x24924: ('ldrh', 'w3, [x0]'),
        0x2492c: ('ldurh', 'w4, [x2, #-80]'), 0x24934: ('ldurh', 'w12, [x2, #-78]'),
        0x2493c: ('sub', 'w4, w3, w4'), 0x24944: ('stur', 'w4, [x10, #-4]'),
        0x24948: ('add', 'w4, w9, w4'), 0x24950: ('stur', 'w4, [x8, #-4]'),
        0x24958: ('add', 'w3, w9, w3'), 0x2495c: ('str', 'w3, [x8], #8'),
        0x249e0: ('add', 'x5, sp, #0xc0'), 0x24a28: ('add', 'x5, sp, #0xc0'),
        0x2b498: ('stp', 'x19, x20, [sp, #-176]!'),
        0x2b4bc: ('stp', 'xzr, xzr, [sp, #112]'), 0x2b4c8: ('stp', 'xzr, xzr, [sp, #160]'),
        0x2b4f4: ('cbz', 'x5, 0x2b508'), 0x2b4f8: ('mov', 'w2, #0x40'),
        0x2b500: ('add', 'x0, sp, #0x70'), 0x2b504: ('bl', '0x1fcc4'),
        0x2b528: ('sxtw', 'x9, w22'),
        0x2b690: ('tbz', 'w23, #13, 0x2b77c'), 0x2b6a4: ('lsl', 'x9, x9, #1'),
        0x2b830: ('add', 'x0, x9, w2, uxtw'), 0x2b834: ('add', 'x1, sp, #0xb0'),
        0x2b83c: ('add', 'x0, x1, x0, lsl #3'),
        0x2b848: ('ldurh', 'w12, [x0, #-64]'), 0x2b84c: ('ldurh', 'w11, [x0, #-60]'),
    }
    for p, expected in selected.items():
        if lines[p][1:] != expected:
            raise ValueError(f'operand differs at {p:#x}')
    for load, call, x5, *_ in specs:
        if lines[load][1] != 'ldr' or lines[call][1] != 'blr':
            raise ValueError('call witness differs')
        setup = {0x23550: 0x23534, 0x245e8: 0x245d4, 0x24838: 0x2481c,
                 0x24a00: 0x249e0, 0x24a44: 0x24a28, 0x24cec: 0x24ccc,
                 0x24d68: 0x24ccc, 0x25570: 0x25558, 0x25684: 0x2566c}[call]
        if lines[setup][1:] != (('mov', 'x5, #0x0') if x5 == '0' else ('add', 'x5, sp, #0xc0')):
            raise ValueError('X5 setup differs')
    pointer = struct.unpack_from('<Q', data, 0x31088)[0]
    if pointer != 0x02115498:
        raise ValueError('initial slot20 pointer differs')
    packed = b''.join(struct.pack('<II', p, lines[p][0]) for p in sorted(pcs))
    return dict(mode='static_newtime_slot20_callers', sboot_sha256=IMAGES['sboot'][1],
        slot=dict(table='0x30fe8', index=20, cell='0x31088', initial_pointer=hex(pointer), target_file='0x2b498'),
        candidate_scan=dict(first=hex(FIRST), end_exclusive=hex(LAST), words=(LAST-FIRST)//4,
            encodings='LDR X unsigned immediate; LDP X signed immediate without writeback',
            displacement=160, sites=[dict(pc=hex(p), group='stack_data' if p in stack else
                'different_or_unresolved_base' if p in other else 'selected_slot20_load',
                note=other.get(p)) for p in candidates]),
        selected_calls=[dict(load=hex(load), call=hex(call), X0=x0, W1=w1, W2=w2, W3=w3, X4=x4, X5=x5,
                             nominal_target_if_binding_preserved='0x2b498')
                        for load, call, x5, x0, w1, w2, w3, x4 in specs],
        selected_X5_counts=dict(Counter(x5 for _, _, x5, *_ in specs)),
        direct_entry_references=direct,
        buffer_construction=dict(entry='0x246f4', frame_bytes=896, pointer='caller SP+0xc0', bytes=64,
            shape='sixteen u32: four channels times two lanes times two words',
            word_formula='u32(counter[i] + current_u16[i,j,k] - saved_u16[i,j,k])',
            counter='M32[base_from_0x30fc0[i]+1664], PC 0x248c8',
            current='M16[channel_pointer[i]+0x50+0x50*j+2*k]',
            saved='M16[caller SP+0x128+0xa0*i+0x50*j+2*k]',
            output='caller SP+0xc0+16*i+8*j+4*k',
            domain='i=0..3, j=0..1, k=0..1 on selected construction loops',
            intervening_calls_and_memory_preservation_are_conditions=True, sample_values_observed=False),
        callee_snapshot=dict(frame_bytes=176, destination='callee SP+0x70 .. +0xb0',
            cleared_before_optional_copy=True, copy_bytes=64, skip_if_X5_zero=True,
            selected_bit13_reads='low16(words[4*channel+2*lane]), low16(words[4*channel+2*lane+1])',
            PCs=['0x2b690', '0x2b830', '0x2b848', '0x2b84c'],
            physical_meaning_or_units_resolved=False),
        slot47_additional_scan=dict(
            accepted_encodings='same LDR/LDP forms; LDR X literal; ADR; adjacent ADRP + ADD X immediate with matching base',
            first=hex(FIRST), end_exclusive=hex(LAST), cell_file=hex(CELL),
            load_displacements={str(off): [hex(p) for p in sites] for off, sites in extra_offsets.items()},
            literal_X_loads_to_cell=[hex(p) for p in literal], ADR_to_cell=[hex(p) for p in adr],
            adjacent_page_add_to_cell_or_table=pairs,
            prior_376_candidates_remain_another_table_under_their_selected_bases=True,
            complete_alias_or_caller_exclusion=False),
        gnu=dict(version=version, words=len(lines), relative_targets=relative, selected_operands=len(selected),
                 instruction_index_sha256=hashlib.sha256(packed).hexdigest()),
        ranges=[dict(first=hex(a), end_exclusive=hex(b), sha256=hashlib.sha256(data[a:b]).hexdigest()) for a,b in RANGES],
        witnesses=[dict(pc=hex(p), word=f'{w:08x}', op=op, args=args) for p,(w,op,args) in sorted(lines.items())],
        limits=['manual selected-path argument deductions, not whole-program reachability',
                'table/register/memory preservation and normal entry/returns remain conditions',
                'SP-relative origin does not establish physical stack location or absence of all aliases',
                'static channel/counter reads are not sample values, units or observed hardware behavior',
                'additional slot47 search covers only the stated encodings and region',
                'other indirect/internal callers and the received method-base candidate remain unresolved'],
        selected_X5_origins_resolved=True, all_callers_resolved=False, incoming_slot47_X0_resolved=False,
        transport_of_cell_found=False, firmware_executed=False, qemu_scope_extended=False, physical_device_tested=False)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try: result=inspect(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc: parser.exit(2,f'{exc}\n')
    print(json.dumps(result,indent=2))
