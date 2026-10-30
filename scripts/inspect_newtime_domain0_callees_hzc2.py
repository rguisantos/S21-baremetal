#!/usr/bin/env python3
"""Hash-bound domain0 callback leaves, index truncation and nominal DMC17 route."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal, thumb_target
from inspect_el2_hzc2 import IMAGES, read_exact

RANGES=((0x599ec,0x59a00),(0x59e34,0x59e62),(0x5a004,0x5a044),
        (0x5a2b8,0x5a512),(0x5acec,0x5ad28),(0x5822c,0x58244),
        (0x5faac,0x5fada),(0x60198,0x601a8),(0x65124,0x65164),
        (0x647ac,0x647c8),(0x648b0,0x648c0))
SELECTED={
 0x599ee:('bl','0x59e34'),0x599f2:('bl','0x5a004'),
 0x599f6:('movs','r0, #2'),0x599f8:('bl','0x5a2b8'),
 0x59e60:('bx','lr'),0x5a022:('ldr','r0, [r1, #0]'),
 0x5a038:('ands','r3, r1'),0x5a040:('str','r3, [r2, #0]'),
 0x5a042:('bx','lr'),0x5a2ce:('ldr','r5, [r3, #12]'),
 0x5a2d4:('ldrh','r4, [r5, #22]'),0x5a2ec:('cbnz','r0, 0x5a300'),
 0x5a302:('ldr','r3, [r1, #32]'),0x5a306:('bl','0x5acec'),
 0x5a30a:('uxtb','r3, r0'),0x5a314:('muls','r4, r0'),
 0x5a328:('ldrb','r2, [r4, #2]'),0x5a32c:('str','r2, [r3, #0]'),
 0x5a332:('str','r2, [r3, #0]'),0x5a35a:('sdiv','r3, r3, r2'),
 0x5a3a8:('beq.n','0x5a432'),0x5a43c:('bl','0x5822c'),
 0x5a488:('ldr','r3, [r1, #0]'),0x5a48c:('bne.n','0x5a488'),
 0x5acf0:('ldrb','r4, [r3, #1]'),0x5acf8:('cbz','r4, 0x5ad22'),
 0x5ad0c:('ldmia','r1!, {r3}'),0x5ad22:('subs','r2, r4, #1'),
 0x58230:('str','r0, [sp, #0]'),0x58232:('str','r1, [sp, #4]'),
 0x58234:('movs','r3, #17'),0x5823a:('movs','r0, #9'),
 0x5823c:('bl','0x58170'),0x5facc:('bl','0x60198'),
 0x5fad0:('ldr','r3, [r7, #8]'),0x6019c:('ldr','r3, [r4, #96]'),
 0x601a0:('blx','r3'),0x601a2:('ldr','r3, [r4, #0]'),
 0x601a4:('blx','r3'),0x65150:('str','r3, [r2, r4]'),
 0x6515a:('ldr','r1, [r3, #124]'),0x65160:('str','r1, [r2, r3]'),
 0x647ba:('str','r0, [sp, #20]'),0x647bc:('movs','r4, r1'),
 0x648be:('str','r5, [r3, r1]')}


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
         str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    rows={};literals={};covered=set();relative=0
    for lo,hi in RANGES:
        part=parse_thumb(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',
            f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True))
        if rows.keys()&part.keys():raise ValueError('overlapping ranges')
        rows.update(part)
    for pc,(raw,op,args) in rows.items():
        if raw!=data[pc:pc+len(raw)] or op.startswith('.') or op=='udf':raise ValueError('GNU byte mismatch')
        covered.update(range(pc,pc+len(raw),2));target=thumb_target(data,pc)
        if target is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=target:raise ValueError('branch mismatch')
            relative+=1
        if op=='ldr' and '[pc,' in args:
            at,value=thumb_literal(data,pc,int(args.split(',')[0][1:]))
            if f'(0x{at:x})' not in args:raise ValueError('literal mismatch')
            literals[at]=value
    if covered!={pc for lo,hi in RANGES for pc in range(lo,hi,2)}:raise ValueError('coverage mismatch')
    for pc,expected in SELECTED.items():
        _,op,args=rows[pc]
        if (op,args.split('@')[0].strip())!=expected:raise ValueError(f'operand mismatch {pc:#x}')
    anchors={0x5a514:0x2f44c,0x5a518:0x2fbf4,0x5a520:0x2fdd4,0x5a524:0x2fdd8,
        0x5a064:0x0effffff,0x65514:0x322ad,0x601a8:0x38038,
        0x65898:0x36fad,0x658f8:0x37925,0x65164:0x381c8,0x65168:0x37e0c,0x6516c:0x37df8}
    if any(struct.unpack_from('<I',data,a)[0]!=v for a,v in anchors.items()):raise ValueError('anchor mismatch')
    return dict(source_base='3d3eeaac2dd86edf452762aef17105657942fb36',sboot_sha256=IMAGES['sboot'][1],
        scope='two complete local leaves, selected third-callee slices, DMC17 dispatch and final write helper',
        first_leaf=dict(entry='0x59e34',constant_stores=[['0xaa031800',2],['0xaa331830',4],['0xaa331034',2]],
            rmw=[['0xaa030600','old|0x10'],['0xaa030840','old|1'],['0xaa030844','old|1']],
            calls=False,polls=False,return_r0='unchanged input; no status encoded'),
        second_leaf=dict(entry='0x5a004',constant_stores=[['0xaa3318d4',1],['0xaa3310dc',1],
            ['0xa0021804',2],['0xa0021000',0],['0xa0021800',7]],
            rmw=[['0xa0020600','old|0x10'],['0xa0020850','old|1'],['0xa0020800','(old&0x0effffff)|0xf0000000']],
            calls=False,polls=False,return_r0='old M32[0xa0020600] read at0x5a022; not a success code'),
        selection=dict(entry='0x5a2b8',callback_mode=2,domain='core0x2f44c entry0',
            captured_header='H=M32[core0x2f458]',base='B=M32[core0x2fbf4]',
            row_base='u32(B+M16[H+22])',row_width='M8[H+2]',
            nonzero_mode='lookup(M32[entry0+32]>>8,entry0); k=return&255',
            row='u32(row_base+row_width*k)',zero_mode='uses header+8 as index instead of lookup',
            lookup='0x5acec: first index with low24(level)<=value; last index if none; count0 returns0xffffffff',
            error_guard_before_row_read=False,empty_count_index=255,
            early_stores='read row+2 and row+5, then store to core0x2fdd4/0x2fdd8',
            caveat='no live count, table extent or physical out-of-bounds occurrence established'),
        dmc17=dict(selected_call='0x5a43c ->0x5822c(header_byte8,k)',
            wrapper='frame words0/1 preserve full arguments; plugin9/subcommand17/R2=0 ->relay0x58170',
            nominal_handler='core table0x37cd0[17]=0x322ad ->file0x5faac, under existing relay/method12 gates',
            handler='loads full frame words0/1 ->0x60198; returns0 regardless of callee return if it returns',
            methods='0x60198 calls core0x38038+96 ->0x647ac, then reloads +192 ->0x65124 without testing first return',
            loader_arguments='R0=header_byte8, R1=k; loader captures R0 in frame+20 and R1 in R4',
            loader_cache='previously audited store0x648be installs base from descriptor14',
            second_method_reloaded=True,full_loader_executed_in_host=False,
            original_call_return='no local return-value guard at0x5a440; subsequent memory/branches remain conditional'),
        final_helper=dict(entry='0x65124',source_byte='M8[M32[core0x383b0]+28]',
            first='M32[u32(M32[core0x37e1c]+0xa94)]=(M32[u32(M32[core0x37e0c]+0xa94)]&0xfffffff0)|(source_byte&15)',
            second='M32[u32(M32[core0x37e08]+0x504)]=M32[u32(M32[core0x38268]+128)]',
            roots_reloaded_in_order=True,return_r0='core0x38268; not a success code',physical_register_roles='unassigned'),
        limits=['no live descriptors, MMIO responses, physical aliases, ordering or firmware execution',
            'third-callee body is statically covered; host tests stop before SDIV and selected opaque calls',
            'selected poll0x5a488 repeats while bit16 set, with no local timeout; no physical completion claim',
            'DMC17 is a nominal route; relay gates, bindings, loader returns and preservation remain conditions',
            'no claim of global absence of DMC8/9 or other callees'],
        unresolved=['producer of0xabcd1234','full third-callee/loader effects','init9 versus mask order','slot47/X0'],
        anchors={hex(a):v for a,v in anchors.items()},literals={hex(a):v for a,v in sorted(literals.items())},
        witnesses=[dict(pc=hex(pc),bytes=raw.hex(),op=op,args=args) for pc,(raw,op,args) in sorted(rows.items())],
        gnu=dict(instructions=len(rows),halfwords=len(covered),relative_targets=relative,literals=len(literals),selected_operands=len(SELECTED)),
        firmware_executed=False,slot47_resolved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');p.add_argument('--json',required=True);a=p.parse_args()
    try:result=inspect(a.sboot)
    except (OSError,ValueError,subprocess.CalledProcessError) as error:p.exit(2,str(error)+'\n')
    Path(a.json).write_text(json.dumps(result,indent=1)+'\n');print(json.dumps(result['gnu']))


if __name__=='__main__':main()
