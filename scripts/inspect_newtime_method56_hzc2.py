#!/usr/bin/env python3
"""Hash-bound static method+56 dispatch, request publication and reply polling."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_asv_gen_hzc2 import named_directory
from inspect_newtime_hzc2 import embedded

DELTA = 0x020ea000
U32, U64 = (1 << 32) - 1, (1 << 64) - 1
RANGES = ((0x17c04, 0x17e14), (0x17fb4, 0x17fc8), (0x190ec, 0x19140),
          (0x1b148, 0x1b1a8), (0x1b35c, 0x1b37c),
          (0x1dcb4, 0x1dcc0), (0x22560, 0x22570), (0x2f488, 0x2f4b0))
SELECTED = {
    0x17c10: ('ldr', 'w6, [x3, #688]'), 0x17c14: ('ldr', 'w5, [x3, #700]'),
    0x17c18: ('sub', 'w4, w6, #0x4'), 0x17c1c: ('ldr', 'w4, [x4]'),
    0x17c20: ('madd', 'w5, w4, w5, w6'), 0x17c24: ('str', 'w0, [x5]'),
    0x17c28: ('ldr', 'w0, [x3, #688]'), 0x17c2c: ('ldr', 'w5, [x3, #700]'),
    0x17c38: ('madd', 'w0, w4, w5, w0'), 0x17c3c: ('str', 'w1, [x0]'),
    0x17c40: ('ldr', 'w0, [x3, #688]'), 0x17c44: ('ldr', 'w1, [x3, #700]'),
    0x17c4c: ('madd', 'w0, w4, w1, w0'), 0x17c54: ('str', 'w1, [x0]'),
    0x17c58: ('ldr', 'w0, [x3, #688]'), 0x17c5c: ('ldr', 'w1, [x3, #700]'),
    0x17c64: ('madd', 'w0, w4, w1, w0'), 0x17c6c: ('add', 'w4, w4, #0x1'),
    0x17c70: ('str', 'w1, [x0]'), 0x17c74: ('ldr', 'w1, [x3, #696]'),
    0x17c78: ('udiv', 'w0, w4, w1'), 0x17c7c: ('msub', 'w4, w0, w1, w4'),
    0x17c88: ('str', 'w4, [x0]'), 0x17c90: ('ldr', 'x2, [x3, #672]'),
    0x17c94: ('str', 'w0, [x2, #32]'), 0x17c98: ('ldr', 'w0, [x3, #680]'),
    0x17ca4: ('lsl', 'w0, w0, w1'), 0x17ca8: ('str', 'w0, [x2, #8]'),
    0x17cbc: ('and', 'w0, w0, #0xffff0000'),
    0x17cc0: ('ldr', 'w4, [x2, #692]'), 0x17cc4: ('ldr', 'w5, [x2, #700]'),
    0x17cc8: ('ldr', 'x6, [x2, #672]'), 0x17ccc: ('sub', 'w3, w4, #0x8'),
    0x17cd0: ('ldr', 'w2, [x6, #40]'), 0x17cd4: ('and', 'w2, w2, #0xf'),
    0x17cd8: ('cbz', 'w2, 0x17cd0'), 0x17cdc: ('ldr', 'w2, [x3]'),
    0x17ce0: ('madd', 'w2, w2, w5, w4'), 0x17ce4: ('ldr', 'w2, [x2]'),
    0x17ce8: ('cmp', 'w2, w0'), 0x17cec: ('b.ne', '0x17cd0'),
    0x17cf4: ('ldr', 'w0, [x3]'), 0x17cfc: ('ldr', 'w4, [x1, #696]'),
    0x17d00: ('udiv', 'w2, w0, w4'), 0x17d04: ('msub', 'w0, w2, w4, w0'),
    0x17d08: ('str', 'w0, [x3]'), 0x17d14: ('str', 'w1, [x0, #32]'),
    0x17d24: ('str', 'wzr, [sp, #16]'), 0x17d2c: ('ldr', 'x2, [x1, #2656]'),
    0x17d30: ('ldrh', 'w1, [x2, #20]'), 0x17d38: ('add', 'x0, x1, w0, uxtw #2'),
    0x17d40: ('ldr', 'w0, [x2, x0]'), 0x17d48: ('str', 'wzr, [x7, #-4]!'),
    0x17d4c: ('ubfx', 'x0, x0, #0, #24'), 0x17d50: ('str', 'w0, [sp, #20]'),
    0x17d54: ('mov', 'w0, #0x6'), 0x17d5c: ('str', 'w0, [sp, #24]'),
    0x17d64: ('bl', '0x17c04'), 0x17d78: ('bl', '0x17cb0'),
    0x17d8c: ('cbnz', 'w1, 0x17da0'), 0x17d98: ('ldr', 'x1, [x1, #40]'),
    0x17d9c: ('strb', 'w2, [x1, #25]'), 0x17da0: ('bl', '0x17d1c'),
    0x17da8: ('ldr', 'x0, [x8, #40]'), 0x17dac: ('strb', 'wzr, [x0, #25]'),
    0x17db0: ('str', 'wzr, [x0, #20]'),
    0x17dcc: ('ldr', 'w0, [x0, #8]'), 0x17dd0: ('add', 'w0, w0, w2'),
    0x17dd8: ('cbz', 'w0, 0x17e10'), 0x17de0: ('ldr', 'w3, [x1, #96]'),
    0x17dec: ('add', 'w3, w3, w2'), 0x17df0: ('str', 'w3, [x0, #688]'),
    0x17df4: ('ldr', 'w3, [x1, #48]'), 0x17dfc: ('str', 'w2, [x0, #692]'),
    0x17e00: ('ldr', 'w2, [x1, #52]'), 0x17e04: ('ldr', 'w1, [x1, #56]'),
    0x17e08: ('str', 'w2, [x0, #696]'), 0x17e0c: ('str', 'w1, [x0, #700]'),
    0x17fb4: ('bl', '0x17dbc'),
    0x190f0: ('mov', 'x8, #0x34'),
    0x190fc: ('mul', 'x28, x19, x8'), 0x19100: ('ldr', 'x10, [x9, #32]'),
    0x19110: ('add', 'x22, x10, x28'), 0x1911c: ('bl', '0x1aab4'),
    0x19124: ('ldr', 'x1, [x9, #32]'), 0x19128: ('sub', 'x0, x0, x1'),
    0x1912c: ('strh', 'w0, [x22, #20]'),
    0x1b150: ('mov', 'w4, #0x3e8'),
    0x1b17c: ('ldr', 'x1, [x28, #24]'), 0x1b184: ('ldr', 'w3, [x25, x2]'),
    0x1b188: ('ldr', 'w1, [x1, x2]'), 0x1b18c: ('mul', 'w1, w1, w4'),
    0x1b190: ('and', 'w1, w1, #0xfffff8'),
    0x1b194: ('bfxil', 'w3, w1, #0, #24'), 0x1b198: ('str', 'w3, [x25, x2]'),
    0x1b35c: ('mov', 'x0, x25'),
    0x1dcb4: ('cbz', 'x3, 0x1dcc0'), 0x1dcbc: ('str', 'x3, [x0, #784]'),
    0x22564: ('mov', 'w0, w21'), 0x22568: ('mov', 'w1, #0x0'),
    0x2256c: ('blr', 'x2'), 0x2f490: ('ldr', 'x2, [x2, #2456]'),
    0x2f494: ('ldr', 'x2, [x2, #56]'), 0x2f498: ('blr', 'x2'),
    0x2f4a4: ('ldr', 'x1, [x0, #64]'), 0x2f4a8: ('mov', 'w0, #0x4'),
    0x2f4ac: ('br', 'x1'),
}


def uint(value, bits):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'expected host u{bits}')
    return value


def record_address(root, offset16, index):
    """ADD X, W UXTW #2; this offset does not truncate at 32 bits."""
    return (uint(root, 64) + uint(offset16, 16) + (uint(index, 32) << 2)) & U64


