#!/usr/bin/env python3
"""Bounded slot47 audit: distinguish table bases; never executes firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_consumers_hzc2 import branch_candidates, occurrences

RANGES=((0x2475c,0x24790),(0x24aa4,0x24aec),(0x24b78,0x24bac),
        (0x24fdc,0x25024),(0x2d364,0x2d3bc))


def load_offsets(word):
    """Only unsigned-offset LDR X and signed-offset LDP X without writeback."""
    if type(word) is not int or not 0<=word<=0xffffffff:raise ValueError('expected u32 instruction')
    if word & 0xffc00000 == 0xf9400000:
        return [((word>>10)&4095)*8]
    if word & 0xffc00000 == 0xa9400000:
        imm=(word>>15)&127
        if imm&64:imm-=128
        return [imm*8,imm*8+8]
    return []


def inspect(path):
    data=read_exact(path,*IMAGES['sboot'])
    first,last=0x16000,0x2fd00
    candidates=[]
    for pc in range(first,last,4):
        word=struct.unpack_from('<I',data,pc)[0]
        if 376 in load_offsets(word):candidates.append(pc)
    if candidates != [0x24784,0x24adc,0x24ba0,0x2501c]:raise ValueError('candidate inventory changed')
    root=Path(__file__).resolve().parent.parent
    command=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
             str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for a,b in RANGES:
        lines.update(parse_lines(subprocess.check_output(command+['-D','-b','binary','-m','aarch64',
            f'--start-address={a}',f'--stop-address={b}',str(Path(path).resolve())],text=True)))
    if set(lines)!={pc for a,b in RANGES for pc in range(a,b,4)}:raise ValueError('GNU coverage differs')
    relative=0
    for pc,(word,op,args) in lines.items():
        if word!=struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):raise ValueError('GNU word differs')
        kind,target=flow(word,pc)
        if kind in ('b','bl','conditional'):
            if target!=direct_target(op,args):raise ValueError('GNU target differs')
            relative+=1
    selected={0x24760:('adrp','x20, 0x30000'),0x24780:('add','x0, x20, #0xfe8'),
        0x24784:('ldr','x2, [x0, #376]'),0x24788:('mov','w0, #0x4'),0x2478c:('blr','x2'),
        0x24ab0:('add','x20, x20, #0xfe8'),0x24adc:('ldr','x2, [x20, #376]'),
        0x24ae4:('mov','w0, #0x4'),0x24ae8:('blr','x2'),
        0x24b7c:('adrp','x20, 0x30000'),0x24b9c:('add','x0, x20, #0xfe8'),
        0x24ba0:('ldr','x2, [x0, #376]'),0x24ba4:('mov','w0, #0x4'),0x24ba8:('blr','x2'),
        0x24fe8:('add','x20, x20, #0xfe8'),0x25018:('mov','w0, #0x4'),
        0x2501c:('ldr','x2, [x20, #376]'),0x25020:('blr','x2'),
        0x2d378:('ldr','x1, [x1]'),0x2d390:('cbz','x0, 0x2d398'),
        0x2d394:('str','x0, [x2, #784]'),0x2d398:('adrp','x0, 0x31000')}
    for pc,operand in selected.items():
        if lines[pc][1:]!=operand:raise ValueError(f'operand differs at{pc:#x}')
    cells={a:struct.unpack_from('<Q',data,a)[0] for a in (0x31160,0x31580,0x31998)}
    if cells!={0x31160:0x02116300,0x31580:0x02117364,0x31998:0}:raise ValueError('initial cells differ')
    packed=b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    incoming=[dict(target=hex(t),candidates=branch_candidates(data,t)) for t in range(0x2d364,0x2d3bc,4)]
    return dict(mode='static_newtime_slot47_audit',sboot_sha256=IMAGES['sboot'][1],
        scan=dict(first=hex(first),end_exclusive=hex(last),alignment=4,words=(last-first)//4,
            accepted_encodings='LDR X unsigned immediate; LDP X signed immediate without writeback',
            tested_displacement=376,candidate_PCs=[hex(pc) for pc in candidates],
            LDP_candidates=[hex(pc) for pc in candidates if len(load_offsets(struct.unpack_from('<I',data,pc)[0]))==2]),
        tables=[dict(base=hex(base),index=47,cell=hex(base+376),raw=hex(cells[base+376]),
                     nominal_target=hex(cells[base+376]-0x020ea000)) for base in (0x30fe8,0x31408)],
        candidate_calls=[dict(load=hex(pc),call=hex(call),X0=4,
            base_under_selected_path='0x30fe8',cell='0x31160',nominal_target='0x2c300',
            base_preservation_is_condition=True) for pc,call in zip(candidates,(0x2478c,0x24ae8,0x24ba8,0x25020))],
        incoming_B_BL_scan=incoming,
        nominal_pointer_occurrences=[hex(x) for x in occurrences(data,struct.pack('<Q',0x02117364))],
        writer_2d394=dict(source='incoming X0, not recovered',zero='skip only binding store; retain old cell',
            nonzero='replace 0x31998 with incoming X0',
            AP02073600_read='0x2d378, before the zero test; no runtime value supplied',
            other_effects_are_not_skipped_by_zero=True),
        gnu_words=len(lines),gnu_relative_targets=relative,selected_operands=len(selected),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        witnesses=[dict(pc=hex(pc),word=f'{w:08x}',op=op,args=args) for pc,(w,op,args) in sorted(lines.items())],
        limits=['bounded encoding inventory, not complete address/alias analysis',
                'four candidates are not calls to 0x2d364 under their selected bases',
                'no indirect caller of actual cell 0x31580 resolved',
                'register-indexed, literal, pre/post-indexed loads, copies and other images not excluded',
                'preservation of cell/table/ABI and actual execution not observed'],
        incoming_X0_resolved=False,firmware_executed=False,qemu_scope_extended=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:result=inspect(args.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:parser.exit(2,f'{exc}\n')
    print(json.dumps(result,indent=2))
