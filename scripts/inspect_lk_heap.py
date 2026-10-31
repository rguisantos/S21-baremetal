#!/usr/bin/env python3
"""Trace the pinned LK heap to its page pool; establish no physical/DMA mapping."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_avb_boot import wide_constant
from inspect_lk_build_id import page_plus_add, load_unsigned_w
from inspect_lk_embedded_key import adrp
from inspect_lk_payload_return import DELTA, summarize_local
from inspect_lk_precopy_measurement import verify_disassembly

U64 = (1 << 64)-1
BLOCKS = {
    'init_dispatcher': (0xfa7b0, 0xfa8cc),
    'startup_fragment': (0xfa990, 0xfa9cc),
    'pool_constructor': (0x18d808, 0x18d8e8),
    'pool_binding': (0x18d8e8, 0x18d918),
    'page_allocator': (0x18d918, 0x18d9ec),
    'page_request': (0x18d9f0, 0x18da28),
    'heap_seed': (0x18da28, 0x18da64),
    'heap_init': (0x18fd30, 0x18fd50),
    'allocation_wrappers': (0x18fd50, 0x18fde8),
    'page_tail': (0x18fef0, 0x18fef4),
    'seed_tail': (0x18fef8, 0x18fefc),
    'free_chunk': (0x20bf58, 0x20c094),
    'heap_allocator': (0x20c098, 0x20c340),
    'heap_constructor': (0x20c410, 0x20c478),
    'configuration_getter': (0x147ea8, 0x147eb4),
}
SELECTED = {
    0xfa990: ('mov', 'w2, #0x1ffff'),
    0xfa994: ('mov', 'w1, #0x10000'),
    0xfa998: ('mov', 'w0, #0x1'),
    0xfa99c: ('bl', '0xfa7b0'),
    0xfa9c8: ('bl', '0x18fd30'),
    0xfa800: ('ldr', 'w3, [x0, #4]'),
    0xfa814: ('ldr', 'w3, [x0]'),
    0xfa858: ('ldr', 'x1, [x22, #8]'),
    0xfa85c: ('blr', 'x1'),
    0x18d818: ('add', 'x19, x2, #0xfff'),
    0x18d820: ('and', 'x19, x19, #0xfffffffffffff000'),
    0x18d824: ('and', 'x21, x3, #0xfffffffffffff000'),
    0x18d84c: ('lsr', 'x20, x21, #12'),
    0x18d850: ('cmp', 'x24, xzr'),
    0x18d858: ('ccmp', 'x20, x26, #0x2, ne'),
    0x18d85c: ('b.ls', '0x18d8d8'),
    0x18d89c: ('stp', 'x22, x0, [x23, #96]'),
    0x18d8b0: ('str', 'x24, [x23, #72]'),
    0x18d8bc: ('stp', 'x19, x21, [x23, #80]'),
    0x18d8c0: ('str', 'x20, [x23, #64]'),
    0x18d8e0: ('stp', 'x22, x0, [x23, #96]'),
    0x18d8e8: ('adrp', 'x2, 0xd09000'),
    0x18d8ec: ('adrp', 'x4, 0xd06000'),
    0x18d8f0: ('add', 'x2, x2, #0x0'),
    0x18d8f4: ('mov', 'x3, #0xe9800000'),
    0x18d8fc: ('adrp', 'x0, 0xd07000'),
    0x18d900: ('mov', 'x5, #0x1800'),
    0x18d904: ('add', 'x4, x4, #0x110'),
    0x18d908: ('sub', 'x3, x3, x2'),
    0x18d910: ('add', 'x0, x0, #0x910'),
    0x18d914: ('b', '0x18d808'),
    0x18d918: ('cbz', 'x1, 0x18d9e4'),
    0x18d924: ('ldr', 'x2, [x0, #64]'),
    0x18d934: ('b.hi', '0x18d9d4'),
    0x18d958: ('ldrb', 'w1, [x6, x19]'),
    0x18d97c: ('cmp', 'x3, x7'),
    0x18d988: ('mov', 'w1, #0x1'),
    0x18d98c: ('bl', '0x1af540'),
    0x18d998: ('ldr', 'x0, [x20, #80]'),
    0x18d99c: ('add', 'x0, x0, x19, lsl #12'),
    0x18d9b8: ('b.ls', '0x18d958'),
    0x18d9f0: ('tbnz', 'w1, #0, 0x18da00'),
    0x18da04: ('mov', 'x1, x0'),
    0x18da08: ('adrp', 'x0, 0xd07000'),
    0x18da10: ('add', 'x0, x0, #0x910'),
    0x18da14: ('bl', '0x18d918'),
    0x18da28: ('adrp', 'x1, 0xd07000'),
    0x18da2c: ('add', 'x1, x1, #0x910'),
    0x18da30: ('ldr', 'x2, [x1, #96]'),
    0x18da34: ('cbz', 'x2, 0x18da50'),
    0x18da38: ('ldr', 'x3, [x1, #104]'),
    0x18da3c: ('str', 'x3, [x0]'),
    0x18da44: ('stp', 'xzr, xzr, [x1, #96]'),
    0x18da50: ('mov', 'x2, #0x1000'),
    0x18da58: ('str', 'x2, [x0]'),
    0x18da5c: ('mov', 'x0, #0x1'),
    0x18da60: ('b', '0x18d9f0'),
    0x18fd3c: ('bl', '0x18fef8'),
    0x18fd40: ('ldr', 'x1, [x29, #24]'),
    0x18fd44: ('bl', '0x20c410'),
    0x18fd68: ('b', '0x20c098'),
    0x18fdb4: ('mov', 'w1, w0'),
    0x18fdb8: ('mov', 'x0, x19'),
    0x18fdc4: ('b', '0x20c098'),
    0x18fef0: ('b', '0x18d9f0'),
    0x18fef8: ('b', '0x18da28'),
    0x20bf68: ('adrp', 'x20, 0xd08000'),
    0x20bf70: ('add', 'x21, x20, #0x9b8'),
    0x20bf90: ('add', 'x2, x2, x3'),
    0x20bf94: ('str', 'x2, [x21, #16]'),
    0x20c0a4: ('mov', 'w22, w1'),
    0x20c0a8: ('sub', 'w1, w1, #0x1'),
    0x20c0b8: ('tst', 'w1, w22'),
    0x20c0c0: ('b.ne', '0x20c22c'),
    0x20c0c4: ('add', 'x1, x0, #0x10'),
    0x20c0c8: ('mov', 'x19, #0x18'),
    0x20c0cc: ('cmp', 'x1, #0x17'),
    0x20c0d0: ('b.hi', '0x20c2e4'),
    0x20c0d4: ('cbnz', 'w22, 0x20c2c8'),
    0x20c0d8: ('adrp', 'x26, 0xd08000'),
    0x20c0e0: ('add', 'x26, x26, #0x9b8'),
    0x20c120: ('cmp', 'x19, x0'),
    0x20c124: ('b.hi', '0x20c110'),
    0x20c154: ('b.cs', '0x20c2c0'),
    0x20c184: ('add', 'x25, x1, #0x10'),
    0x20c188: ('cbz', 'w22, 0x20c198'),
    0x20c18c: ('add', 'x25, x24, x25'),
    0x20c190: ('neg', 'x0, x23'),
    0x20c194: ('and', 'x25, x25, x0'),
    0x20c19c: ('stp', 'x1, x19, [x25, #-16]'),
    0x20c1cc: ('add', 'x25, x19, #0xfff'),
    0x20c1d4: ('and', 'x25, x25, #0xfffffffffffff000'),
    0x20c1d8: ('lsr', 'x0, x25, #12'),
    0x20c1dc: ('bl', '0x18fef0'),
    0x20c1ec: ('bl', '0x20bf58'),
    0x20c22c: ('mov', 'x0, #0x0'),
    0x20c2c8: ('cmp', 'w22, #0xf'),
    0x20c2d4: ('mov', 'x0, #0x10'),
    0x20c2dc: ('add', 'x19, x19, x0'),
    0x20c2e4: ('add', 'x0, x0, #0x17'),
    0x20c2e8: ('and', 'x19, x0, #0xfffffffffffffff8'),
    0x20c41c: ('adrp', 'x21, 0xd08000'),
    0x20c428: ('add', 'x19, x21, #0x9b8'),
    0x20c438: ('str', 'x22, [x21, #2488]'),
    0x20c444: ('stp', 'x20, xzr, [x19, #8]'),
    0x20c448: ('stp', 'x0, x0, [x19, #88]'),
    0x20c460: ('str', 'x20, [x22, #16]'),
    0x20c474: ('b', '0x20bf58'),
    0x147ea8: ('adrp', 'x0, 0xcd3000'),
    0x147eac: ('ldr', 'w0, [x0, #456]'),
    0x147eb0: ('ret', ''),
}
STRINGS = {0x25f210: b'novm', 0x25f1c8: b'main',
           0x2906b0: b'%s:%d: failed to grow kernel heap by 0x%zx bytes\n',
           0x2906e8: b'heap_grow'}


def uint(value, bits):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'u{bits} integer required')
    return value


def request_layout(size, alignment):
    """Selected A64 arithmetic only, including wrap; no free-list simulation."""
    uint(size, 64); uint(alignment, 32)
    if alignment & ((alignment-1) & 0xffffffff):
        return dict(accepted=False, reason='alignment_not_power_of_two_or_zero')
    normalized = 24 if ((size+16) & U64) <= 23 else ((size+23) & U64) & ~7
    effective = max(16, alignment) if alignment else 0
    reserved = (normalized+effective) & U64
    return dict(accepted=True, effective_alignment=effective,
                requested_chunk_bytes=reserved,
                size_addition_wrapped=size+23 > U64,
                dma_mapping_or_extent_established=False)


def pool_contract(words):
    pool_reg, pool = page_plus_add(words, 0x18d8e8, 0x18d8f0)
    bitmap_reg, bitmap = page_plus_add(words, 0x18d8ec, 0x18d904)
    context_reg, context = page_plus_add(words, 0x18d8fc, 0x18d910)
    end_reg, end_width, end = wide_constant([words[0x18d8f4]])
    count_reg, count_width, count = wide_constant([words[0x18d900]])
    if (pool_reg, bitmap_reg, context_reg, end_reg, end_width, count_reg, count_width) != (2,4,0,3,64,5,64):
        raise ValueError('pool argument binding differs')
    base = pool+DELTA
    if base % 4096 or not base < end <= 1 << 32 or (end-base) % 4096:
        raise ValueError('nominal pool bounds differ')
    pages=(end-base)//4096
    if pages > count:
        raise ValueError('external bitmap insufficient for selected nominal pool')
    return dict(nominal_va_minus_file=hex(DELTA), relative_base=hex(pool),
        nominal_base=hex(base), end_exclusive=hex(end), bytes=end-base, pages=pages,
        page_bytes=4096, context_relative=hex(context), bitmap_relative=hex(bitmap),
        bitmap_capacity_bytes=count, bitmap_bytes_used=pages,
        below_4g_nominally=True, physical_or_dma_identity_established=False)


def heap_bindings(words):
    reg, heap=page_plus_add(words,0x20c0d8,0x20c0e0)
    ctor_reg, ctor=page_plus_add(words,0x20c41c,0x20c428)
    free_reg, free=page_plus_add(words,0x20bf68,0x20bf70)
    seed_reg, seed=page_plus_add(words,0x18da28,0x18da2c)
    pages_reg, pages=page_plus_add(words,0x18da08,0x18da10)
    getter_reg, getter_page=adrp(words[0x147ea8],0x147ea8)
    dest, base, offset=load_unsigned_w(words[0x147eac])
    if (reg,ctor_reg,free_reg,seed_reg,pages_reg)!=(26,19,21,1,0) or len({heap,ctor,free})!=1 or seed!=pages:
        raise ValueError('heap/page context binding differs')
    if (getter_reg,dest,base)!=(0,0,0):
        raise ValueError('configuration getter binding differs')
    return dict(heap_context_relative=hex(heap),page_context_relative=hex(seed),
                configuration_word_relative=hex(getter_page+offset),
                configuration_word_runtime_value_acquired=False)


def init_record(data):
    if len(data) < 0x29b1a8:
        raise ValueError('truncated initialization record')
    level,flags,function,name=struct.unpack_from('<IIQQ',data,0x29b190)
    if (level,flags,function-DELTA,name-DELTA)!=(0x1ffff,1,0x18d8e8,0x25f210):
        raise ValueError('pool initialization record differs')
    return dict(file_offset='0x29b190',level=hex(level),flags=flags,
                function_file_offset=hex(function-DELTA),name='novm',
                selected_dispatch_precedes_heap_init=True,active_invocation_observed=False)


def inspect(path):
    data=read_exact(path,*IMAGES['sboot'])
    root=Path(__file__).resolve().parent.parent
    command=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
             str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for low,high in BLOCKS.values():
        parsed=parse_lines(subprocess.check_output(command+['-D','-z','-b','binary','-m','aarch64',
            f'--start-address={low}',f'--stop-address={high}',str(Path(path).resolve())],text=True))
        if lines.keys() & parsed.keys(): raise ValueError('duplicate GNU PC')
        lines.update(parsed)
    branches=verify_disassembly(data,lines,BLOCKS,SELECTED)
    words={pc:row[0] for pc,row in lines.items()}
    for offset,value in STRINGS.items():
        if data[offset:offset+len(value)+1]!=value+b'\0':
            raise ValueError(f'literal differs at {offset:#x}')
    packed=b''.join(struct.pack('<II',pc,row[0]) for pc,row in sorted(lines.items()))
    return dict(mode='static_lk_heap_page_pool_origin',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,
        gnu_words=len(lines),gnu_relative_targets=len(branches),selected_operand_checks=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        blocks={name:dict(start=hex(a),end_exclusive=hex(b)) for name,(a,b) in BLOCKS.items()},
        selected_instructions={hex(pc):dict(word=f'{lines[pc][0]:08x}',op=op,args=args)
                               for pc,(op,args) in sorted(SELECTED.items())},
        branches=branches,pool=pool_contract(words),bindings=heap_bindings(words),
        initialization_record=init_record(data),
        strings={hex(a):v.decode('ascii') for a,v in STRINGS.items()},
        local_graphs={k:summarize_local(data,a,a,b) for k,(a,b) in BLOCKS.items()},
        interpretation=dict(
            provider='18fd30 -> 18fef8 -> 18da28 supplies a cached remainder or one page through18d9f0 -> 18d918; then20c410 initializes the generic heap',
            growth='20c098 uses generic free-list chunks; shortage rounds requested chunk to4096 and asks18fef0 -> 18d9f0 for pages, inserts/coalesces via20bf58, retries once',
            metadata='returned user pointer has a two-u64 header at-16: original chunk pointer and charged size; aligned requests round the user pointer, not a DMA address',
            pool='nominal pool [e8c1d000,e9800000),3043 pages, external byte bitmap; no free-RAM or physical/DMA proof',
            config='147ea8 is a pure local u32 load from relativecd31c8; producer/value remain unproved',
            attributes='selected heap/page bodies do not configure page tables or DMA; mutex helpers and other callees remain conditional'),
        limits=['Nominal link delta is assumed, not a measured translation or hardware address.',
                'Selected startup order depends on dispatcher eligibility, preservation and normal helper returns.',
                'Other writers, page users, bitmap state, ownership, cache attributes and DMA identity remain unproved.',
                'Arithmetic model is synthetic, includes A64 wrap and does not simulate allocation or prove extent safety.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot',type=Path)
    args=parser.parse_args()
    try: print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'inspect_lk_heap: {exc}\n')


if __name__=='__main__': main()
