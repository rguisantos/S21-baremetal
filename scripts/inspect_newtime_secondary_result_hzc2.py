#!/usr/bin/env python3
"""Bounded HZC2 secondary-result graph, buffer identities and arithmetic."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_common_continuation_hzc2 import corrected_byte, pack_level
from inspect_newtime_jump_tables_hzc2 import DELTA, adrp_add_base, adrp_page, case_walk, u32
from inspect_newtime_mif_bins_hzc2 import direct_callers

MASK64 = (1 << 64) - 1
RANGES = ((0x18068, 0x1809c), (0x19038, 0x19088), (0x1a26c, 0x1a5b0),
          (0x1a804, 0x1aab4), (0x1ae30, 0x1aea8),
          (0x1b0dc, 0x1b148), (0x1b330, 0x1b35c))
SELECTED = {
    0x19054: ('mov', 'w0, #0x5e4'), 0x19078: ('bl', '0x18068'),
    0x1907c: ('add', 'x1, x20, #0xa40'), 0x19084: ('str', 'x0, [x1, #32]'),
    0x1a80c: ('stp', 'x25, x26, [sp, #64]'),
    0x1a824: ('stp', 'x27, x28, [sp, #80]'),
    0x1a814: ('mov', 'w25, w5'), 0x1a828: ('mov', 'x23, x1'),
    0x1a82c: ('mov', 'w28, w0'), 0x1a830: ('mov', 'x19, x2'),
    0x1a834: ('mov', 'x21, x3'), 0x1a838: ('mov', 'w24, w4'),
    0x1a83c: ('mov', 'x20, x6'),
    0x1a840: ('ldr', 'x27, [x26, #2656]'),
    0x1a84c: ('ldr', 'w22, [x3, #16]'),
    0x1a850: ('lsl', 'w0, w22, #2'), 0x1a854: ('bl', '0x18068'),
    0x1a858: ('mov', 'x13, x0'), 0x1a85c: ('cmp', 'w28, #0x3'),
    0x1a868: ('add', 'x27, x27, #0x410'),
    0x1a86c: ('ldr', 'x0, [x0, #2664]'),
    0x1a870: ('ldrb', 'w0, [x0, #7]'),
    0x1a874: ('cbnz', 'w0, 0x1a888'),
    0x1a87c: ('sub', 'x0, x20, x0'),
    0x1a880: ('strh', 'w0, [x27, #18]'),
    0x1a89c: ('ldr', 'x1, [x0, #176]'),
    0x1a8a4: ('ubfx', 'x1, x1, #4, #2'),
    0x1a8a8: ('msub', 'w1, w1, w2, w3'),
    0x1a8bc: ('ubfx', 'x1, x1, #6, #2'),
    0x1a8d4: ('and', 'w1, w1, #0x3'),
    0x1a8ec: ('and', 'w1, w1, #0x3'),
    0x1a8fc: ('sub', 'x0, x13, x0'),
    0x1a900: ('strh', 'w0, [x27, #18]'),
    0x1a908: ('cmp', 'w28, #0x2'),
    0x1a91c: ('ldrb', 'w0, [x0, #6]'),
    0x1a920: ('cbnz', 'w0, 0x1a938'),
    0x1a928: ('sub', 'x0, x20, x0'),
    0x1a92c: ('strh', 'w0, [x27, #16]'),
    0x1a930: ('mov', 'x0, x20'), 0x1a934: ('b', '0x1aa98'),
    0x1a954: ('ubfx', 'x1, x1, #2, #2'),
    0x1a96c: ('ubfx', 'x1, x1, #4, #2'),
    0x1a984: ('ubfx', 'x1, x1, #6, #2'),
    0x1a99c: ('ubfx', 'x1, x1, #6, #2'),
    0x1a9b0: ('strh', 'w0, [x27, #16]'),
    0x1a9c4: ('bl', '0x1a294'), 0x1a9c8: ('mov', 'x0, x13'),
    0x1a9cc: ('cbz', 'x21, 0x1aa98'),
    0x1a9d0: ('ldr', 'w0, [x21, #20]'),
    0x1a9dc: ('umull', 'x1, w0, w1'),
    0x1a9e4: ('cmp', 'x1, x0'), 0x1a9e8: ('b.eq', '0x1aa04'),
    0x1a9f4: ('add', 'x0, x0, #0x30'),
    0x1aa14: ('cmp', 'w18, w22'),
    0x1aa10: ('mov', 'w27, #0x3e8'),
    0x1aa20: ('sub', 'x20, x15, x13'),
    0x1aa2c: ('ldr', 'w2, [x0, x20]'), 0x1aa34: ('bl', '0x1a294'),
    0x1aa38: ('ldr', 'w1, [x14]'),
    0x1aa4c: ('madd', 'w2, w18, w2, w25'),
    0x1aa58: ('cmp', 'w1, #0xa1'),
    0x1aa5c: ('csel', 'w1, w2, w1, cs'),
    0x1aa64: ('strb', 'w1, [x15, #3]'),
    0x1aa6c: ('strb', 'w0, [x15, #3]'),
    0x1aa80: ('mul', 'w0, w0, w27'),
    0x1aa84: ('and', 'w0, w0, #0xfffff8'),
    0x1aa88: ('bfxil', 'w1, w0, #0, #24'),
    0x1aa8c: ('str', 'w1, [x15], #4'),
    0x1aa94: ('mov', 'x0, x13'), 0x1aab0: ('ret', ''),
    0x1aaa4: ('ldp', 'x25, x26, [sp, #64]'),
    0x1aaa8: ('ldp', 'x27, x28, [sp, #80]'),
    0x1ae44: ('ldr', 'x0, [x0, #176]'),
    0x1ae54: ('ldrb', 'w0, [x0, #2]'),
    0x1ae58: ('ldr', 'x1, [x1, #2664]'),
    0x1ae5c: ('ubfx', 'x0, x0, #3, #1'),
    0x1ae60: ('uxtb', 'w27, w0'), 0x1ae64: ('strb', 'w0, [x1, #6]'),
    0x1ae80: ('ldr', 'x0, [x0, #176]'),
    0x1ae90: ('ldrb', 'w0, [x0, #2]'),
    0x1ae94: ('ldr', 'x1, [x1, #2664]'),
    0x1ae98: ('ubfx', 'x0, x0, #2, #1'),
    0x1ae9c: ('uxtb', 'w27, w0'), 0x1aea0: ('strb', 'w0, [x1, #7]'),
    0x1b110: ('strb', 'w4, [x5, #3]'),
    0x1b114: ('b.eq', '0x1b138'),
    0x1b11c: ('add', 'x2, x0, x2'),
    0x1b12c: ('ldrb', 'w3, [x2, #3]'),
    0x1b134: ('strb', 'w3, [x2, #3]'),
    0x1b354: ('bl', '0x1a804'), 0x1b358: ('b', '0x1b0dc'),
}


def byte(value):
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError('expected byte')
    return value


def xword(value):
    if type(value) is not int or not 0 <= value <= MASK64:
        raise ValueError('expected X-register value')
    return value


def route(selector, gate=None):
    u32(selector)
    if selector not in (2, 3):
        return dict(return_kind='allocated', metadata_offset=None, gate_offset=None)
    byte(gate)
    return dict(return_kind='original' if gate == 0 else 'allocated',
                metadata_offset=0x420 if selector == 2 else 0x422,
                gate_offset=6 if selector == 2 else 7)


def case_gate(selector, byte2):
    u32(selector)
    byte(byte2)
    if selector not in (2, 3):
        raise ValueError('no selected case gate')
    return (byte2 >> (3 if selector == 2 else 2)) & 1


def adjusted_samples(selector, b2, b3, samples):
    u32(selector)
    byte(b2)
    byte(b3)
    if len(samples) != 4:
        raise ValueError('expected four samples')
    for value in samples:
        u32(value)
    if selector == 3:
        fields = [(b2 >> 4) & 3, (b2 >> 6) & 3, b3 & 3, b3 & 3]
    elif selector == 2:
        fields = [(b3 >> 2) & 3, (b3 >> 4) & 3, (b3 >> 6) & 3, (b3 >> 6) & 3]
    else:
        raise ValueError('no selected sample adjustment')
    return [(v - 6250*f) & 0xffffffff for v, f in zip(samples, fields)]


def metadata_write(selector, gate, root_entry, root_late, original, allocated):
    for value in (root_entry, root_late, original, allocated):
        xword(value)
    decision = route(selector, gate)
    if decision['metadata_offset'] is None:
        return None
    pointer = original if decision['return_kind'] == 'original' else allocated
    return dict(address=(root_entry + decision['metadata_offset']) & MASK64,
                value=(pointer - root_late) & 65535, width=2)


def record_span(count):
    u32(count)
    return count * 48  # UMULL X: no signed32 conversion or W multiply wrap.


def selected_record(keys, wanted, count):
    u32(wanted)
    record_span(count)
    if len(keys) != count:
        raise ValueError('host fixture must supply the unsigned record count')
    for key in keys:
        u32(key)
    if count == 0:
        return dict(index=None, zero_key_read_if_n_positive=True)
    found = next((i for i, key in enumerate(keys) if key == wanted), None)
    return dict(index=count - 1 if found is None else found,
                zero_key_read_if_n_positive=False)


def result_word(level, numerical_W, code=None):
    u32(numerical_W)
    high = numerical_W & 255 if code is None else corrected_byte(numerical_W, code)
    return pack_level(high << 24, level)


def apply_margin_pair(primary, secondary, margin, tag, same_buffer):
    """Two ordered byte stores, under stable E data and exact B==Q or disjointness."""
    for value in (primary, secondary, margin):
        byte(value)
    u32(tag)
    if type(same_buffer) is not bool or (same_buffer and primary != secondary):
        raise ValueError('inconsistent host alias fixture')
    p = (primary + margin) & 255
    s = p if same_buffer else secondary
    if tag != 255:
        s = (s + margin) & 255
        if same_buffer:
            p = s
    return dict(primary=p, secondary=s, stores=1 if tag == 255 else 2)


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
            if target != direct_target(op, args):
                raise ValueError('GNU relative target differs')
            relative += 1
    for pc, want in SELECTED.items():
        if lines[pc][1:] != want:
            raise ValueError(f'GNU selected operands differ at {pc:#x}')
    walk = case_walk(data, [0x1a804], 0x1a804, 0x1aab4)
    if (len(walk['visited']) != 172 or walk['exits'] != [dict(pc='0x1aab0', reason='ret')] or
            [(c['pc'], c['target_file']) for c in walk['calls']] !=
            [('0x1a854', '0x18068'), ('0x1a9c4', '0x1a294'), ('0x1aa34', '0x1a294')]):
        raise ValueError('selected secondary-result graph differs')
    numerical = case_walk(data, [0x1a294], 0x1a294, 0x1a5b0)
    if numerical['calls'] or numerical['exits'] != [dict(pc='0x1a5ac', reason='ret')]:
        raise ValueError('numerical helper escapes')
    if any(re.search(r'\b[wx](?:1[3-9]|2[0-8])\b', lines[p][2])
           for p in range(0x1a26c, 0x1a5b0, 4)):
        raise ValueError('packed/numerical helper references carried GPRs')
    root_cell = adrp_page(lines[0x1a810][0], 0x1a810) - DELTA + 2656
    config_cell = adrp_page(lines[0x1a864][0], 0x1a864) - DELTA + 2664
    packed_cell = adrp_page(lines[0x1a888][0], 0x1a888) - DELTA + 0xaa8 + 8 + 176
    published_cell = adrp_add_base(lines[0x19040][0], lines[0x1907c][0], 0x19040) + 32
    if root_cell != published_cell:
        raise ValueError('selected root publication differs')
    return dict(mode='static_newtime_secondary_result_hzc2', sboot_sha256=IMAGES['sboot'][1],
        nominal_delta=hex(DELTA), local_walk=walk,
        direct_B_BL_callers=dict(sites=direct_callers(data, 0x1a804),
            range=['0x16000', '0x2fd00'], global_uniqueness_proved=False),
        arguments=dict(W0='selector', X1='A: four input points', X2='Y: four mutable samples',
            X3='D: dynamic descriptor', W4='wanted record key', W5='column', X6='B: original buffer'),
        allocation=dict(pc='0x1a854', count='n_entry=u32(M32[D+16]) or zero',
            request='u32(4*n_entry), then allocator SXTW',
            before_selector_and_gate_tests=True, allocated_symbol='Qnew, old arena cursor',
            requires_normal_return=True),
        cells=[dict(role=role, file=hex(cell), initial_file_value=hex(struct.unpack_from('<Q', data, cell)[0]))
               for role, cell in [('root', root_cell), ('config_pointer', config_cell),
                                  ('sample_bits_pointer', packed_cell)]],
        root_publication=dict(pc='0x19084', cell=hex(published_cell),
            value='selected allocator return after request 0x5e4=1508 bytes',
            exclusive_writer_or_runtime_order_proved=False),
        paths=[dict(selector=s, gate_byte=g, return_kind=route(s, g)['return_kind'],
                    metadata_offset=hex(route(s, g)['metadata_offset']) if s in (2, 3) else None,
                    sample_adjustment=s in (2, 3) and g != 0)
               for s, g in [(2, 0), (2, 1), (3, 0), (3, 1), (0, None)]],
        metadata=dict(root_destination='Rentry + 0x420 for selector 2, +0x422 for selector 3',
            encoded_value='low16((B on fast path, Qnew otherwise) - Rlate)',
            root_reload='Rlate is reloaded from 0x31a60; not assumed identical to Rentry',
            width=2, reconstructs_full_pointer=False),
        sample_adjustments=dict(unit_scale=6250, arithmetic='u32 subtraction of two-bit field * 6250',
            selector2_fields=['byte3[3:2]', 'byte3[5:4]', 'byte3[7:6]', 'byte3[7:6]'],
            selector3_fields=['byte2[5:4]', 'byte2[7:6]', 'byte3[1:0]', 'byte3[1:0]'],
            guard='selected config byte nonzero; four stores occur even when n_entry==0',
            alias_and_repeated_pointer_reads='fields/bytes modeled as stable only under explicit nonalias conditions'),
        record_search=dict(count='unsigned M32[D+20], loaded after numerical setup',
            byte_span='UMULL(u32(count),48), not signed32 or W32 multiplication',
            choice='first matching key, otherwise last record',
            zero_count='X14 remains zero; key load at 0x1aa38 reads zero if n_entry>0',
            mapping_and_fault_observed=False),
        numerical_helper=dict(entry='0x1a294', carried_GPRs_13_through_28='not referenced in selected body',
            floating_point_results_and_memory_effects='opaque',
            setup_call='0x1a9c4: A,Y,W2=0,W3=0',
            loop_call='0x1aa34: A,Y,W2=level[i],W3=1'),
        filled_word='(low8(numerical_W + optional byte correction)<<24) | (u32(level*1000)&0x00fffff8)',
        caller_interaction=dict(call='0x1b354', returns_to='0x1b358 -> 0x1b0dc',
            case_gate_publication='case 2 copies Z.byte2 bit3 to W27 and P.byte6; case 3 copies bit2 to W27 and P.byte7',
            gate_tag_relation='under preservation, tag is the same 0/1 gate value; zero selects return B',
            tag_restored='0x1a824 saves caller X27 and 0x1aaa8 restores it at the sole epilogue; internal W27=1000 does not escape',
            exact_alias='fast paths return B, so caller Q==B',
            ordered_stores=['0x1b110 B-byte add', '0x1b134 Q-byte add when tag!=255'],
            conditional_effect='if correction loop runs, tag!=255, Q==B and E-byte is stable, same byte receives two additions modulo 256',
            feasibility_or_nonzero_margin_observed=False),
        gnu=dict(version=version, words=len(lines), relative_targets=relative, selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(p), word=f'{w:08x}', op=op, args=args)
                   for p, (w, op, args) in sorted(lines.items())],
        conditions=['normal returns from the allocator and numerical helper',
            'valid private frames, preserved code and nominal BL2 mapping',
            'dynamic pointers, repeated fields and nonalias relations are premises, not measured facts',
            'both conditional CFG edges retained without solving hardware/data feasibility'],
        limits=['no actual pointer, gate byte, E margin or floating-point output was observed',
            'new allocation does not establish physical disjointness from B or other cells',
            'metadata and buffer stores remain possible aliases; no global slot47 exclusion',
            'no physical interpretation or vulnerability claim from synthetic arithmetic'],
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
