#!/usr/bin/env python3
"""Bounded static witnesses for NEWTIME pointer reloads; requires GNU, no execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_consumers_hzc2 import occurrences, branch_candidates
from inspect_newtime_hzc2 import embedded

RANGES = ((0x1dcb4,0x1dccc),(0x28808,0x28a6c),(0x2cdb8,0x2ce88),
          (0x2d270,0x2d2cc),(0x2d364,0x2d3bc),(0x2d6d0,0x2d798),
          (0x2e4b4,0x2e4fc))


def inspect(path):
    data = read_exact(path,*IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for start,end in RANGES:
        lines.update(parse_lines(subprocess.check_output(command + ['-D','-b','binary','-m','aarch64',
            f'--start-address={start}',f'--stop-address={end}',str(Path(path).resolve())],text=True)))
    if set(lines) != {pc for a,b in RANGES for pc in range(a,b,4)}:
        raise ValueError('GNU coverage mismatch')
    branches = 0
    for pc,(raw,op,args) in lines.items():
        if raw != struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):
            raise ValueError(f'invalid witness at {pc:#x}')
        kind,target=flow(raw,pc)
        if kind in ('b','bl','conditional'):
            if target != direct_target(op,args): raise ValueError('relative target differs')
            branches += 1
    def expect(pc,op,args):
        if lines[pc][1:] != (op,args): raise ValueError(f'operand changed at {pc:#x}')
    # Fourteen u32 calls, each reloading both the payload and dispatch object.
    events=[]
    for index,tag in enumerate((0x100,0x101,0x104,0x105,0x106,0x107,0x10a,0x10b,
                                0x10c,0x10d,0x10e,0x10f,0x110,0x111)):
        load=0x28820 if index==0 else 0x2883c+(index-1)*40
        read=load+4 if index==0 else load+16
        dispatch=load+8 if index==0 else load+20
        method=load+16 if index==0 else load+28
        call=load+24 if index==0 else load+36
        expect(load,'ldr','x0, [x19, #208]')
        expect(read,'ldr',f'w2, [x0{", #"+str(index*4) if index else ""}]')
        expect(dispatch,'ldr','x0, [x19, #784]')
        expect(method,'ldr','x4, [x0, #72]')
        expect(call,'blr','x4')
        tag_pc=0x28810 if index==0 else load+4
        expect(tag_pc,'mov',f'x1, #{hex(tag)}')
        expect(0x2881c if index==0 else load+12,'movk','x1, #0x468d, lsl #16')
        events.append(dict(payload_pointer_load=hex(load),payload_read=hex(read),
            byte_offset=index*4,width=4,extension='zero',tag=hex(0x468d0000+tag),call=hex(call)))
    expect(0x28a44,'ldr','x0, [x19, #208]')
    expect(0x28a4c,'ldr','x1, [x19, #784]')
    expect(0x28a54,'ldrsw','x2, [x0, #56]')
    expect(0x28a5c,'ldr','x4, [x1, #72]')
    expect(0x28a68,'br','x4')
    expect(0x28a60,'mov','x1, #0x12d')
    expect(0x28a64,'movk','x1, #0x468d, lsl #16')
    events.append(dict(payload_pointer_load='0x28a44',payload_read='0x28a54',byte_offset=56,
        width=4,extension='signed',tag='0x468d012d',tail_branch='0x28a68'))
    tables={t['key']:t for t in embedded(data)['parsed']['entries']}
    payloads=[]
    for key in (0x12b,0x11b):
        t=tables[key]
        if len(t['cells'])!=15: raise ValueError('column1 payload size changed')
        vals=[]
        for event,value in zip(events,t['cells']):
            vals.append(dict(tag=event['tag'],u32=hex(value),
                supplied_X2=value-(1<<32) if event['extension']=='signed' and value>>31 else value))
        payloads.append(dict(key=hex(key),bytes=60,values=vals))
    # Initial cells only: never substitute these for observed runtime bindings.
    cells={hex(a):hex(struct.unpack_from('<Q',data,a)[0]) for a in
           (0x31998,0x30ec0,0x30f18,0x30f20,0x314c8,0x314d8)}
    packed=b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    return dict(mode='static_newtime_reloads',sboot_sha256=IMAGES['sboot'][1],
        ranges=[dict(first=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest()) for a,b in RANGES],
        gnu_words=len(lines),gnu_relative_targets=branches,instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions=[dict(pc=hex(pc),word=f'{w:08x}',op=op,args=args) for pc,(w,op,args) in sorted(lines.items())],
        initial_cells=cells,column1_other_reader=dict(entry='0x28808',nominal_slot=14,table='0x30e50',
            dispatch_pointer='0x31998',method_offset=72,events=events,supplied_payloads=payloads,
            direct_BL_B_candidates=branch_candidates(data,0x28808),
            nominal_pointer_occurrences=[hex(x) for x in occurrences(data,struct.pack('<Q',0x02112808))]),
        AP0207365c_literal_occurrences={str(width):[hex(x) for x in occurrences(data,(0x0207365c).to_bytes(width,'little'))] for width in (4,8)},
        limits=['bounded witnesses, not exhaustive alias/store inventory',
                'no AP0207365c reader established; literal absence does not exclude computed/aliased reads',
                'payload/dispatch reloaded between calls; preservation and method target unproven',
                'initial function slots do not prove runtime targets',
                'register base table 0x30f98 can be rewritten in 0x2d270 conditional path'],
        firmware_executed=False,qemu_scope_extended=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try: result=inspect(args.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc: parser.exit(2,f'{exc}\n')
    print(json.dumps(result,indent=2))