def request_words(record_word):
    return [0, uint(record_word, 32) & 0xffffff, 6, 6]


def relative_vector(root, vector):
    uint(root, 64); uint(vector, 64)
    offset = (vector-root) & 65535
    reconstructed = (root+offset) & U64
    return dict(offset16=offset, reconstructed=reconstructed, exact=reconstructed == vector)


def packed_level(previous, level):
    uint(previous, 32); uint(level, 32)
    return (previous & 0xff000000) | ((level * 1000) & 0x00fffff8)


def ring_addresses(base, stride, index):
    """Stable-config fixture only: real code reloads base/stride between stores."""
    for value in (base, stride, index):
        uint(value, 32)
    return [(base + offset + stride * index) & U32 for offset in (0, 4, 8, 12)]


def advance(index, count):
    uint(index, 32); uint(count, 32)
    increment = (index + 1) & U32
    quotient = increment // count if count else 0  # A64 UDIV by zero is zero.
    return (increment - quotient * count) & U32


def doorbell(channel):
    return 1 << (((uint(channel, 32) + 16) & U32) & 31)


def reply_matches(status, reply_word, request_word0=0):
    for value in (status, reply_word, request_word0):
        uint(value, 32)
    return bool(status & 15) and reply_word == (request_word0 & 0xffff0000)


