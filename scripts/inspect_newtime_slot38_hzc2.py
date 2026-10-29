#!/usr/bin/env python3
"""Bounded static slot38 audit: leaf, selected callers and column13 mask."""
import argparse
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
from inspect_newtime_jump_tables_hzc2 import DELTA, adrp_page, case_walk, u32
from inspect_newtime_mif_bins_hzc2 import direct_callers
from inspect_newtime_record_hzc2 import plan

MASK64 = (1 << 64) - 1
CALLS = (0x247b4, 0x249d4, 0x24ad8, 0x24c28, 0x25010,
         0x25e5c, 0x260f8, 0x26834, 0x269c4)
RANGES = ((0x22370, 0x2253c), (0x2d2e4, 0x2d318), (0x2d5ac, 0x2d5b8), (0x2d6cc, 0x2d738),
          (0x2ef90, 0x2eff0), (0x2f484, 0x2f488), (0x2f90c, 0x2fa98)) + tuple(
          (pc - 32, pc + 4) for pc in CALLS)
SELECTED = {
    0x22380: ('adrp', 'x23, 0x31000'), 0x22384: ('mov', 'w24, w0'),
    0x2239c: ('mov', 'w21, w1'), 0x224f0: ('add', 'x23, x23, #0x408'),
    0x2251c: ('ldr', 'x5, [x23, #152]'), 0x22520: ('mov', 'w4, w21'),
    0x22524: ('mov', 'x3, x19'), 0x22528: ('mov', 'x2, x20'),
    0x2252c: ('mov', 'x1, x25'), 0x22530: ('mov', 'w0, w24'),
    0x22538: ('blr', 'x5'),
    0x2d2e4: ('adrp', 'x1, 0x31000'), 0x2d2e8: ('cmp', 'w0, #0x7'),
    0x2d2ec: ('ldr', 'x1, [x1, #2288]'), 0x2d2f0: ('ldr', 'w1, [x1, #68]'),
    0x2d2f4: ('ccmp', 'w1, wzr, #0x4, le'), 0x2d2f8: ('b.eq', '0x2d310'),
    0x2d2fc: ('asr', 'w1, w1, w0'), 0x2d300: ('and', 'w1, w1, #0x1'),
    0x2d304: ('cmp', 'w1, wzr'), 0x2d308: ('csinv', 'w0, w0, wzr, ne'),
    0x2d30c: ('ret', ''), 0x2d310: ('mov', 'w0, #0xffffffff'),
    0x2d314: ('ret', ''),
    0x2d5ac: ('adrp', 'x6, 0x31000'),
    0x2d6d0: ('add', 'x19, x6, #0x688'),
    0x2d70c: ('mov', 'w0, #0x3600'), 0x2d710: ('movk', 'w0, #0x207, lsl #16'),
    0x2d720: ('mov', 'x1, #0x3860'), 0x2d724: ('movk', 'x1, #0x207, lsl #16'),
    0x2d728: ('ldr', 'w1, [x1, #4]'), 0x2d72c: ('add', 'w1, w1, w0'),
    0x2d730: ('sxtw', 'x1, w1'), 0x2d734: ('str', 'x1, [x19, #616]'),
    0x2ef90: ('mov', 'x0, #0x9b0'), 0x2ef94: ('movk', 'x0, #0x1586, lsl #16'),
    0x2ef98: ('ldr', 'w0, [x0]'), 0x2ef9c: ('tbnz', 'w0, #31, 0x2efec'),
    0x2efa0: ('mov', 'x0, #0x3860'), 0x2efa4: ('movk', 'x0, #0x207, lsl #16'),
    0x2efa8: ('ldr', 'w1, [x0, #4]'), 0x2efac: ('mov', 'w0, #0x3600'),
    0x2efb0: ('movk', 'w0, #0x207, lsl #16'),
    0x2efb4: ('add', 'w0, w1, w0'), 0x2efb8: ('adrp', 'x1, 0x31000'),
    0x2efbc: ('sxtw', 'x0, w0'), 0x2efc0: ('str', 'x0, [x1, #2288]'),
    0x2f484: ('ret', ''),
    0x2f90c: ('cmp', 'w0, #0x4'), 0x2f910: ('b.hi', '0x2f940'),
    0x2f914: ('adrp', 'x5, 0x30000'), 0x2f918: ('add', 'x5, x5, #0x130'),
    0x2f91c: ('ldrb', 'w0, [x5, w0, uxtw]'), 0x2f920: ('adr', 'x5, 0x2f92c'),
    0x2f924: ('add', 'x0, x5, w0, sxtb #2'), 0x2f928: ('br', 'x0'),
    0x2fa54: ('mov', 'x0, #0x3698'), 0x2fa58: ('movk', 'x0, #0x207, lsl #16'),
    0x2fa5c: ('ldr', 'w0, [x0]'), 0x2fa60: ('tbz', 'w0, #12, 0x2f940'),
    0x2fa64: ('adrp', 'x1, 0x31000'), 0x2fa68: ('mov', 'w0, w4'),
    0x2fa6c: ('stp', 'x19, x30, [sp, #-16]!'), 0x2fa70: ('mov', 'x19, x2'),
    0x2fa74: ('ldr', 'x1, [x1, #1336]'), 0x2fa78: ('blr', 'x1'),
    0x2fa7c: ('cmn', 'w0, #0x1'), 0x2fa80: ('b.eq', '0x2fa90'),
    0x2fa84: ('ldrb', 'w0, [x19, #1]'),
    0x2fa88: ('and', 'w0, w0, #0xfffffffd'),
    0x2fa8c: ('strb', 'w0, [x19, #1]'),
    0x2fa90: ('ldp', 'x19, x30, [sp], #16'), 0x2fa94: ('ret', ''),
}


