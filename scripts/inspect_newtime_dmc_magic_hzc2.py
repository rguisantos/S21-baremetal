#!/usr/bin/env python3
"""Verify a local producer of DVFS magic; establish no global-writer uniqueness."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_acpm_handshake_hzc2 import thumb_wide
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_avb_boot import wide_constant
from inspect_lk_precopy_measurement import verify_disassembly
from inspect_newtime_fast_channel_hzc2 import inspect as fast_inspect

MAGIC=0xabcd1234
SIGNAL=0x1590010c
LOCAL_SIGNAL=0xa590010c
BLOCKS = {
    'entry': (0x36000, 0x3608c),
    'entry_pmu_helpers': (0x3608c, 0x3610c),
    'smc_veneer': (0x36138, 0x36140),
    'continuation': (0x3624c, 0x36264),
    'clock_wrapper': (0x36934, 0x36974),
    'magic_publisher': (0x36974, 0x369c8),
}
SELECTED = {
    0x36008: ('mrs', 'x1, currentel'),
    0x36010: ('b.eq', '0x36030'),
    0x36018: ('b.eq', '0x36038'),
    0x3601c: ('msr', 'vbar_el3, x0'),
    0x36030: ('msr', 'vbar_el2, x0'),
    0x36038: ('msr', 'vbar_el1, x0'),
    0x36054: ('ldr', 'x0, 0x36110'),
    0x36058: ('ldr', 'w1, [x0]'),
    0x3605c: ('ldr', 'w2, 0x3610c'),
    0x36060: ('cmp', 'w1, w2'),
    0x3606c: ('ldr', 'x0, 0x36118'),
    0x36074: ('ldr', 'x0, 0x36120'),
    0x36078: ('and', 'sp, x0, #0xfffffffffffffff0'),
    0x36080: ('bl', '0x360f8'),
    0x36084: ('bl', '0x36974'),
    0x36088: ('b', '0x3624c'),
    0x36138: ('smc', '#0x0'),
    0x3624c: ('mov', 'x3, #0xf000'),
    0x36250: ('mov', 'x2, #0x0'),
    0x36254: ('movk', 'x3, #0xbfff, lsl #16'),
    0x36258: ('mov', 'x1, #0x0'),
    0x3625c: ('mov', 'x0, #0xffffffffffffff18'),
    0x36260: ('b', '0x36138'),
    0x3693c: ('bl', '0x3633c'),
    0x36940: ('bl', '0x36668'),
    0x36944: ('bl', '0x3671c'),
    0x36948: ('bl', '0x3678c'),
    0x3694c: ('bl', '0x36824'),
    0x36950: ('bl', '0x368c0'),
    0x36954: ('adrp', 'x0, 0x36000'),
    0x36958: ('ldrb', 'w0, [x0, #2616]'),
    0x36960: ('b.hi', '0x3696c'),
    0x36968: ('b', '0x366d0'),
    0x36974: ('stp', 'x29, x30, [sp, #-32]!'),
    0x36978: ('mov', 'x0, #0x3b50'),
    0x3697c: ('mov', 'w1, #0x1234'),
    0x36980: ('movk', 'x0, #0x1586, lsl #16'),
    0x36984: ('mov', 'x29, sp'),
    0x36988: ('movk', 'w1, #0xabcd, lsl #16'),
    0x3698c: ('mov', 'w2, #0x80000'),
    0x36990: ('ldr', 'w0, [x0]'),
    0x36994: ('str', 'w0, [x29, #28]'),
    0x36998: ('mov', 'x0, #0x10c'),
    0x3699c: ('movk', 'x0, #0x1590, lsl #16'),
    0x369a0: ('str', 'w1, [x0]'),
    0x369a4: ('mov', 'x1, #0x8'),
    0x369a8: ('movk', 'x1, #0x1590, lsl #16'),
    0x369ac: ('str', 'w2, [x1]'),
    0x369b0: ('ldr', 'w1, [x0]'),
    0x369b4: ('cbnz', 'w1, 0x369b0'),
    0x369b8: ('ldr', 'w0, [x29, #28]'),
    0x369bc: ('bl', '0x36934'),
    0x369c0: ('ldp', 'x29, x30, [sp], #32'),
    0x369c4: ('ret', ''),
}
LITERALS={0x3610c:(4,0xbad),0x36110:(8,0x15860804),
    0x36118:(8,0x02039000),0x36120:(8,0x0225a000)}


def census(data):
    literal=[];at=0;needle=struct.pack('<I',MAGIC)
    while True:
        at=data.find(needle,at)
        if at<0:break
        literal.append(hex(at));at+=1
    movk=[]
    for pc in range(0,len(data)-3,4):
        w=struct.unpack_from('<I',data,pc)[0]
        if w & 0x7f800000==0x72800000 and (w >> 5) & 65535==0xabcd:
            movk.append(dict(pc=hex(pc),word=f'{w:08x}',register=w & 31,shift=((w >> 21)&3)*16))
    thumb=[]
    for pc in range(0x38000,min(len(data)-3,0x67000),2):
        try:reg,value=thumb_wide(data,pc)
        except ValueError:continue
        if value==0x1234:thumb.append(dict(pc=hex(pc),register=reg))
    return dict(exact_le32_magic=literal,a64_aligned_movk_abcd=movk,thumb_movw_1234=thumb,
        scope=dict(literal='all supplied bytes',a64='4-byte aligned candidate words, not recovered instruction boundaries',
            thumb='halfword candidate starts in [0x38000,0x67000), including possible data'),
        global_writer_uniqueness_proven=False,computed_copied_aliased_or_external_writers_excluded=False)


def bindings(words):
    def wide(pcs,reg,width):
        got=wide_constant([words[p] for p in pcs])
        if got[:2]!=(reg,width):raise ValueError('wide argument register/width differs')
        return got[2]
    return dict(pmu_source=hex(wide((0x36978,0x36980),0,64)),
        signal=hex(wide((0x36998,0x3699c),0,64)),magic=hex(wide((0x3697c,0x36988),1,32)),
        doorbell=hex(wide((0x369a4,0x369a8),1,64)),doorbell_value=hex(wide((0x3698c,),2,32)),
        continuation_x0=hex(wide((0x3625c,),0,64)),continuation_x3=hex(wide((0x3624c,0x36254),3,64)))


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for a,b in BLOCKS.values():
        part=parse_lines(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','aarch64',f'--start-address={a}',f'--stop-address={b}',str(Path(path).resolve())],text=True))
        if lines.keys() & part.keys():raise ValueError('overlapping GNU PCs')
        lines.update(part)
    targets=verify_disassembly(data,lines,BLOCKS,SELECTED)
    words={p:v[0] for p,v in lines.items()}
    for a,(n,value) in LITERALS.items():
        if int.from_bytes(data[a:a+n],'little')!=value:raise ValueError('entry literal differs')
    fast=fast_inspect(path)
    packed=b''.join(struct.pack('<II',p,v[0]) for p,v in sorted(lines.items()))
    return dict(mode='static_local_dmc_magic_publisher',source_base='20c472c0a03d5ad9a6f409e5f8adab1bfefb6897',
        sboot_sha256=IMAGES['sboot'][1],firmware_executed=False,hardware_observed=False,slot47_resolved=False,
        stage=dict(file_entry='0x36000',candidate_container='BL2',current_el_is_read_and_multiple_els_handled=True,
            actual_el3_entry_established=False,distinct_el3_candidate_offset='0x36c000'),
        entry=dict(call='0x36084 ->0x36974',after_return='0x36088 ->0x3624c',
            stack_selector='u32[AP0x15860804] ==0xbad ->0x02039000, otherwise0x0225a000; align16',
            prior_helpers_are_conditional=True),bindings=bindings(words),
        publisher=dict(store='0x369a0',signal=hex(SIGNAL),value=hex(MAGIC),
            saved_pmu='u32[0x15863b50] ->frame+28 before publication',
            doorbell_store='0x369ac',doorbell='0x15900008',doorbell_value='0x80000',
            polling='0x369b0 LDR W1;0x369b4 CBNZ back; exit only on low32 zero',
            firmware_timeout_present_in_selected_loop=False,
            after_zero='reload saved PMU; call0x36934; restore frame and return',
            local_writer_confirmed=True,global_unique_writer_proven=False),
        acpm=dict(channel=fast['channel'],route=fast['route'],callback=fast['callback'],
            clear='0x5a998 writes zero to local0xa590010c after selected callee returns',
            ap_local_alias_assumed_for_cross_core_interpretation=True,physical_alias_or_event_delivery_observed=False),
        continuation=dict(wrapper='0x3624c',veneer='0x36138 SMC0;RET',x0='0xffffffffffffff18',x1=0,x2=0,x3='0xbffff000',
            service_minus232_implementation_executed=False),
        census=census(data),
        gnu=dict(a64_words=len(lines),a64_relative_targets=len(targets),selected_a64_operands=len(SELECTED),entry_literals=len(LITERALS),
            inherited_thumb=fast['gnu'],instruction_index_sha256=hashlib.sha256(packed).hexdigest()),
        a64_witnesses=[dict(pc=hex(p),word=f'{w:08x}',op=op,args=args) for p,(w,op,args) in sorted(lines.items())],
        a64_literals={hex(a):dict(bytes=n,value=hex(v)) for a,(n,v) in LITERALS.items()},
        witnesses=fast['witnesses'],literals=fast['literals'],
        limits=['Local writer and selected control flow only; census is not global data-flow or an exclusion of other agents/aliases.',
                '0x36000 lies in candidate BL2 and handles EL1/EL2/EL3; do not identify it with the separate EL3 monitor container.',
                'Cross-core alias, delivery, visibility, current clocks and PMU values remain unobserved.',
                'A host-injected clear is an external-agent fixture, not execution of the whole ACPM path or SMC service.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as exc:parser.exit(2,f'inspect_newtime_dmc_magic: {exc}\n')