def marker_stores(flag, before, after):
    uint(flag, 32); uint(before, 64); uint(after, 64)
    result = [] if flag else [dict(phase='before_request', address=(before+25)&U64, width=1, value=0x5a)]
    return result + [dict(phase='after_reply', address=(after+25)&U64, width=1, value=0),
                     dict(phase='after_reply', address=(after+20)&U64, width=4, value=0)]


def channel_config(pointer_word, tx_offset, rx_offset, count, stride):
    """Selected 17dbc fixture; fields are read only when wrapped pointer != 0."""
    for value in (pointer_word, tx_offset, rx_offset, count, stride):
        uint(value, 32)
    base = (pointer_word + 0x02039000) & U32
    if base == 0:
        return dict(table=None, config_written=False)
    return dict(table=base, config_written=True, tx=(tx_offset+0x02039000)&U32,
                rx=(rx_offset+0x02039000)&U32, count=count, stride=stride)


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
                raise ValueError(f'GNU relative target differs at {pc:#x}')
            relative += 1
    for pc, expected in SELECTED.items():
        if lines[pc][1:] != expected:
            raise ValueError(f'GNU operand differs at {pc:#x}: {lines[pc][1:]}')
    for lo, hi in ((0x17c04, 0x17cb0), (0x17cb0, 0x17d1c)):
        if any(re.search(r'\b[wx](?:7|8|19|20|21|22|23|24|25|26|27|28|29)\b', lines[p][2])
               or lines[p][1] in ('bl', 'blr', 'smc', 'hvc') for p in range(lo, hi, 4)):
            raise ValueError('selected leaf preservation differs')
    if any(re.search(r'\b[wx](?:8|19|20|21|22|23|24|25|26|27|28|29)\b', lines[p][2])
           for p in range(0x17d1c, 0x17d84, 4)):
        raise ValueError('packet wrapper selected register preservation differs')
    q = lambda at: struct.unpack_from('<Q', data, at)[0]
    w = lambda at: struct.unpack_from('<I', data, at)[0]
    required = {0x314a8: 0x02119488, 0x30818: 0x02101d84,
                0x31998: 0, 0x31040: 0x0211424c, 0x307c0: 0x15900000,
                0x31a60: U64, 0x31a68: U64}
    if any(q(at) != value for at, value in required.items()):
        raise ValueError('selected initial pointer cells differ')
    ect = embedded(data); directory = dict(ect['directory']); origin = ect['source_file']
    asv_start = origin + directory['ASV']
    asv_end = origin + min(off for off in directory.values() if off > directory['ASV'])
    asv = data[asv_start:asv_end]
    version, _, records = named_directory(asv)
    columns, n, _ = struct.unpack_from('<III', asv, records['MIF'])
    if version != 3 or n != 13 or columns != 12:
        raise ValueError('selected ASV MIF layout differs')
    levels = struct.unpack_from('<'+'I'*n, asv, records['MIF']+12)
    calls = []
    for pc in range(0x16000, 0x2fd00, 4):
        kind, target = flow(w(pc), pc)
        if kind in ('b', 'bl') and target in (0x17c04, 0x17cb0, 0x17d1c, 0x17d84, 0x17dbc):
            calls.append(dict(pc=hex(pc), kind=kind, target=hex(target)))
    return dict(mode='static_method56_queue_hzc2', sboot_sha256=IMAGES['sboot'][1],
        source_base='e00c9b1c1c58467b0fb6656c402a89691b4c22e5', nominal_BL2_delta=hex(DELTA),
        initial_cells={hex(at):hex(value) for at, value in required.items()},
        dispatch=dict(wrapper_call='0x2256c', W0='k=W21', W1=0, slot20_cell='0x314a8',
            slot20_nominal_target='0x2f488', binding_cell='0x31998',
            selected_provider_file='0x307e0', selected_provider_nominal='0x0211a7e0',
            method_offset=56, method_cell='0x30818', call='0x2f498',
            conditional_target='0x17d84', successor=dict(branch='0x2f4ac', cell='0x31040',
                initial_target_file=hex(q(0x31040)-DELTA), W0=4, transitive_effects='open')),
        request=dict(wrapper='0x17d84', packet_builder='0x17d1c', root_cell='0x31a60',
            root='R=M64[nominal(0x31a60)]', address='u64(R+u16(M16[R+20])+4*u32(k))',
            read='0x17d40', word_formula='M32[address]&0x00ffffff',
            local_frame_words_at_16=[0,'low24(record_word)',6,0],
            published_words=[0,'low24(record_word)',6,6],
            fourth_published_word='0x17c68 reloads [X2] (local+24), not local+28',
            no_syntactic_k_bounds_check=True, direct_buffer_B_argument=False,
            buffer_B_value_dependency='not established; dynamic roots and aliases remain open'),
        selected_word_producer=dict(driver_call='0x1911c', driver_target='0x1aab4',
            driver_record='Rentry+52*domain_selector; selected first record domain0=MIF',
            relative_store='0x1912c: M16[Rentry+52*selector+20]=low16(returned_U-Rlate)',
            consumer_record='Rconsume+20, not Rconsume+52*k+20; k selects a word of the first vector',
            requirements=['Rentry=Rlate=Rconsume and selector0 store reached/preserved',
                'u64(Rconsume+low16(U-Rlate))==U; no unproved 16bit roundtrip',
                'returned U and ASV level fields/words preserved after normal construction',
                'k<n and final packing loop completed; earlier gates/calls are still conditions'],
            U='X25 of common continuation, returned at 0x1b35c; distinct label from slot38 temporary B',
            packing='0x1b198: (previous&0xff000000)|(u32(level[k]*1000)&0x00fffff8)',
            payload_MIF_levels=list(levels), selected_n=n,
            conditional_request_values=[packed_level(0, v)&0xffffff for v in levels],
            upper_byte_ignored='under the same valid vector/word, packet low24 removes MARGIN byte corrections'),
        marker=dict(root_cell='0x31a68', pointer='P=M64[nominal(0x31a68)]',
            before='if W1==0: M8[P_before+25]=0x5a at 0x17d9c',
            after='after normal reply: reload P_after; M8[P_after+25]=0; M32[P_after+20]=0',
            same_before_after_pointer_proved=False,
            method_return='P_after in X0; slot20 overwrites X0 before its tail branch'),
        configuration=dict(initial_MMIO_base=hex(q(0x307c0)), initial_channel=w(0x307c8),
            initial_tx=w(0x307d0), initial_rx=w(0x307d4), initial_count=w(0x307d8), initial_stride=w(0x307dc),
            state_cells=dict(MMIO='0x307c0', channel='0x307c8', tx='0x307d0', rx='0x307d4',
                             count='0x307d8', stride='0x307dc'),
            initializer='0x17dbc', direct_call='0x17fb4',
            table='T=u32(M32[AP0x02041008]+0x02039000); if T==0 no config stores',
            fields='tx=u32(M32[T+96]+0x02039000); rx=u32(M32[T+120]+0x02039000); count=M32[T+124]; stride=M32[T+128]',
            runtime_values_observed=False),
        publication=dict(leaf='0x17c04', index='i=M32[u32(tx-4)]',
            stores=[dict(pc=hex(pc), address=f'u32(tx+{offset}+i*stride)', value=value)
                for pc, offset, value in ((0x17c24,0,0),(0x17c3c,4,'low24(record_word)'),
                                         (0x17c54,8,6),(0x17c70,12,6))],
            caveat='tx/stride are reloaded for each store; repeated source packet words are reloaded too',
            index_update='M32[u32(tx_reloaded-4)]=remainder_u32(u32(i+1), count_reloaded)',
            zero_divisor='UDIV yields zero; MSUB leaves wrapped increment, not host modulo exception',
            notifications=['0x17c94: M32[MMIO+32]=0xffff',
                           '0x17ca8: M32[MMIO+8]=1<<((u32(channel+16))&31)'],
            bounds_or_full_queue_guard=False, explicit_barrier_in_selected_leaf=False),
        reply=dict(leaf='0x17cb0', captured='rx/stride/MMIO captured before polling',
            loop_header='0x17cd0', status='M32[MMIO+40]&15',
            pending='status==0 OR M32[u32(rx+M32[u32(rx-8)]*stride)]!=(packet_word0&0xffff0000)',
            expected_for_selected_packet=0, matched_word_is_full_u32=True,
            syntactic_timeout_or_retry_limit=False,
            completion=['reload index; advance with reloaded count; store at u32(rx-8)',
                        'reload MMIO base; M32[MMIO+32]=2'],
            response_body_copied=False, return_value='MMIO base, not response payload or success code'),
        direct_calls_in_aligned_BL2_scan=calls,
        conditions=['nominal BL2 mapping; successful earlier binding publication and no intervening replacement',
            'slot20, method cell and successor cell preserved; dynamic R/P/config and selected memory readable',
            'private stack and packet words preserved; no alias changes to config or packet between reloads',
            'poll status and reply eventually satisfy predicates; stores/reads complete normally',
            'firmware syntax and host fixtures do not establish hardware ordering, side effects or valid resources'],
        conclusion=['method+56 conditionally resolves to packet command6 with a runtime selected low24 word',
            'RAM restore after return does not cover queue/MMIO effects or undo a consumed request',
            'no direct B-to-packet value edge or hardware meaning demonstrated; no slot47 caller/X0 resolved'],
        gnu=dict(version=subprocess.check_output(cmd+['--version'], text=True).splitlines()[0],
                 words=len(lines), relative_targets=relative, selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(pc), word=f'{word:08x}', op=op, args=args)
            for pc, (word, op, args) in sorted(lines.items())],
        firmware_executed=False, qemu_scope_extended=False, physical_device_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('sboot'); args = parser.parse_args()
    try:
        report = inspect(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'inspect_newtime_method56_hzc2: {exc}\n')
    print(json.dumps(report, indent=2))
