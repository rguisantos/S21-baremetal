#!/usr/bin/env python3
"""Hash-bound DMC17 loader publications and control-word-driven tail."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal, thumb_target
from inspect_el2_hzc2 import IMAGES, read_exact

BASE=0x3a600;STATE=0x381c8;DIRECTORY=0x3a7a0
RANGES=((0x647ac,0x64956),(0x60c6c,0x60c6e),(0x64a64,0x64c4e),
        (0x60198,0x601a8),(0x65124,0x65164))
SELECTED={0x647be:('cmp','r3, r2'),0x647c0:('ble.n','0x647c8'),
 0x647c4:('bl','0x60c6c'),0x60c6c:('bx','lr'),
 0x647f6:('lsls','r2, r2, #1'),0x647f8:('lsrs','r2, r2, #17'),
 0x647fa:('asrs','r2, r4'),0x64816:('cmp','r4, #5'),
 0x64818:('ble.n','0x64858'),0x6481e:('uxth','r2, r2'),
 0x64820:('asrs','r2, r4'),0x6483a:('subs','r4, #6'),
 0x6489c:('ldr','r1, [r5, #0]'),0x648ae:('str','r5, [r1, #36]'),
 0x648be:('str','r5, [r3, r1]'),0x64906:('ldr','r0, [sp, #20]'),
 0x6490a:('muls','r0, r1'),0x6490c:('muls','r1, r4'),
 0x6491a:('str','r2, [r3, r1]'),0x6491e:('str','r0, [r3, r5]'),
 0x64936:('str','r0, [r2, #0]'),0x64938:('str','r1, [r2, #4]'),
 0x6494c:('bl','0x64a64'),0x64950:('movs','r0, #0'),
 0x64a68:('ldr','r3, [r0, #0]'),0x64a6c:('bpl.n','0x64aa8'),
 0x64a82:('strb','r3, [r2, #11]'),0x64b00:('strh','r3, [r4, #12]'),
 0x64b68:('blx','r3'),0x64b7c:('blx','r3'),
 0x64c4a:('movs','r0, #0'),0x601a0:('blx','r3'),0x601a4:('blx','r3')}


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    rows={};literals={};covered=set();relative=0
    for lo,hi in RANGES:
        part=parse_thumb(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',
            f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True))
        if rows.keys()&part.keys():raise ValueError('overlapping ranges')
        rows.update(part)
    for pc,(raw,op,args) in rows.items():
        if raw!=data[pc:pc+len(raw)] or op.startswith('.') or op=='udf':raise ValueError('GNU byte mismatch')
        covered.update(range(pc,pc+len(raw),2));to=thumb_target(data,pc)
        if to is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=to:raise ValueError('branch mismatch')
            relative+=1
        if op=='ldr' and '[pc,' in args:
            at,value=thumb_literal(data,pc,int(args.split(',')[0][1:]))
            if f'(0x{at:x})' not in args:raise ValueError('literal mismatch')
            literals[at]=value
    if covered!={pc for lo,hi in RANGES for pc in range(lo,hi,2)}:raise ValueError('coverage mismatch')
    for pc,wanted in SELECTED.items():
        _,op,args=rows[pc]
        if (op,args.split('@')[0].strip())!=wanted:raise ValueError(f'operand mismatch {pc:#x}')
    anchors={0x64958:BASE+16,0x6495c:BASE,0x64960:0x3c9ff,0x64968:STATE,
        0x64978:0xa58609bc,0x6497c:0x3a658,0x64980:0x3a654,
        0x64c50:0xa58609a8,0x64c54:STATE,0x64c60:0xa58609ac,0x64c64:0x37fb4,
        0x657c4:0x369a5,0x657dc:0x369d1}
    if any(struct.unpack_from('<I',data,a)[0]!=v for a,v in anchors.items()):raise ValueError('anchor mismatch')
    return dict(source_base='65732506b9af16dc7e506194f93a09829cf83d27',sboot_sha256=IMAGES['sboot'][1],
        scope='complete local loader and tail bodies, opaque indirect service calls; no physical execution',
        size_test=dict(expression='s32(u32(0x3a600+M32[core0x3a610])) > s32(0x3c9ff)',
            greater='call0x60c6c(R0=4), then continue',callee='literal BX LR; no local abort',bounds_enforced=False),
        selection=dict(mask_register='0xa58609bc',second_argument='k, full u32; shift counts use low8',
            upper_flag='((mask>>16)&0x7fff) ASR low8(k), bit0 ->state+0x229 and core0x3a658',
            alternate='s32(k)>5 and ((mask&0xffff) ASR low8(k)) bit0 !=0',
            adjusted_index='j=u32(k-6) if alternate, else k',
            caller_u8='for mode2 k in0..255, alternate is possible only for6..15; k255 uses regular descriptors'),
        publications=dict(conditions='formulas assume preserved descriptor fields/nonalias fixtures; raw stores and reloads define aliases',
            offset='off_i=M32[0x3a7a0+16*i+4]; B=0x3a600; S=0x381c8',
            alternatives={'0xa4':'B+off_(1/2)+64*j','0xa8':'B+off_(9/10)+8*j',
                '0xa0':'B+off_(3/4)+4*M32[descriptor3+8]*j',
                '0x1ec':'B+off_(5/6)+4*M32[descriptor5+8]*j',
                '0x1e8':'B+off_(5/6)+4*M32[descriptor5+8]*first_argument',
                '0x8':'B+off_(7/8)+4*M8[S]*j'},
            common={'0x10':'B+off11','0x1e4':'B+off12','0x23c':'B+off14','0x204':'B+off15','0xac':'B+off0'},
            indirect='M32[M32[S+0x9c]+36]=u32(B+off13)',
            copied_header='M32[S+0x240]=M32[B]; M32[S+0x244]=M32[B+4]; M8[S+0x209]=(M32[S+0x240]>>4)&15',
            returned_state_preserved=False,reason='tail runs after publications and can mutate descriptor bytes/call opaque services'),
        tail=dict(entry='0x64a64',first_control='M32[0xa58609a8] repeatedly sampled; bits24/25/26 gate descriptor edits',
            descriptor='M32[S+0x1ec], relayed from adjusted second argument',
            second_control='M32[0xa58609ac] repeatedly sampled; bits24..28 gate service read/write sequences',
            indirect='core0x37fb4+16/+40, initially file0x641a4/0x641d0; opaque service hooks in host tests',
            service_ids=[11,41,18,17,3],return_value=0,service_errors_aggregated=False,
            loader_return='0x64950 overwrites R0 with0 if tail returns; no rollback of earlier publications'),
        conditions=['explicit readable header/directory, state roots and control-word samples',
            'calls return and preserve ABI state; no freshness/alias/physical readiness assumption',
            'first and adjusted second arguments select different published rows; no global bounds claim'],
        unresolved=['producer of0xabcd1234','rest of0x5a2b8 and indirect service effects','init9 versus masks order','slot47/X0'],
        anchors={hex(a):v for a,v in anchors.items()},literals={hex(a):v for a,v in sorted(literals.items())},
        witnesses=[dict(pc=hex(pc),bytes=raw.hex(),op=op,args=args) for pc,(raw,op,args) in sorted(rows.items())],
        gnu=dict(instructions=len(rows),halfwords=len(covered),relative_targets=relative,literals=len(literals),selected_operands=len(SELECTED)),
        firmware_executed=False,slot47_resolved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');p.add_argument('--json',required=True);a=p.parse_args()
    try:r=inspect(a.sboot)
    except (OSError,ValueError,subprocess.CalledProcessError) as e:p.exit(2,str(e)+'\n')
    Path(a.json).write_text(json.dumps(r,indent=1)+'\n');print(json.dumps(r['gnu']))


if __name__=='__main__':main()
