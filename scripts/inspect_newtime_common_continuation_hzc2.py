#!/usr/bin/env python3
"""Bounded static evidence for NEWTIME 0x1aff0; never executes firmware."""
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
from inspect_newtime_jump_tables_hzc2 import DELTA, adrp_page, case_walk, u32

MASK32 = 0xffffffff
MASK64 = 0xffffffffffffffff
RANGES = ((0x18068, 0x1809c), (0x1a26c, 0x1a5b0), (0x1aab4, 0x1b37c))
SELECTORS = (0x1adb4, 0x1ade0, 0x1ae18, 0x1ae34, 0x1ae70, 0x1aeb4,
             0x1aed8, 0x1aefc, 0x1af34, 0x1af58, 0x1af90, 0x1afc8)
SELECTED = {
    0x1ab04: ('stp', 'x5, x4, [x29, #104]'),
    0x1ab94: ('bl', '0x1c690'), 0x1ab98: ('mov', 'x28, x0'),
    0x1aba0: ('ldr', 'w23, [x0, #16]'),
    0x1abb0: ('lsl', 'w0, w23, #2'), 0x1abb4: ('bl', '0x18068'),
    0x1abb8: ('mov', 'x25, x0'),
    0x1a26c: ('lsr', 'w2, w1, #1'),
    0x1a270: ('ubfiz', 'w1, w1, #4, #1'),
    0x1a274: ('add', 'w0, w2, w0, lsl #1'),
    0x1a278: ('adrp', 'x2, 0x31000'),
    0x1a27c: ('add', 'x2, x2, #0xaa8'),
    0x1a280: ('add', 'x2, x2, w0, uxtw #2'),
    0x1a284: ('ldr', 'w0, [x2, #108]'),
    0x1a288: ('lsr', 'w0, w0, w1'), 0x1a28c: ('uxth', 'w0, w0'),
    0x1a290: ('ret', ''),
    0x1b040: ('mov', 'x5, #0x30'),
    0x1b070: ('b.gt', '0x1b04c'), 0x1b074: ('ldr', 'w0, [x2]'),
    0x1b0c4: ('madd', 'w4, w1, w4, w19'),
    0x1b0d0: ('sturb', 'w4, [x3, #-1]'),
    0x1b0d8: ('mov', 'x0, #0x0'),
    0x1b110: ('strb', 'w4, [x5, #3]'),
    0x1b114: ('b.eq', '0x1b138'),
    0x1b11c: ('add', 'x2, x0, x2'),
    0x1b134: ('strb', 'w3, [x2, #3]'),
    0x1b178: ('strb', 'w0, [x1]'),
    0x1b18c: ('mul', 'w1, w1, w4'),
    0x1b190: ('and', 'w1, w1, #0xfffff8'),
    0x1b194: ('bfxil', 'w3, w1, #0, #24'),
    0x1b198: ('str', 'w3, [x25, x2]'),
    0x1b208: ('add', 'x21, x20, w21, uxtw #2'),
    0x1b210: ('ldr', 'w0, [x21, #44]'),
    0x1b270: ('add', 'x1, x29, #0xd0'),
    0x1b274: ('add', 'x0, x29, #0xc0'),
    0x1b2dc: ('ldr', 'w2, [x0, x13, lsl #2]'),
    0x1b2e8: ('ldr', 'w1, [x18]'),
    0x1b308: ('sub', 'w2, w21, w1'),
    0x1b30c: ('cmp', 'w1, #0xa1'),
    0x1b310: ('csel', 'w1, w2, w1, cs'),
    0x1b318: ('strb', 'w1, [x14, #3]'),
    0x1b320: ('strb', 'w0, [x14, #3]'),
    0x1b334: ('mov', 'x0, #0x0'),
    0x1b33c: ('ldp', 'w4, w0, [x29, #152]'),
    0x1b340: ('mov', 'x6, x25'),
    0x1b344: ('mov', 'w5, w19'),
    0x1b348: ('mov', 'x3, x28'),
    0x1b34c: ('add', 'x2, x29, #0xd0'),
    0x1b350: ('add', 'x1, x29, #0xc0'),
    0x1b35c: ('mov', 'x0, x25'), 0x1b378: ('ret', ''),
}


def signed32(value):
    u32(value)
    return value - (1 << 32) if value & (1 << 31) else value


def allocation_request(count):
    """W23 -> LSL W0,#2 -> allocator SXTW; no allocation is simulated."""
    u32(count)
    request = (count * 4) & MASK32
    return dict(request_W=request, signed_request=signed32(request),
                equals_nonnegative_logical_size=signed32(request) == count * 4)


def packed_field(selector, part, word):
    """1a26c with caller-supplied memory word, including W arithmetic wrap."""
    for value in (selector, part, word):
        u32(value)
    index = ((part >> 1) + ((selector << 1) & MASK32)) & MASK32
    shift = (part & 1) * 16
    return dict(word_index=index, word_file=0x31aa8 + 108 + 4 * index,
                nominal_address=DELTA + 0x31aa8 + 108 + 4 * index,
                shift=shift, result=(word >> shift) & 0xffff)


