#!/usr/bin/env python3
"""Hash-bound static audit of BL@1adcc and the 53-word leaf at 1a668."""
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
from inspect_newtime_jump_tables_hzc2 import (
    DELTA, adr_target, adrp_add_base, adrp_page, case_walk, cmp_w0_limit, entries, u32,
)

THRESHOLDS = (3172, 2730, 2535, 2288, 2028, 1716, 1539, 1352, 1014,
              845, 676, 546, 421, 0, 0)
RANGES = ((0x1a664, 0x1a740), (0x1abe8, 0x1ad20), (0x1ad60, 0x1add4),
          (0x1aff0, 0x1b010), (0x1b038, 0x1b03c), (0x1b37c, 0x1b3a4),
          (0x1c55c, 0x1c5b4))
SELECTED = {
    0x1a668: ('sub', 'sp, sp, #0x40'),
    0x1a6c8: ('str', 'xzr, [sp, #48]'),
    0x1a6d4: ('str', 'w2, [sp, #48]'),
    0x1a6dc: ('str', 'wzr, [sp, #56]'),
    0x1a6e0: ('str', 'w1, [x2, #2672]'),
    0x1a6e8: ('ldr', 'w3, [sp, x2, lsl #2]'),
    0x1a6ec: ('cmp', 'w3, w0'), 0x1a6f0: ('b.hi', '0x1a700'),
    0x1a6f8: ('str', 'w2, [x0, #2680]'),
    0x1a704: ('cmp', 'x2, #0xf'),
    0x1a710: ('ldr', 'w2, [sp, x0, lsl #2]'),
    0x1a714: ('cmp', 'w1, w2'), 0x1a718: ('b.cc', '0x1a728'),
    0x1a720: ('str', 'w0, [x1, #2676]'),
    0x1a734: ('add', 'sp, sp, #0x40'), 0x1a738: ('ret', ''),
    0x1abf4: ('ldr', 'x22, [x27, #24]'),
    0x1ac90: ('ldr', 'x22, [x27, #24]'),
    0x1accc: ('add', 'x22, x3, x0'),
    0x1acc0: ('ldr', 'w2, [x29, #128]'),
    0x1ad68: ('bl', '0x1c55c'), 0x1ad6c: ('cbz', 'x0, 0x1ad7c'),
    0x1ad74: ('bl', '0x1c700'),
    0x1ad84: ('cmp', 'w0, #0x13'),
    0x1adc8: ('ldp', 'w1, w0, [x22, #12]'),
    0x1adcc: ('bl', '0x1a668'), 0x1add0: ('b', '0x1aff0'),
    0x1b00c: ('ldr', 'w0, [x24, #12]'),
    0x1b038: ('mov', 'x0, #0x0'),
    0x1b388: ('ldrb', 'w2, [x1, x3]'),
    0x1b38c: ('sub', 'w2, w4, w2'),
    0x1b390: ('sxtb', 'w0, w2'),
    0x1c58c: ('bl', '0x1b37c'),
    0x1c5a0: ('ldr', 'x0, [x7, #24]'),
}


def bin_index(value):
    u32(value)
    return next(i for i, threshold in enumerate(THRESHOLDS) if threshold <= value)


def leaf_contract(w0, w1):
    """Algebraic host model, assuming valid private stack and nominal globals."""
    i, j = bin_index(w0), bin_index(w1)
    return dict(raw_W1=w1, bin_W0=i, bin_W1=j, X0=j, X1=0x0211b000,
                X2=THRESHOLDS[j], X3=THRESHOLDS[i])


def stack_table(data):
    """Only the closed MOVZ-W2/STR-SP initializer; no generic register engine."""
    table, current = {}, None
    for pc in range(0x1a66c, 0x1a6e0, 4):
        word, = struct.unpack_from('<I', data, pc)
        if word & 0xffe0001f == 0x52800002:
            current = (word >> 5) & 65535
        elif word & 0xffc003ff == 0xb90003e2:
            if current is None:
                raise ValueError('stack initializer W2 is unknown')
            table[(word >> 10) & 4095] = current
        elif word == 0xf9001bff:
            table.update({12: 0, 13: 0})
        elif word == 0xb9003bff:
            table[14] = 0
    if set(table) != set(range(15)):
        raise ValueError('stack initializer coverage differs')
    return tuple(table[k] for k in range(15))