def s32(value):
    u32(value)
    return value - (1 << 32) if value & 0x80000000 else value


def pointer_from_offset(offset):
    """ADD W then SXTW, not unsigned X arithmetic."""
    u32(offset)
    return s32((0x02073600 + offset) & 0xffffffff) & MASK64


def leaf_result(index, mask):
    """Host algebra after the two loads complete; no memory guard implied."""
    u32(index); u32(mask)
    if s32(index) > 7 or mask == 0:
        return 0xffffffff
    return index if (mask >> (index & 31)) & 1 else 0xffffffff


def leaf_reads(pointer):
    if type(pointer) is not int or not 0 <= pointer <= MASK64:
        raise ValueError('expected u64 pointer')
    return [(0x0211b8f0, 8), ((pointer + 68) & MASK64, 4)]


def caller_effect(selector, gate, index, mask, byte):
    """Only the selected case0 arm, with disjoint valid host fixtures."""
    for value in (selector, gate, index, mask):
        u32(value)
    if type(byte) is not int or not 0 <= byte <= 255:
        raise ValueError('expected u8 descriptor byte')
    if selector != 0:
        return dict(in_case0=False, callback_called=False, byte_store=False, byte_after=byte)
    if not gate & 0x1000:
        return dict(in_case0=True, callback_called=False, byte_store=False, byte_after=byte)
    result = leaf_result(index, mask)
    store = result != 0xffffffff
    return dict(in_case0=True, callback_called=True, callback_W0=result,
                byte_store=store, byte_after=byte & 0xfd if store else byte)