def choose_record(keys, wanted, count):
    """Fallback loop, under stable caller-supplied keys; not a memory reader."""
    u32(wanted)
    n = signed32(count)
    if n <= 0:
        return dict(index=None, first_key_read_address=0,
                    reason='signed count skips loop; X2 remains zero at 0x1b074')
    if len(keys) != n:
        raise ValueError('host fixture must supply exactly the positive record count')
    for key in keys:
        u32(key)
    found = next((i for i, key in enumerate(keys) if key == wanted), None)
    return dict(index=0 if found is None else found, first_key_read_address=None,
                reason='fallback to first record' if found is None else 'first matching key')


def corrected_byte(result_W, code):
    u32(result_W)
    if type(code) is not int or not 0 <= code <= 255:
        raise ValueError('expected byte code')
    delta = 160 - code if code >= 161 else code
    return (result_W + delta) & 255


def pack_level(previous_W, level_W):
    u32(previous_W)
    u32(level_W)
    return (previous_W & 0xff000000) | (((level_W * 1000) & MASK32) & 0x00fffff8)


def secondary_address(base, index, tag):
    if type(base) is not int or not 0 <= base <= MASK64:
        raise ValueError('expected unsigned X-register base')
    u32(index)
    u32(tag)
    return None if tag == 255 else (base + 4 * index + 3) & MASK64


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root'),
               str(root / 'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command + ['--version'], text=True).splitlines()[0]
    lines = {}
    for a, b in RANGES:
        lines.update(parse_lines(subprocess.check_output(command + ['-D', '-z', '-b', 'binary',
            '-m', 'aarch64', f'--start-address={a}', f'--stop-address={b}',
            str(Path(path).resolve())], text=True)))
    if set(lines) != {p for a, b in RANGES for p in range(a, b, 4)}:
        raise ValueError('GNU coverage differs')
    relative = 0
    for pc, (word, op, args) in lines.items():
        if word != struct.unpack_from('<I', data, pc)[0] or op in ('.inst', 'udf'):
            raise ValueError(f'GNU instruction differs at {pc:#x}')
        kind, target = flow(word, pc)
        if kind in ('b', 'bl', 'conditional'):
            if target != direct_target(op, args):
                raise ValueError(f'GNU relative target differs at {pc:#x}')
            relative += 1
    for pc, wanted in SELECTED.items():
        if lines[pc][1:] != wanted:
            raise ValueError(f'GNU selected operands differ at {pc:#x}')
    walk = case_walk(data, [0x1aff0], 0x1aff0, 0x1b37c)
    expected_calls = {0x1b1b0: 0x1a26c, 0x1b1c4: 0x1a26c,
                      0x1b1d4: 0x1a26c, 0x1b1e4: 0x1a26c,
                      0x1b278: 0x1a294, 0x1b2e4: 0x1a294, 0x1b354: 0x1a804}
    if {int(c['pc'], 16): int(c['target_file'], 16) for c in walk['calls']} != expected_calls:
        raise ValueError('continuation calls differ')
    if walk['exits'] != [dict(pc='0x1b378', reason='ret')]:
        raise ValueError('continuation frontier differs')
    selectors = []
    for pc in SELECTORS:
        _, op, args = lines[pc]
        if op != 'mov' or not args.startswith('w21, #'):
            raise ValueError('selected W21 definition differs')
        selectors.append(dict(pc=hex(pc), value=int(args.split('#')[1], 0)))
    # Exact callee body, not AAPCS guesses about caller-saved registers.
    numeric_body = {p: v for p, v in lines.items() if 0x1a294 <= p < 0x1a5b0}
    if any(re.search(r'\b[wx](13|14|15|18|25)\b', v[2]) for v in numeric_body.values()):
        raise ValueError('numeric helper references a preserved selected register')
    if any(v[1] in ('bl', 'blr', 'br') for v in numeric_body.values()):
        raise ValueError('numeric helper has an unaccounted call/branch')
    numeric_walk = case_walk(data, [0x1a294], 0x1a294, 0x1a5b0)
    if (len(numeric_walk['visited']) != len(numeric_body) or numeric_walk['calls'] or
            numeric_walk['exits'] != [dict(pc='0x1a5ac', reason='ret')]):
        raise ValueError('numeric helper local control differs')
    base = adrp_page(lines[0x1a278][0], 0x1a278) - DELTA + 0xaa8
    return dict(mode='static_newtime_common_continuation_hzc2',
        sboot_sha256=IMAGES['sboot'][1], nominal_delta=hex(DELTA),
        local_walk=walk, symbols=dict(F='X29/SP after 224-byte prologue',
            B='X25 = return of allocator BL@0x1abb4', D='X28 = lookup result BL@0x1ab94, or zero',
            E='X26 = lookup result BL@0x1ab7c, or zero', C='X24 = lookup result BL@0x1ab58, or zero',
            n='W23 = M32[D+16], or zero', G=hex(base)),
        allocation=dict(call='0x1abb4', count='u32(4*n), then SXTW in 0x18078',
            cursor_cell='0x31a50', limit_cell='0x31a58',
            return_value='old cursor; new cursor written before unsigned limit test',
            overflow='u32(4*n) may wrap or become negative under SXTW',
            bounds_or_disjointness_demonstrated=False),
        packed_reader=dict(entry='0x1a26c', words=10, global_file=hex(base),
            index='u32((part>>1) + u32(selector<<1))',
            address='nominal(G) + 108 + 4*index', result='(M32[address] >> (16*(part&1))) & 0xffff',
            selected_parts=[0, 1, 2, 3], selected_selector_definitions=selectors,
            selected_word_file_interval=['0x31b14', '0x31b74'],
            interval_conditions='20 switch entries, stable definitions and preserved registers across callees',
            default_selector='W0>19 bypasses these W21 definitions; no bound established',
            only_modified_GPRs=['X0', 'X1', 'X2'], calls_or_stores=False),
        call_arguments=[dict(pc=hex(p), target=hex(t),
            arguments=({'W0': 'selected W21', 'W1': i} if i < 4 else
                       {'X0': 'F+192', 'X1': 'F+208', 'W2': '0', 'W3': '0'} if i == 4 else
                       {'X0': 'F+192', 'X1': 'F+208', 'W2': 'M32[M64[D+24]+4*i]', 'W3': '1'} if i == 5 else
                       {'W0': 'M32[F+156]', 'X1': 'F+192', 'X2': 'F+208', 'X3': 'D',
                        'W4': 'M32[F+152]', 'W5': 'selected W19', 'X6': 'B'}),
            guards=('C row found and M32[row+4]!=0; part 1..3 also require part0!=0' if i < 4 else
                    'enabled C path' if i == 4 else 'enabled C path and i<n' if i == 5 else
                    'enabled C path and W27!=255'),
            result=('selected 16-bit field' if i < 4 else 'not interpreted'))
            for i, (p, t) in enumerate(expected_calls.items())],
        numeric_helper=dict(code=['0x1a294', '0x1a5b0'], words=len(numeric_body),
            local_walk=numeric_walk,
            selected_GPRs_not_referenced=['X13', 'X14', 'X15', 'X18', 'X25'],
            floating_point_and_memory_effects='opaque; no numerical or memory-purity claim'),
        writes=[
            dict(pc='0x1b0d0', address='B+4*i+3', width=1, value='selected descriptor byte',
                 guard='fallback path, i<n; wrapped W32 row/column index'),
            dict(pc='0x1b318/0x1b320', address='B+4*i+3', width=1,
                 value='low8(helper_W0 + optional signed byte correction)', guard='enabled C path, i<n'),
            dict(pc='0x1b110', address='B+4*i+3', width=1,
                 value='low8(old byte + E byte)', guard='E nonzero and i<n'),
            dict(pc='0x1b134', address='Q+4*i+3', width=1,
                 value='low8(old byte + E byte)', guard='E nonzero, i<n, W27!=255; no Q-nonzero guard'),
            dict(pc='0x1b178', address='M64[F+104]', width=1,
                 value='low8(i)', guard='i<n and M32[M64[F+112]] equals level[i]'),
            dict(pc='0x1b198', address='B+4*i', width=4,
                 value='(old_W&0xff000000) | (u32(level[i]*1000)&0x00fffff8)', guard='i<n')],
        secondary_Q=dict(fallback='0 at 0x1b0d8', enabled_tag255='0 at 0x1b334',
            enabled_other_tag='opaque X0 returned by BL@0x1b354 to 0x1a804',
            zero_base_store='syntactic fallback/non255/E/nonempty path yields addresses 4*i+3; feasibility and mapping unknown'),
        record_search=dict(stride=48, count='signed32(M32[D+20])',
            fallback='first matching key; otherwise first record',
            empty='X2=0 at 0x1b074 when signed count<=0; address-zero read precedes fallback',
            enabled_path='X18=0 when signed count<=0; loop 0x1b2e8 may read zero if n>0',
            no_hardware_fault_claim=True),
        return_value=dict(pc='0x1b35c', X0='B, before restoring caller X25'),
        gnu=dict(version=version, words=len(lines), relative_targets=relative,
                 selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(p), word=f'{w:08x}', op=op, args=args)
                   for p, (w, op, args) in sorted(lines.items())],
        conditions=['syntactic CFG follows both conditional edges, without proving feasibility',
            'BL following edges require normal return; unwatched callees remain opaque',
            'frame, descriptors, globals, code and carried registers retain stated values',
            'buffer and descriptor aliasing, asynchronous writes and actual mappings remain open',
            'host arithmetic examples are not observed device values or firmware guards'],
        limits=['no indirect control transfer in selected continuation; callees and external execution remain open',
            'dynamic B/Q/argument stores cannot be excluded as aliases of 0x31580 or 0x31998',
            '0x1a668 is a separate frontier; no inference about its effects is added here',
            'no proof of slot47 caller, X0 origin, binding preservation or hardware reachability'],
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