def direct_callers(data, target):
    """Only aligned B/BL in the declared BL2 code range; not all callers."""
    hits = []
    for pc in range(0x16000, 0x2fd00, 4):
        word, = struct.unpack_from('<I', data, pc)
        kind, destination = flow(word, pc)
        if kind in ('b', 'bl') and destination == target:
            hits.append(dict(pc=hex(pc), kind=kind))
    return hits


def return_overwrite_frontier(lines):
    """Check every syntactic path before X0's first overwrite, not file order."""
    pending, seen, ends = [0x1aff0], set(), set()
    stops = {0x1b00c: ('ldr', 'w0, [x24, #12]'), 0x1b038: ('mov', 'x0, #0x0')}
    while pending:
        pc = pending.pop()
        if pc in seen:
            continue
        seen.add(pc)
        if pc not in lines:
            raise ValueError('return liveness escaped selected witnesses')
        word, op, args = lines[pc]
        if pc in stops:
            if (op, args) != stops[pc]:
                raise ValueError('return overwrite differs')
            ends.add(pc)
            continue
        if re.search(r'\b[wx]0\b', args):
            raise ValueError('unaccounted X0 read/write before overwrite')
        kind, target = flow(word, pc)
        if kind == 'linear':
            pending.append(pc + 4)
        elif kind == 'b':
            pending.append(target)
        elif kind == 'conditional':
            pending.extend((target, pc + 4))
        else:
            raise ValueError('unaccounted call/exit before return overwrite')
    return dict(visited=[hex(p) for p in sorted(seen)],
                overwrites=[hex(p) for p in sorted(ends)], conditions_tested=False)


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
    relatives = 0
    for pc, (word, op, args) in lines.items():
        if word != struct.unpack_from('<I', data, pc)[0] or op in ('.inst', 'udf'):
            raise ValueError('GNU word/instruction differs')
        kind, target = flow(word, pc)
        if kind in ('b', 'bl', 'conditional'):
            if target != direct_target(op, args):
                raise ValueError('GNU relative target differs')
            relatives += 1
    for pc, want in SELECTED.items():
        if lines[pc][1:] != want:
            raise ValueError(f'GNU selected operand differs at {pc:#x}')
    table = stack_table(data)
    if table != THRESHOLDS:
        raise ValueError('threshold table differs')
    walk = case_walk(data, [0x1a668], 0x1a668, 0x1a73c)
    if len(walk['visited']) != 53 or walk['calls'] or walk['exits'] != [dict(pc='0x1a738', reason='ret')]:
        raise ValueError('leaf control differs')
    if any(re.search(r'\b[wx](?:[4-9]|[12][0-9]|30)\b', lines[p][2])
           for p in range(0x1a668, 0x1a73c, 4)):
        raise ValueError('leaf references an assumed preserved GPR')
    global_writes = []
    for pc, page_pc, displacement in ((0x1a6e0, 0x1a6d8, 2672),
                                       (0x1a6f8, 0x1a6f4, 2680),
                                       (0x1a720, 0x1a71c, 2676)):
        cell = adrp_page(lines[page_pc][0], page_pc) + displacement - DELTA
        global_writes.append(dict(pc=hex(pc), cell_file=hex(cell), width=4,
            initial_file_value=hex(struct.unpack_from('<I', data, cell)[0])))
    limit = cmp_w0_limit(lines[0x1ad84][0])
    array = adrp_add_base(lines[0x1ad8c][0], lines[0x1ad94][0], 0x1ad8c)
    anchor = adr_target(lines[0x1ad9c][0], 0x1ad9c)
    targets = entries(data[array:array + 2*(limit + 1)], 16, anchor, anchor, 0x1aff0)
    name_file = adrp_add_base(lines[0x1ad60][0], lines[0x1ad64][0], 0x1ad60)
    name = data[name_file:data.index(0, name_file)].decode('ascii')
    if name != 'MARGIN':
        raise ValueError('last lookup name differs')
    return dict(mode='static_newtime_mif_bins_hzc2', sboot_sha256=IMAGES['sboot'][1],
        mapping=dict(nominal_delta=hex(DELTA), derived_from_ADR=False,
            reason='PC-relative ADR encodes +12 only; absolute mapping is an external premise'),
        call=dict(pc='0x1adcc', callee='0x1a668', switch_unsigned_max=limit,
            indices_selecting_case0=[e['index'] for e in targets if e['target'] == 0x1ada8],
            scope='selected initial switch, stable frame and no alternate entry assumed',
            X0='zero-extended M32[X22+16]', X1='zero-extended M32[X22+12]',
            X2_through_X7='not established as original arguments; volatile across intervening calls',
            X22='dynamic selected row, inherited/base on some empty paths; no concrete address established'),
        direct_B_BL_scan=dict(code=['0x16000', '0x2fd00'],
            to_leaf=direct_callers(data, 0x1a668), to_caller=direct_callers(data, 0x1aab4),
            indirect_callers_or_alternate_entries_excluded=False),
        leaf=dict(code=['0x1a668', '0x1a73c'], local_walk=walk,
            thresholds=list(table), unread_stack_index=15, first_zero_index=13,
            bin='first k with unsigned input >= table[k]; k<=13 under stable private stack',
            global_writes=global_writes,
            effects={'0x31a70': 'incoming W1', '0x31a74': 'bin(incoming W1)',
                     '0x31a78': 'bin(incoming W0)'},
            GP_exit={'X0': 'bin(incoming W1)', 'X1': '0x0211b000',
                     'X2': 'table[bin(incoming W1)]', 'X3': 'table[bin(incoming W0)]',
                     'X4..X30': 'unchanged by selected body', 'SP': 'restored'},
            stack_aliasing_excluded=False),
        return_liveness=return_overwrite_frontier(lines),
        volatile_counterexample=dict(condition='last lookup matches MARGIN and its runtime handle is zero',
            lookup_name=name, lookup_name_file=hex(name_file),
            lookup='BL@0x1ad68 -> 0x1c55c -> strcmp@0x1b37c',
            proof='equal strings finish with W2=0; handle load/return and selected CBZ/case0 do not redefine X2',
            X2_at_0x1adcc='0 under this condition, not a preserved GEN-argument chain',
            observed_on_device=False),
        external_audit=dict(confirmed=['53-word leaf, table/sentinels, three nominal global stores',
            'LDP-W arguments and dead X0 return along both selected continuation paths'],
            corrections=['X2 exit is a threshold, not constant 13',
                'CMP switch limit is 0x13 (19), not 0x19',
                'ADR round-trip does not establish an absolute image base',
                'direct B/BL scan and incomplete writer scan do not prove global uniqueness',
                'writer scan retains stale X2 after a W2 write; demonstrated with synthetic EOR W2',
                'some negative flags/descriptions in external JSON are hardcoded, not derived checks']),
        gnu=dict(version=version, words=len(lines), relative_targets=relatives,
                 selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(p), word=f'{w:08x}', op=op, args=args)
                   for p, (w, op, args) in sorted(lines.items())],
        limits=['nominal globals do not equal slot47 cell/binding; arbitrary stack aliases remain unexcluded',
            'no global absence of writers/readers/callers is established',
            'hardware keys, dynamic ECT contents and prior callee effects remain conditional',
            'bin models use caller-supplied values and are not observations of the device'],
        incoming_X0_of_slot47_resolved=False, firmware_executed=False, qemu_scope_extended=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(result, indent=2))