def column13(data):
    raw = embedded(data)
    tables = {entry['key']: entry for entry in raw['parsed']['entries']}
    special = tables[0x11111111]
    if (special['columns'], special['rows']) != (17, 22):
        raise ValueError('unsupported special shape')
    groups = {}
    for row in range(22):
        key = special['cells'][row * 17 + 13]
        groups.setdefault(key, []).append(row)
    payloads = []
    for key, rows in sorted(groups.items()):
        table = tables[key]
        if table['mode'] != 1 or table['columns'] * table['rows'] <= 17:
            raise ValueError('column13 has no u32 at +68')
        start = raw['block_file'] + table['offset'] + 12
        size = table['columns'] * table['rows'] * 4
        payloads.append(dict(key=hex(key), selector_rows=rows, data_file=hex(start),
            rows=table['rows'], columns=table['columns'], bytes=size,
            mask_file=hex(start + 68), mask=hex(table['cells'][17]),
            sha256=hashlib.sha256(data[start:start + size]).hexdigest()))
    plans = []
    for row in (10, 15):
        for branch_mask in (0, 511):
            result = plan(tables, row, branch_mask)
            if result['status'] != 'complete':
                raise ValueError('selected conditional plan changed')
            step = result['steps'][12]
            plans.append(dict(row=row, supplied_gate_branches=hex(branch_mask),
                key=hex(step['key']), descriptor_offset=hex(step['descriptor_offset']),
                payload_offset=hex(step['payload_offset']),
                fixed_alias_mask_address=hex(0x02073600 + step['payload_offset'] + 68)))
    return dict(column=13, record_loop_index=12, descriptor_fixed_alias='AP0x02073860',
                payloads=payloads, selected_conditional_plans=plans,
                all_selected_masks_0x1ff=all(p['mask'] == '0x1ff' for p in payloads),
                actual_row_gate_alias_and_completion_observed=False)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    cmd = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root'),
           str(root / 'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(cmd + ['--version'], text=True).splitlines()[0]
    lines = {}
    for lo, hi in RANGES:
        lines.update(parse_lines(subprocess.check_output(cmd + ['-D', '-z', '-b', 'binary',
            '-m', 'aarch64', f'--start-address={lo}', f'--stop-address={hi}',
            str(Path(path).resolve())], text=True)))
    if set(lines) != {p for a, b in RANGES for p in range(a, b, 4)}:
        raise ValueError('GNU coverage differs')
    relative = 0
    for pc, (word, op, args) in lines.items():
        if word != struct.unpack_from('<I', data, pc)[0] or op in ('.inst', 'udf'):
            raise ValueError('GNU word/instruction differs')
        kind, target = flow(word, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, args) != target:
                raise ValueError('GNU relative target differs')
            relative += 1
    for pc, expected in SELECTED.items():
        if lines[pc][1:] != expected:
            raise ValueError(f'GNU selected operand differs at {pc:#x}')
    word = lambda p: struct.unpack_from('<I', data, p)[0]
    cell = adrp_page(word(0x2fa64), 0x2fa64) - DELTA + ((word(0x2fa74) >> 10) & 4095) * 8
    cache = adrp_page(word(0x2d2e4), 0x2d2e4) - DELTA + ((word(0x2d2ec) >> 10) & 4095) * 8
    pointer, = struct.unpack_from('<Q', data, cell)
    stub, = struct.unpack_from('<Q', data, 0x314b8)
    dispatch, = struct.unpack_from('<Q', data, 0x314a0)
    if (cell, pointer - DELTA, cache, stub - DELTA, dispatch - DELTA) != (
            0x31538, 0x2d2e4, 0x318f0, 0x2f484, 0x2f90c):
        raise ValueError('selected binding differs')
    walk = case_walk(data, [0x2d2e4], 0x2d2e4, 0x2d318)
    body = {p: lines[p] for p in range(0x2d2e4, 0x2d318, 4)}
    if walk['calls'] or any(op.startswith('st') or re.search(r'\b[wx](?:[2-9]|[12][0-9]|30)\b', args)
                            for _, op, args in body.values()):
        raise ValueError('leaf store/call/GPR contract differs')
    upstream = []
    for pc in CALLS:
        if flow(word(pc), pc) != ('bl', 0x22370) or lines[pc - 8][1:] != ('mov', 'w1, w0'):
            raise ValueError('selected direct caller differs')
        if word(pc - 4) & 0xffe0001f != 0x52800000 or lines[pc - 12][1:] != ('blr', 'x1'):
            raise ValueError('selected caller selector/indirect call differs')
        selector = (word(pc - 4) >> 5) & 65535
        load = word(pc - 20)
        if load & 0xffc0001f != 0xf9400001 or ((load >> 10) & 4095) * 8 not in (176, 1208):
            raise ValueError('selected upstream slot22 load differs')
        byte_origin = lines[pc - 16][1] == 'ldrb' and lines[pc - 16][2].startswith('w0, ')
        upstream.append(dict(call=hex(pc), selector=selector, incoming_W1='return of selected slot22',
            slot22_load_pc=hex(pc - 20), slot22_load_args=lines[pc - 20][2],
            load_condition='base register is the nominal tableA/table page and loaded slot22 preserved',
            source_pc=hex(pc - 16), source_op=lines[pc - 16][1], source_args=lines[pc - 16][2],
            if_slot22_is_initial_RET_then_u8=byte_origin,
            can_select_case0_under_preserved_carrier=selector == 0))
    if direct_callers(data, 0x22370) != [dict(pc=hex(p), kind='bl') for p in CALLS]:
        raise ValueError('selected direct-caller inventory differs')
    table = data[0x30130:0x30135]
    targets = [0x2f92c + 4 * (v if v < 128 else v - 256) for v in table]
    if targets[0] != 0x2fa54:
        raise ValueError('case0 target differs')
    column = column13(data)
    return dict(mode='static_newtime_slot38_hzc2', sboot_sha256=IMAGES['sboot'][1],
        nominal_delta=hex(DELTA),
        dispatch=dict(table='0x31408', slot=38, call='0x2fa78', cell=hex(cell),
            initial_pointer=hex(pointer), target_if_initial=hex(pointer - DELTA),
            incoming_W0='incoming W4 of 0x2f90c, via 0x2fa68',
            guard='case0 and AP0x02073698 bit12 set',
            case_targets=[hex(t) for t in targets]),
        leaf=dict(code=['0x2d2e4', '0x2d318'], words=len(body), walk=walk,
            cache_cell=hex(cache), cache_initial_u64=hex(struct.unpack_from('<Q', data, cache)[0]),
            reads=[dict(pc='0x2d2ec', address='nominal(0x318f0)', width=8),
                   dict(pc='0x2d2f0', address='P+68', width=4)],
            both_loads_precede_any_early_return=True, explicit_stores=0, calls=0,
            GPR_writes=['X0 through W0', 'X1 through W1/ADRP/LDR'], NZCV_written=True,
            result='index if signed32(index)<=7 and mask!=0 and bit(mask,index&31)==1; else 0xffffffff',
            result_X0='zero-extended W0, including sentinel 0x00000000ffffffff'),
        cache_producers=[dict(store='0x2d734', cell=hex(cache),
            chain=['0x2d720', '0x2d724', '0x2d728', '0x2d72c', '0x2d730', '0x2d734'],
            value='SXTW(u32(M32[AP0x02073864]+0x02073600))',
            conditions='0x2d568 path reached with X19=S and W0=0x02073600'),
            dict(store='0x2efc0', cell=hex(cache),
            chain=['0x2efa0', '0x2efa4', '0x2efa8', '0x2efac', '0x2efb0', '0x2efb4', '0x2efbc', '0x2efc0'],
            value='SXTW(u32(M32[AP0x02073864]+0x02073600))',
            conditions='AP0x158609b0 bit31 clear; pointer and fixed alias preserved')],
        column13=column,
        caller=dict(store='0x2fa8c', destination='incoming X2 of 0x2f90c + 1, carried in X19',
            operation='read-modify-write byte, clear bit1 iff callback W0 != 0xffffffff',
            incoming_argument_GPRs_used_by_selected_arm=['W4', 'X2'],
            X1_at_callback='function pointer, not the old caller X1',
            after_callback_X0_not_forwarded=True, no_global_alias_exclusion=True),
        carrier=dict(entry='0x22370', call='0x22538', selected_slot=19, cell='0x314a0',
            target_if_initial='0x2f90c', W0='entry W0 saved in W24',
            W4='entry W1 saved in W21',
            X1='X25 computed buffer', X2='X20 computed buffer', X3='X19 computed buffer',
            conditions='normal intermediate returns; X21/X23/X24 and frame preserved'),
        selected_upstream_callers=upstream,
        conditional_conclusions=dict(
            cases0=[c['call'] for c in upstream if c['selector'] == 0],
            cases0_all_u8_if_initial_slot22=all(c['if_slot22_is_initial_RET_then_u8']
                for c in upstream if c['selector'] == 0),
            initial_slot22=dict(cell='0x314b8', target='0x2f484', body='RET; X0 unchanged'),
            mask_0x1ff_and_index_u8_accepted=[i for i in range(256) if leaf_result(i, 0x1ff) != 0xffffffff],
            raw_negative_example=dict(index='0xffffffe0', mask='0x1ff', result=hex(leaf_result(0xffffffe0, 0x1ff)),
                selected_u8_callers_reach_this=False)),
        inventory=dict(aligned_BL2_code=['0x16000', '0x2fd00'],
            direct_leaf_callers=direct_callers(data, 0x2d2e4),
            direct_dispatch_callers=direct_callers(data, 0x2f90c),
            does_not_cover_indirect_alias_or_other_image_callers=True),
        gnu=dict(version=version, words=len(lines), relative_targets=relative, selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(p), word=f'{w:08x}', op=op, args=args)
                   for p, (w, op, args) in sorted(lines.items())],
        conditions=['nominal stage mapping, initial slots19/22/38 and selected tables preserved',
            'record callback completes, aliases fixed AP base, selected column13 payload preserved',
            'selected buffers/frame are valid and do not alias code, cells or observed loads',
            'syntactic paths do not prove gate values, reaching calls or normal returns'],
        limits=['cache starts NULL in file; runtime P and mask not measured',
            'no claim these are all cache writers or all indirect callers',
            'explicit leaf has no stores/calls; caller byte destination has no proven disjointness',
            'pointer may address MMIO; lack of explicit stores is not proof reads have no physical effects',
            'no slot47 dispatch or incoming X0 established'],
        firmware_executed=False, qemu_scope_extended=False, incoming_X0_of_slot47_resolved=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        report = inspect(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'inspect_newtime_slot38_hzc2: {exc}\n')
    print(json.dumps(report, indent=2))
