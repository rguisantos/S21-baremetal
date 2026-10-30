#!/usr/bin/env python3
"""Hash-bound software-table services and selected downstream MMIO publisher."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal,thumb_target
from inspect_el2_hzc2 import IMAGES,read_exact

RANGES=((0x641a4,0x641cc),(0x641d0,0x641ee),(0x63f94,0x63fac),
        (0x63fb0,0x640dc),(0x640e8,0x64126),(0x615ec,0x6163a))
SELECTED={0x641aa:('ldrb','r1, [r3, #0]'),0x641ac:('ldr','r3, [r3, #8]'),
 0x641b8:('ldrb','r5, [r5, #0]'),0x641ba:('cmp','r5, r0'),
 0x641be:('ldrb','r0, [r4, #0]'),0x641c8:('negs','r0, r0'),
 0x641d6:('ldr','r2, [r3, #8]'),0x641d8:('ldrb','r5, [r3, #0]'),
 0x641de:('ldrb','r5, [r2, #1]'),0x641e4:('strb','r1, [r2, #0]'),
 0x641ea:('b.n','0x641d8'),0x63fce:('blx','r3'),
 0x63fc4:('adcs','r1, r3'),0x63fdc:('ldrb','r3, [r5, #0]'),
 0x63fe6:('ldr','r3, [r5, #8]'),0x63fee:('beq.n','0x640d0'),
 0x64016:('blx','r4'),0x64028:('blx','r3'),0x6403e:('blx','r5'),
 0x640ba:('bl','0x63f94'),0x640c2:('ldrb','r3, [r6, #0]'),
 0x640ce:('blx','r5'),0x64120:('bl','0x63fb0'),
 0x61602:('ldr','r4, [r4, #0]'),0x61604:('ldr','r4, [r4, #0]'),
 0x61624:('ldr','r2, [r0, r2]'),0x61628:('str','r4, [r2, #0]'),
 0x6162a:('str','r1, [r2, #56]'),0x6162c:('str','r3, [r2, #8]'),
 0x61630:('str','r3, [r2, #4]'),0x61634:('movs','r0, #1'),0x61636:('negs','r0, r0')}


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    rows={};covered=set();literals={};relative=0
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
            at,v=thumb_literal(data,pc,int(args.split(',')[0][1:]))
            if f'(0x{at:x})' not in args:raise ValueError('literal mismatch')
            literals[at]=v
    if covered!={p for lo,hi in RANGES for p in range(lo,hi,2)}:raise ValueError('coverage mismatch')
    for pc,expected in SELECTED.items():
        _,op,args=rows[pc]
        if (op,args.split('@')[0].strip())!=expected:raise ValueError(f'operand mismatch {pc:#x}')
    anchors={0x641cc:0x381c8,0x641f0:0x381c8,0x640dc:0x381c8,0x640e0:0x37fb4,
        0x640e4:0x37d40,0x655a4:0x33ded,0x655a8:0x34471,
        0x657b4:0x368e9,0x657c4:0x369a5,0x657dc:0x369d1,
        0x6163c:0x37df8,0x61640:0xcfffffff,0x61644:0xf80fffff,0x63fac:0x3801c}
    if any(struct.unpack_from('<I',data,a)[0]!=v for a,v in anchors.items()):raise ValueError('anchor mismatch')
    filter_ids=list(data[0x6581c:0x6581c+15])
    return dict(source_base='296bc4af02ac921dd98f4eaaf15d6ed11cb54193',sboot_sha256=IMAGES['sboot'][1],
        scope='complete local table getter/setter, selected consumer paths and publisher; no physical execution',
        table=dict(state='core0x381c8',count='M8[state]',pointer='M32[state+8]',stride=4,
            record='byte0=value, byte1=id; bytes2/3 not used by getter/setter',
            getter='0x641a4: captures count/pointer once, returns first matching value u8 or0xffffffff',
            getter_input='full R0 compared with u8 id; no truncation of input id',
            setter='0x641d0: captures pointer once, reloads count each iteration, writes low8(R1) to every matching record',
            setter_return='unchanged R0 input id, including no-match/count0; not a success code',
            local_calls=False,local_polls=False,physical_device_write_proven=False,
            alias='setter writes can change subsequent count/id/data; captured table pointer is not reloaded'),
        consumer=dict(entry='0x63fb0',caller='0x64120 ->0x63fb0 with R0=0, inside nominal method0x640e8',
            initial_lookup='getter(id18), result captured once in frame+8 even if0xffffffff',
            loop='reload count and table pointer each iteration; records processed in order',
            id16='skip',id18='low8(captured lookup18 | (state+0x229==1 ?0x10:0)) ->publisher channel4',
            ordinary='if argument0==0 or filter(id) nonzero: publish(4,M8[state+0x209],id,M8[record])',
            id21='read method+104(0,1,21); publish record only if low3(return)==7',
            id30='special nested path remains a frontier in host tests; static bytes exported',
            filter_ids=filter_ids,
            publish_binding='core0x37d40+100 initially0x33ded ->file0x615ec',
            read_binding='core0x37d40+104 initially0x34471 ->file0x61c70; explicit hook in host tests',
            no_local_aggregation=True,return_r0='path-dependent last carried R0; no aggregate status'),
        publisher=dict(entry='0x615ec',channels='unsigned0..4 allowed; others return0xffffffff before table read',
            source='channel0..3 reads own entry; channel4 reads M32[M32[core0x37df8]] (entry0)',
            destination='M32[core0x37df8+4*channel], including distinct entry4',
            config='((old&0xcfffffff)|((arg1&3)<<28))&0xf80fffff | ((arg2&127)<<20)',
            stores=[['destination+0','config'],['destination+0x38',22],['destination+8','full arg3'],['destination+4',16]],
            local_return=0,poll=False,read_after_publish=False,physical_completion=False),
        distinctions=['tail getter/setter mutate table bytes; later consumer can submit them through a different method',
            'first-match getter and all-match setter differ for duplicate ids; setter return does not report match count',
            'nominal caller/consumer path does not establish execution order versus DMC17 tail in the device',
            'source entry0 and destination entry4 must not be conflated; zero return follows stores without acknowledgement'],
        unresolved=['caller/order of table application relative to loader tail','consumer id30 path and read method0x61c70',
            'producer of0xabcd1234','physical aliases/completion and init9/masks order','slot47/X0'],
        anchors={hex(a):v for a,v in anchors.items()},literals={hex(a):v for a,v in sorted(literals.items())},
        witnesses=[dict(pc=hex(p),bytes=raw.hex(),op=op,args=args) for p,(raw,op,args) in sorted(rows.items())],
        gnu=dict(instructions=len(rows),halfwords=len(covered),relative_targets=relative,literals=len(literals),selected_operands=len(SELECTED)),
        firmware_executed=False,slot47_resolved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');p.add_argument('--json',required=True);a=p.parse_args()
    try:r=inspect(a.sboot)
    except (OSError,ValueError,subprocess.CalledProcessError) as e:p.exit(2,str(e)+'\n')
    Path(a.json).write_text(json.dumps(r,indent=1)+'\n');print(json.dumps(r['gnu']))


if __name__=='__main__':main()
