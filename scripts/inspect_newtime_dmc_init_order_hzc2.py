#!/usr/bin/env python3
"""Selected program order of BL2/ACPM handshake and later DMC mask publication."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
from check_epbl_protocol_gnu import parse_lines,direct_target
from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal,thumb_target
from inspect_bl2_geometry_record import wide64
from inspect_el2_hzc2 import IMAGES,read_exact
from inspect_lk_final_edges import flow

A64_RANGES=((0x179e4,0x17a60),(0x17eb0,0x17ed8),(0x17fb4,0x1801c),(0x1e2c0,0x1e2e4))
THUMB_RANGES=((0x56e00,0x56e72),(0x56eee,0x56f0c),(0x38e6a,0x38ec0),(0x5f600,0x5f61a))
SELECTED_A64={0x17a40:('bl','0x19038'),0x17a50:('str','wzr, [x21]'),0x17a5c:('ret',''),
 0x17eb0:('bl','0x17974'),0x17ec0:('mov','w0, #0xabcd'),0x17ec8:('movk','w0, #0x1234, lsl #16'),0x17ecc:('ldr','w1, [x2]'),0x17ed0:('cmp','w1, w0'),
 0x17ed4:('b.ne','0x17ecc'),0x17fe8:('str','x2, [x4, #1312]'),0x18000:('bl','0x1dc90'),
 0x18018:('str','wzr, [x0]'),0x1e2d0:('blr','x3'),0x1e2d8:('ldr','x2, [x25, #192]'),0x1e2e0:('blr','x2')}
SELECTED_THUMB={0x56e1e:('bl','0x56ee0'),0x56ef2:('str','r2, [r3, #0]'),
 0x56ef6:('ldr','r3, [r2, #0]'),0x56efa:('bne.n','0x56ef6'),
 0x56f00:('str','r4, [r3, #0]'),0x56f0a:('str','r2, [r3, #0]'),
 0x56e6e:('str','r2, [r3, #0]'),0x56e70:('pop','{r4, r5, r6, pc}'),
 0x38e7e:('cbz','r2, 0x38eb6'),0x38e90:('blx','r8'),0x38eb4:('str','r3, [r6, #80]'),
 0x38eb8:('adds','r5, #1'),0x38eba:('adds','r4, #48'),0x38ebe:('bcc.n','0x38e76'),
 0x5f610:('str','r2, [r3, #12]')}
EDGES=(('pub108','read108'),('read108','ack108'),('ack108','poll_zero'),
 ('poll_zero','ready10c'),('ready10c','read_magic'),('read_magic','late_entry'),
 ('late_entry','late_masks'),('ready10c','return7'),('return7','init9'))


def precedes(a,b,edges=EDGES):
    pending=[a];seen=set()
    while pending:
        x=pending.pop()
        for source,destination in edges:
            if source==x:
                if destination==b:return True
                if destination not in seen:seen.add(destination);pending.append(destination)
    return False


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    a64={};thumb={};literals={};relative=[0,0]
    for lo,hi in A64_RANGES:
        rows=parse_lines(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','aarch64',f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True))
        if set(rows)!=set(range(lo,hi,4)):raise ValueError('A64 coverage mismatch')
        a64.update(rows)
    for pc,(w,op,args) in a64.items():
        if w!=struct.unpack_from('<I',data,pc)[0]:raise ValueError('A64 word mismatch')
        kind,to=flow(w,pc)
        if kind in ('b','bl','conditional'):
            if direct_target(op,args)!=to:raise ValueError('A64 target mismatch')
            relative[0]+=1
    for lo,hi in THUMB_RANGES:
        rows=parse_thumb(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True))
        if {x for p,(raw,_,_) in rows.items() for x in range(p,p+len(raw),2)}!=set(range(lo,hi,2)):raise ValueError('Thumb coverage mismatch')
        thumb.update(rows)
    for pc,(raw,op,args) in thumb.items():
        if raw!=data[pc:pc+len(raw)] or op.startswith('.'):raise ValueError('Thumb word mismatch')
        to=thumb_target(data,pc)
        if to is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=to:raise ValueError('Thumb target mismatch')
            relative[1]+=1
        if op=='ldr' and '[pc,' in args:
            at,value=thumb_literal(data,pc,int(args.split(',')[0][1:]));literals[at]=value
            if f'(0x{at:x})' not in args:raise ValueError('Thumb literal mismatch')
    for rows,selected in ((a64,SELECTED_A64),(thumb,SELECTED_THUMB)):
        for pc,expect in selected.items():
            _,op,args=rows[pc]
            if (op,args.split('@')[0].strip())!=expect:raise ValueError(f'operand mismatch {pc:#x}')
    word=lambda at:struct.unpack_from('<I',data,at)[0]
    anchors={0x56e88:0x1234abcd,0x56e8c:0xa590010c,0x56fd8:0xa5900108,0x56fdc:0x38e00,
        0x3b2c0:1,0x3b320:1,0x39a48:0x29600,0x39a90:0x31e00,0x5f63c:0x37c40}
    if any(word(at)!=v for at,v in anchors.items()):raise ValueError('anchor mismatch')
    if wide64(data,(0x179e8,0x179ec),21)!=0x15900108:raise ValueError('ACK address mismatch')
    if wide64(data,(0x17ebc,0x17ec4),2)!=0x1590010c:raise ValueError('magic address mismatch')
    for at,to in ((0x314c8,0x2d568),(0x31510,0x2f6c0)):
        if struct.unpack_from('<Q',data,at)[0]-0x020ea000!=to:raise ValueError('nominal selected pointer mismatch')
    return dict(scope='selected program order; not measured cross-core chronology',
        source_base='faed93b64560c861d6c4f53cc10ab6df4cf91e32',sboot_sha256=IMAGES['sboot'][1],
        phases=dict(pub108='0x56ef2 publishes core0x38e00 at local0xa5900108',
            ack108='0x17a50 clears AP0x15900108 after call0x19038 returns',
            after_ack='0x56ef6..0x56efa exits on zero; 0x56f00/0x56f0a publish bases0x38e00/0x3a600',
            ready10c='0x56e6e publishes0x1234abcd at local0xa590010c before returning init7',
            read_magic='after return of 0x17eb0, AP0x17ecc waits for0x1234abcd at AP0x1590010c',
            late_entry='AP0x18000 calls0x1dc90, after intervening gates/calls',
            late_masks='selected path inside0x1dc90 -> nominal slot24 0x2d568 -> mask/base stores0x2d82c/0x2d840/0x2d850',
            init9='framework0x38e90 reaches descriptor9 after descriptor7 callback returns, if enabled/count/roots preserved'),
        distinction=dict(first_data_core='0x38e00 (DVFS per-domain records)',later_record_core='0x3a600 (BL2 header/directory)',
            initial_ack_certifies_later_mask_publication=False,
            ap_clear_after_late_call='0x18018 clears AP0x15900104; no ACPM consumer/barrier of that address proven here'),
        edges=[dict(before=a,after=b) for a,b in EDGES],
        unordered_pair=['late_masks','init9'],
        abstract_orders=[['pub108','read108','ack108','poll_zero','ready10c','return7','init9','read_magic','late_entry','late_masks'],
            ['pub108','read108','ack108','poll_zero','ready10c','read_magic','late_entry','late_masks','return7','init9']],
        abstract_orders_are_observed_executions=False,
        conditions=['same selected invocation; nominal roots/pointers preserved; selected callbacks return',
            'AP/local MMIO aliases and fresh samples from these writes, not stale/other producers',
            'core poll zero attributed to AP0x17a50, not initial clear0x179a8; magic sample attributed to current init7',
            'intervening gates/calls and other writers can constrain order beyond this partial model',
            'program order does not establish visibility/coherency/barriers or absence of earlier publication'],
        not_proven=['actual cross-core interleaving','race on physical hardware','first/only mask writer',
            'no other ready signal','state stable until DMC command8/9','slot47/X0'],
        gnu=dict(a64_words=len(a64),thumb_instructions=len(thumb),relative_targets=relative,
            literals=len(literals),selected_operands=len(SELECTED_A64)+len(SELECTED_THUMB)),
        a64_witnesses=[dict(pc=hex(pc),word=f'{w:08x}',op=op,args=args) for pc,(w,op,args) in sorted(a64.items())],
        witnesses=[dict(pc=hex(pc),bytes=raw.hex(),op=op,args=args) for pc,(raw,op,args) in sorted(thumb.items())],
        literals={hex(a):v for a,v in sorted(literals.items())},anchors={hex(a):v for a,v in anchors.items()},
        firmware_executed=False,slot47_resolved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');p.add_argument('--json',required=True);a=p.parse_args()
    try:r=inspect(a.sboot)
    except (OSError,ValueError,subprocess.CalledProcessError) as e:p.exit(2,str(e)+'\n')
    Path(a.json).write_text(json.dumps(r,indent=1)+'\n');print(json.dumps(r['gnu']))

if __name__=='__main__':main()
