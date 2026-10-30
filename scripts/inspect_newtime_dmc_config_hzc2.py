#!/usr/bin/env python3
"""Hash-bound DMC command20/config writer and h/g2 cache provenance."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal, thumb_target
from inspect_el2_hzc2 import IMAGES, read_exact

U32=0xffffffff
BASE=0x3a600
DIRECTORY=0x3a7a0
CACHE=0x381c8+0x23c
RANGES=((0x5ff14,0x5fff4),(0x5fd38,0x5fd82),(0x60148,0x60156),
        (0x64c68,0x64c9e),(0x64658,0x64674),(0x6467c,0x64698),
        (0x647ac,0x64956),(0x5f758,0x5f79c))
SELECTED={
 0x5ff26:('ldr','r3, [r7, #4]'),0x5ff28:('ldr','r3, [r3, #0]'),
 0x5ff32:('lsrs','r3, r3, #16'),0x5ff3a:('cbnz','r3, 0x5ff54'),
 0x5ff40:('lsls','r2, r2, #2'),0x5ff42:('ldr','r3, [r2, r3]'),
 0x5ff46:('movs','r1, r2'),0x5ff48:('movs','r0, #0'),0x5ff4a:('blx','r3'),
 0x5fd4c:('ldrb','r3, [r3, #7]'),0x5fd52:('ldrb','r3, [r3, #6]'),
 0x5fd58:('ldrb','r3, [r3, #5]'),0x5fd5e:('ldrb','r3, [r3, #4]'),
 0x5fd64:('ldr','r3, [r3, #8]'),0x5fd66:('str','r3, [sp, #0]'),
 0x5fd6a:('bl','0x60148'),0x5fd72:('str','r2, [r3, #12]'),
 0x6014a:('ldr','r4, [sp, #16]'),0x6014c:('str','r4, [sp, #0]'),
 0x60150:('ldr','r4, [r4, #104]'),0x60152:('blx','r4'),
 0x64c6c:('lsls','r0, r0, #4'),0x64c72:('ldr','r4, [r0, #4]'),
 0x64c74:('adds','r4, r4, r5'),0x64c78:('cmp','r3, #1'),
 0x64c7c:('movs','r5, #12'),0x64c7e:('movs','r2, #0'),
 0x64c84:('cmp','r2, r5'),0x64c86:('bgt.n','0x64c9a'),
 0x64c88:('ldr','r3, [r0, #8]'),0x64c8a:('ldr','r6, [sp, #16]'),
 0x64c8c:('muls','r3, r2'),0x64c8e:('lsls','r3, r3, #2'),
 0x64c94:('str','r6, [r3, #0]'),0x64c98:('b.n','0x64c84'),
 0x64c9a:('ldr','r0, [r3, #0]'),
 0x648b0:('ldr','r5, [pc, #244]'),0x648b4:('ldr','r5, [r5, #4]'),
 0x648b6:('adds','r5, r5, r1'),0x648be:('str','r5, [r3, r1]'),
 0x64660:('cbnz','r1, 0x64668'),0x64666:('str','r1, [r2, r3]'),
 0x6466a:('adds','r0, #18'),0x64670:('ldr','r0, [r0, #4]'),
 0x64684:('cbnz','r1, 0x6468c'),0x6468a:('str','r1, [r2, r3]'),
 0x6468e:('adds','r0, #31'),0x64694:('ldr','r0, [r0, #4]'),
}
ANCHORS={0x65440:0x32715,0x6544c:0x31f59,0x65520:0x32539,
 0x658a0:0x37469,0x60158:0x38038,0x649a8:0x3a880,
 0x6495c:BASE,0x64ca0:DIRECTORY,0x64674:0x381c8,0x64678:0x3a664}


def uint(v):
    if type(v) is not int or not 0<=v<=U32:raise ValueError('expected u32')
    return v


def target(offset,stride,column,row):
    for v in (offset,stride,column,row):uint(v)
    return (BASE+offset+4*((stride*row+column)&U32))&U32


def packet_fields(packet):
    if len(packet)!=16:raise ValueError('expected 16 bytes')
    return dict(command=struct.unpack_from('<I',packet)[0]&65535,
                descriptor=packet[7],column=packet[6],row=packet[5],mode=packet[4],
                value=struct.unpack_from('<I',packet,8)[0])


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    rows={};covered=set();literals={};relative=0
    for lo,hi in RANGES:
        out=subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True)
        part=parse_thumb(out)
        if rows.keys()&part.keys():raise ValueError('overlap')
        rows.update(part)
    for pc,(raw,op,args) in rows.items():
        if raw!=data[pc:pc+len(raw)] or op.startswith('.') or op=='udf':raise ValueError('GNU byte mismatch')
        covered.update(range(pc,pc+len(raw),2))
        to=thumb_target(data,pc)
        if to is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=to:raise ValueError('branch mismatch')
            relative+=1
        if op=='ldr' and '[pc,' in args:
            at,v=thumb_literal(data,pc,int(args.split(',')[0][1:]))
            if f'(0x{at:x})' not in args:raise ValueError('literal mismatch')
            literals[at]=v
    if covered!={p for lo,hi in RANGES for p in range(lo,hi,2)}:raise ValueError('coverage mismatch')
    for pc,expect in SELECTED.items():
        _,op,args=rows[pc]
        if (op,args.split('@')[0].strip())!=expect:raise ValueError(f'operand mismatch {pc:#x}: {(op,args)}')
    word=lambda at:struct.unpack_from('<I',data,at)[0]
    if any(word(at)!=v for at,v in ANCHORS.items()):raise ValueError('anchor mismatch')
    return dict(scope='static DMC command20 writer and cache origins',source_base='60f291a84aadc319f4aaad192100ffe72a4f6f16',
        sboot_sha256=IMAGES['sboot'][1],
        route=dict(normal_method0='0x5ff14: packet=M32[r0slot]; command=u16(M32[packet]); gate M32[core0x37d3c]==0',
            command20='M32[core0x37cd0+20*4]=core0x32539 -> file0x5fd38; arguments r0=0,r1=packet',
            handler='bytes7/6/5/4 -> descriptor/column/row/mode; word8 -> value; BL0x5fd6a -> 0x60148',
            wrapper='0x60148 forwards fifth stack argument, BLX M32[core0x38038+104] -> core0x37469 -> file0x64c68',
            effect='0x5fd72 writes helper return to packet+12; 0x5fd74 calls 0x5f8dc (opaque in this delivery)',
            method12='same command table permits command20 under its own gates/arguments; DVFS8/9 do not supply command20'),
        writer=dict(pc='0x64c94',descriptor='D=u32(0x3a7a0+16*descriptor)',
            base='B=u32(0x3a600+M32[D+4]) captured once',
            formula='u32(B+u32(4*u32(M32[D+8]*row+column)))',
            rows='mode==1 -> row0..12 inclusive; otherwise start=end=input row; compare signed; increment u32',
            stride='M32[D+8] reloaded each iteration; aliases can change subsequent destinations',
            value='M32[entry_SP] reloaded every iteration (fifth argument); stack aliases also remain relevant',
            return_value='M32[last_written_address] before returning; packet+12 receives it',
            limits='selected helper has no descriptor/column/memory bounds check; packet fields are bytes',
            alias_conditions=[dict(core=hex(BASE+x),condition=f'u32(offset+4*u32(stride*row+column))=={x:#x}') for x in (0x60,0x64,0x68)],
            runtime_write_observed=False),
        cache=dict(core=hex(CACHE),loader='0x648be: M32[CACHE]=u32(0x3a600+M32[core0x3a884])',
            lazy_h='0x64660/0x64666: only when cache==0, copy M32[core0x3a664] into CACHE',
            lazy_g2='0x64684/0x6468a: same cache and fallback',
            lookup='h: M32[u32(cache+u32((input+18)*8)+4)]; g2 uses +31',
            initialization='nonzero cache installed by loader bypasses header fallback; order/preservation conditional'),
        frontiers=['directory core0x3a7a0 and header core0x3a600 lie outside second copy; their live values/producers remain open',
            'a concrete store routine is identified, but actual alias to masks/base requires live descriptor offset/stride and path evidence',
            'other stores/callees, receive provenance, permissions and physical effects are not excluded',
            'slot47/X0 remains open; no device execution or extended QEMU'],
        anchors={hex(a):v for a,v in ANCHORS.items()},literals={hex(a):v for a,v in sorted(literals.items())},
        witnesses=[dict(pc=hex(pc),bytes=raw.hex(),op=op,args=args) for pc,(raw,op,args) in sorted(rows.items())],
        gnu=dict(instructions=len(rows),halfwords=len(covered),relative_targets=relative,literals=len(literals),selected_operands=len(SELECTED)),
        firmware_executed=False,slot47_resolved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');p.add_argument('--json',required=True);a=p.parse_args()
    try:r=inspect(a.sboot)
    except (OSError,ValueError,subprocess.CalledProcessError) as e:p.exit(2,str(e)+'\n')
    Path(a.json).write_text(json.dumps(r,indent=1)+'\n');print(json.dumps(r['gnu']))

if __name__=='__main__':main()
