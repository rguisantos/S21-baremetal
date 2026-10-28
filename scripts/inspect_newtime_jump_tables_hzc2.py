#!/usr/bin/env python3
"""Hash-bound enumeration of two HZC2 BL2 switches; no firmware execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow

DELTA = 0x020ea000
RANGES = ((0x1ad7c, 0x1aff0), (0x2f90c, 0x2fa98))
SPECS = (
    dict(branch=0x1ada4, cmp=0x1ad84, guard=0x1ad88,
         adrp=0x1ad8c, add=0x1ad94, load=0x1ad98, adr=0x1ad9c,
         extend=0x1ada0, bits=16, end=0x1aff0),
    dict(branch=0x2f928, cmp=0x2f90c, guard=0x2f910,
         adrp=0x2f914, add=0x2f918, load=0x2f91c, adr=0x2f920,
         extend=0x2f924, bits=8, end=0x2fa98),
)
SELECTED = {
    0x1ad7c: ('ldr', 'w0, [x29, #156]'),
    0x1ad84: ('cmp', 'w0, #0x13'), 0x1ad88: ('b.hi', '0x1aff0'),
    0x1ad8c: ('adrp', 'x0, 0x30000'),
    0x1ad90: ('ldr', 'w1, [x29, #156]'),
    0x1ad94: ('add', 'x0, x0, #0x108'),
    0x1ad98: ('ldrh', 'w0, [x0, w1, uxtw #1]'),
    0x1ad9c: ('adr', 'x1, 0x1ada8'),
    0x1ada0: ('add', 'x0, x1, w0, sxth #2'), 0x1ada4: ('br', 'x0'),
    0x2f90c: ('cmp', 'w0, #0x4'), 0x2f910: ('b.hi', '0x2f940'),
    0x2f914: ('adrp', 'x5, 0x30000'),
    0x2f918: ('add', 'x5, x5, #0x130'),
    0x2f91c: ('ldrb', 'w0, [x5, w0, uxtw]'),
    0x2f920: ('adr', 'x5, 0x2f92c'),
    0x2f924: ('add', 'x0, x5, w0, sxtb #2'), 0x2f928: ('br', 'x0'),
    0x2fa54: ('mov', 'x0, #0x3698'),
    0x2fa58: ('movk', 'x0, #0x207, lsl #16'),
    0x2fa5c: ('ldr', 'w0, [x0]'), 0x2fa60: ('tbz', 'w0, #12, 0x2f940'),
    0x2fa64: ('adrp', 'x1, 0x31000'),
    0x2fa68: ('mov', 'w0, w4'),
    0x2fa74: ('ldr', 'x1, [x1, #1336]'), 0x2fa78: ('blr', 'x1'),
}


def u32(value):
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ValueError('expected unsigned W-register value')
    return value


def sx(value, bits):
    if bits not in (8, 16, 19, 21) or type(bits) is not int:
        raise ValueError('unsupported signed width')
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError('value outside signed encoding width')
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def cmp_w0_limit(word):
    u32(word)
    if word & 0xffc003ff != 0x7100001f:
        raise ValueError('expected unshifted CMP W0, immediate')
    return (word >> 10) & 4095


def bhi_target(word, pc):
    u32(word)
    if word & 0xff00001f != 0x54000008:
        raise ValueError('expected B.HI')
    return pc + 4 * sx((word >> 5) & 0x7ffff, 19)


def adr_target(word, pc):
    u32(word)
    if word & 0x9f000000 != 0x10000000:
        raise ValueError('expected ADR, not ADRP')
    return pc + sx(((word >> 5) & 0x7ffff) << 2 | (word >> 29) & 3, 21)


def adrp_page(first, pc):
    u32(first)
    if first & 0x9f000000 != 0x90000000:
        raise ValueError('expected ADRP')
    pages = sx(((first >> 5) & 0x7ffff) << 2 | (first >> 29) & 3, 21)
    return ((pc + DELTA) & ~4095) + (pages << 12)


def adrp_add_base(first, second, pc):
    page = adrp_page(first, pc)
    u32(second)
    if second & 0xffc00000 != 0x91000000 or (second >> 5) & 31 != first & 31:
        raise ValueError('expected matching ADD X, immediate, no page shift')
    return page + ((second >> 10) & 4095) - DELTA


def entries(raw, bits, anchor, lo, hi):
    if type(bits) is not int or bits not in (8, 16):
        raise ValueError('expected byte or halfword entries')
    if any(type(v) is not int or v % 4 for v in (anchor, lo, hi)) or not 0 <= lo <= anchor < hi:
        raise ValueError('invalid aligned code bounds/anchor')
    width = bits // 8
    if not raw or len(raw) % width:
        raise ValueError('empty or truncated entry table')
    result = []
    for i in range(len(raw) // width):
        value = int.from_bytes(raw[i * width:(i + 1) * width], 'little')
        signed = sx(value, bits)
        target = anchor + 4 * signed
        if not lo <= target < hi:
            raise ValueError('jump-table target outside selected code')
        result.append(dict(index=i, raw=value, signed=signed, target=target))
    return result


def selected_target(index, targets, default):
    """Input is W0 (or its unchanged frame reload), not an arbitrary X0."""
    u32(index)
    if not targets:
        raise ValueError('empty switch')
    return targets[index] if index < len(targets) else default


def case_walk(data, roots, lo, hi, budget=4096):
    """Syntactic local edges. Calls are opaque; continuation assumes return."""
    if any(type(v) is not int or v % 4 for v in (lo, hi)) or not 0 <= lo < hi <= len(data):
        raise ValueError('invalid case window')
    if type(budget) is not int or budget < 1:
        raise ValueError('invalid static PC budget')
    pending, seen, calls, exits = list(roots), set(), {}, {}
    while pending:
        pc = pending.pop()
        if type(pc) is not int or pc % 4 or pc < 0:
            raise ValueError('unaligned/invalid control target')
        if pc in seen:
            continue
        if not lo <= pc < hi:
            exits[pc] = 'outside_case_window'
            continue
        if len(seen) >= budget:
            raise ValueError('static PC budget exceeded')
        seen.add(pc)
        word, = struct.unpack_from('<I', data, pc)
        kind, target = ('linear', None) if word == 0xd503201f else flow(word, pc)
        if kind == 'b':
            pending.append(target)
        elif kind == 'conditional':
            pending.extend((pc + 4, target))
        elif kind in ('bl', 'blr'):
            edge = {'target_file': hex(target)} if kind == 'bl' else {'register': target}
            calls[pc] = dict(kind=kind, **edge, continuation_requires_normal_return=True)
            pending.append(pc + 4)
        elif kind == 'linear':
            pending.append(pc + 4)
        elif kind in ('ret', 'br', 'system', 'exception_call', 'eret', 'udf'):
            exits[pc] = kind
        else:
            raise ValueError('unsupported local control')
    return dict(visited=[hex(p) for p in sorted(seen)],
                calls=[dict(pc=hex(p), **v) for p, v in sorted(calls.items())],
                exits=[dict(pc=hex(p), reason=v) for p, v in sorted(exits.items())],
                conditions_tested=False, callees_explored=False)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    word = lambda p: struct.unpack_from('<I', data, p)[0]
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root'),
               str(root / 'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command + ['--version'], text=True).splitlines()[0]
    lines = {}
    for a, b in RANGES:
        lines.update(parse_lines(subprocess.check_output(command + ['-D', '-z', '-b', 'binary', '-m',
            'aarch64', f'--start-address={a}', f'--stop-address={b}', str(Path(path).resolve())], text=True)))
    if set(lines) != {p for a, b in RANGES for p in range(a, b, 4)}:
        raise ValueError('GNU coverage differs')
    relative = 0
    for p, (w, op, args) in lines.items():
        if w != word(p) or op in ('.inst', 'udf'):
            raise ValueError('GNU word/instruction differs')
        kind, target = flow(w, p)
        if kind in ('b', 'bl', 'conditional'):
            if target != direct_target(op, args):
                raise ValueError('GNU branch target differs')
            relative += 1
    for p, want in SELECTED.items():
        if lines[p][1:] != want:
            raise ValueError(f'GNU operand differs at {p:#x}')
    switches = []
    for s in SPECS:
        limit = cmp_w0_limit(word(s['cmp']))
        default = bhi_target(word(s['guard']), s['guard'])
        table = adrp_add_base(word(s['adrp']), word(s['add']), s['adrp'])
        anchor = adr_target(word(s['adr']), s['adr'])
        raw = data[table:table + (limit + 1) * (s['bits'] // 8)]
        es = entries(raw, s['bits'], anchor, anchor, s['end'])
        walk = case_walk(data, [e['target'] for e in es] + [default], anchor, s['end'])
        switches.append(dict(branch=hex(s['branch']), table=hex(table), anchor=hex(anchor),
            bits=s['bits'], index_max=limit, default=hex(default), table_end=hex(table + len(raw)),
            raw_hex=raw.hex(), table_sha256=hashlib.sha256(raw).hexdigest(),
            entries=[dict(**{k: v for k, v in e.items() if k != 'target'}, target=hex(e['target'])) for e in es],
            unique_targets=[hex(p) for p in sorted({e['target'] for e in es})], local_walk=walk,
            any_entry_in_slot47_routine=any(0x2d364 <= e['target'] < 0x2d3bc for e in es)))
    callback_base = adrp_page(word(0x2fa64), 0x2fa64) - DELTA
    callback_cell = callback_base + ((word(0x2fa74) >> 10) & 4095) * 8
    pointer, = struct.unpack_from('<Q', data, callback_cell)
    if (callback_cell, pointer) != (0x31538, 0x021172e4):
        raise ValueError('initial callback slot differs')
    return dict(mode='static_newtime_jump_tables_hzc2', sboot_sha256=IMAGES['sboot'][1],
        nominal_delta=hex(DELTA), switches=switches,
        selected_callback=dict(call='0x2fa78', guard='AP0x02073698 bit12 must be set on case 0',
            table='0x31408', slot=38, cell=hex(callback_cell), initial_pointer=hex(pointer),
            target_if_initial=hex(pointer - DELTA), W0='incoming W4, via 0x2fa68',
            preservation_is_condition=True, callback_executed=False),
        gnu=dict(version=version, words=len(lines), relative_targets=relative,
            selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(p), word=f'{w:08x}', op=op, args=args)
                   for p, (w, op, args) in sorted(lines.items())],
        conditions=['nominal BL2 mapping and initial table bytes remain valid at each dispatch',
            'frame index is unchanged between 0x1ad7c and 0x1ad90; no intervening alias write',
            'local graph follows both conditional edges without solving feasibility',
            'calls are opaque; their following instructions require a normal return'],
        limits=['0x1ada8 and 0x2f92c are code anchors, not entry-array addresses',
            'no selected entry targets slot47; callees, common continuation and other callers remain open',
            'these finite candidate sets do not prove absence of a slot47 caller',
            'binding preservation, MMIO values and actual execution are not observed'],
        incoming_X0_of_slot47_resolved=False, firmware_executed=False, qemu_scope_extended=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        report = inspect(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(report, indent=2))
