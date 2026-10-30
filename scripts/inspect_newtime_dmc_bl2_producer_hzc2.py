#!/usr/bin/env python3
"""Conditional BL2 -> ACPM provenance of DMC masks and h/g2 base."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from check_epbl_protocol_gnu import parse_lines
from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal,thumb_target
from inspect_el2_hzc2 import IMAGES,read_exact
from inspect_newtime_hzc2 import embedded
from inspect_newtime_record_hzc2 import inspect as record_inspect,plan

U32=0xffffffff
AP_RECORD=0x02073600
AP_SRAM=0x02039000
CORE_RECORD=0x3a600
A64_RANGES=((0x2d720,0x2d768),(0x2d814,0x2d854))
THUMB_RANGES=((0x64620,0x64636),(0x6463c,0x64652),(0x64658,0x64674),(0x6467c,0x64698),(0x648b0,0x648c0))
SELECTED={
 0x2d728:('ldr','w1, [x1, #4]'),0x2d72c:('add','w1, w1, w0'),
 0x2d730:('sxtw','x1, w1'),0x2d734:('str','x1, [x19, #616]'),
 0x2d758:('ldr','w1, [x1, #4]'),0x2d75c:('add','w1, w1, w0'),
 0x2d760:('sxtw','x1, w1'),0x2d764:('str','x1, [x19, #744]'),
 0x2d814:('ldr','x1, [x19, #744]'),0x2d818:('mov','w0, #0x7000'),
 0x2d81c:('movk','w0, #0xfdfc, lsl #16'),0x2d820:('add','w0, w1, w0'),
 0x2d824:('mov','x1, #0x3664'),0x2d828:('movk','x1, #0x207, lsl #16'),
 0x2d82c:('str','w0, [x1]'),0x2d834:('ldr','x0, [x19, #616]'),
 0x2d83c:('ldr','w2, [x0, #60]'),0x2d840:('str','w2, [x1]'),
 0x2d844:('ldr','w1, [x0, #88]'),0x2d850:('str','w1, [x0]'),
}


def uint(v):
    if type(v) is not int or not 0<=v<=U32:raise ValueError('expected u32')
    return v


def header_values(offset14,mask8,mask9):
    for v in (offset14,mask8,mask9):uint(v)
    ap_payload=(AP_RECORD+offset14)&U32
    return {AP_RECORD+0x60:mask8,AP_RECORD+0x64:(ap_payload-AP_SRAM)&U32,AP_RECORD+0x68:mask9}


def source_survey(data):
    raw=embedded(data);tables={t['key']:t for t in raw['parsed']['entries']}
    counts=Counter();groups={};per_row=[]
    for row in range(22):
        row_counts=Counter()
        for gate in range(512):
            result=plan(tables,row,gate);counts[result['status']]+=1;row_counts[result['status']]+=1
            if result['status']!='complete':continue
            s12,s14=result['steps'][12],result['steps'][14]
            t12,t14=tables[s12['key']],tables[s14['key']]
            if (t12['columns'],t12['rows'],t14['columns'],t14['rows'])!=(1,23,2,44):raise ValueError('source shape changed')
            m8,m9=t12['cells'][15],t12['cells'][22]
            key=(s12['key'],m8,m9,s14['key'],s14['payload_offset'])
            if key not in groups:
                groups[key]=dict(mask_key=hex(s12['key']),mask8=hex(m8),mask9=hex(m9),
                    mask8_source_file=hex(raw['block_file']+t12['offset']+12+60),
                    mask9_source_file=hex(raw['block_file']+t12['offset']+12+88),
                    base_key=hex(s14['key']),payload_offset=hex(s14['payload_offset']),
                    core_base=hex((CORE_RECORD+s14['payload_offset'])&U32),
                    first_case=dict(row=row,branch_mask=hex(gate)),multiplicity=0)
            groups[key]['multiplicity']+=1
        per_row.append(dict(row=row,counts=dict(row_counts)))
    summary=Counter()
    for g in groups.values():summary[(g['mask_key'],g['mask8'],g['mask9'])]+=g['multiplicity']
    table=tables[0xa1]
    return dict(assumptions=['embedded ECT preserved, construction completes, output R==AP0x02073600',
        'descriptor/payload/state preserved until selected BL2 stores and DMC reads',
        'AP SRAM aliases core, selected call0x2d960 returns preserving carried state; physical order unmeasured'],
        counts=dict(counts),per_row=per_row,
        mask_profiles=[dict(key=k[0],mask8=k[1],mask9=k[2],cases=n) for k,n in sorted(summary.items())],
        grouped_cases=list(groups.values()),
        source_tables=[dict(key=hex(k),file=hex(raw['block_file']+tables[k]['offset']+12),cells_u32=list(tables[k]['cells']),sha256=hashlib.sha256(struct.pack('<'+'I'*len(tables[k]['cells']),*tables[k]['cells'])).hexdigest()) for k in (0x81,0x82,0x83,0xa1)],
        table_a1=dict(file=hex(raw['block_file']+table['offset']+12),columns=2,rows=44,
            h_input0_12=[table['cells'][2*(i+18)+1] for i in range(13)],
            g2_input0_12=[table['cells'][2*(i+31)+1] for i in range(13)],
            units='not assigned',input_range='arrays cover only inputs0..12; no general bounds check inferred'),
        failed_constructions_excluded=True,physical_probabilities=False,observed_device_values=False)


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);record=record_inspect(path)
    root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    a64={};thumb={};literals={};relative=0
    for lo,hi in A64_RANGES:
        rows=parse_lines(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','aarch64',f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True))
        if set(rows)!=set(range(lo,hi,4)):raise ValueError('A64 coverage differs')
        a64.update(rows)
    for pc,(word,op,args) in a64.items():
        if word!=struct.unpack_from('<I',data,pc)[0]:raise ValueError('A64 word differs')
        if (op,args)!=SELECTED.get(pc,(op,args)):raise ValueError(f'operand mismatch {pc:#x}')
    for lo,hi in THUMB_RANGES:
        rows=parse_thumb(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True))
        if {p for pc,(raw,_,_) in rows.items() for p in range(pc,pc+len(raw),2)}!=set(range(lo,hi,2)):raise ValueError('Thumb coverage differs')
        thumb.update(rows)
    for pc,(raw,op,args) in thumb.items():
        if raw!=data[pc:pc+len(raw)] or op.startswith('.'):raise ValueError('Thumb word differs')
        to=thumb_target(data,pc)
        if to is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=to:raise ValueError('Thumb branch differs')
            relative+=1
        if op=='ldr' and '[pc,' in args:
            at,value=thumb_literal(data,pc,int(args.split(',')[0][1:]))
            if f'(0x{at:x})' not in args:raise ValueError('literal differs')
            literals[at]=value
    if struct.unpack_from('<I',data,0x649a8)[0]!=0x3a880:raise ValueError('loader descriptor differs')
    return dict(scope='conditional BL2 publication of DMC masks/base from NEWTIME',source_base='aab7d05d02e849639930767a7888bccb34fe595e',sboot_sha256=IMAGES['sboot'][1],
        producers=[dict(pc='0x2d840',ap='0x02073660',core_if_alias='0x3a660',source='M32[payload12+60]'),
            dict(pc='0x2d82c',ap='0x02073664',core_if_alias='0x3a664',source='u32(payload14_AP-0x02039000)'),
            dict(pc='0x2d850',ap='0x02073668',core_if_alias='0x3a668',source='M32[payload12+88]')],
        links=dict(directory='BL2 R+0x1a0,16 descriptors/16 bytes; under R/alias same as core0x3a7a0',
            descriptor12='0x2d728..0x2d734: SXTW(u32(AP_RECORD+M32[AP0x02073864])) -> S+616',
            descriptor14='0x2d758..0x2d764: SXTW(u32(AP_RECORD+M32[AP0x02073884])) -> S+744',
            core_conversion='0xfdfc7000 is -0x02039000 modulo2^32; final ADD W truncates pointer to32 bits',
            cache_agreement='under same preserved descriptor14/alias, header fallback and loader 0x648be both produce u32(0x3a600+offset14)',
            first_publisher='BL2 callback0x193fc builds descriptor/payload from embedded NEWTIME (existing hash-bound plan)',
            intervening_call='0x2d810->0x2d960 not executed here; memory preservation is an assumption'),
        survey=source_survey(data),prior_record_validation=dict(suffix=record['instructions'],prefix_index_sha256=record['prefix_instruction_index_sha256']),
        gnu=dict(a64_words=len(a64),a64_selected=len(SELECTED),thumb_instructions=len(thumb),thumb_relative_targets=relative,thumb_literals=len(literals)),
        a64_witnesses=[dict(pc=hex(pc),word=f'{w:08x}',op=op,args=args) for pc,(w,op,args) in sorted(a64.items())],
        witnesses=[dict(pc=hex(pc),bytes=raw.hex(),op=op,args=args) for pc,(raw,op,args) in sorted(thumb.items())],literals={hex(a):v for a,v in sorted(literals.items())},
        frontiers=['physical SRAM alias, source ECT/gates, executed row and ordering/preservation not measured',
            'partial constructions, other writers and configuration commands can change memory; producer is not exclusive',
            'values/units do not establish hardware effects, slot47 caller or X0'],firmware_executed=False,slot47_resolved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');p.add_argument('--json',required=True);a=p.parse_args()
    try:r=inspect(a.sboot)
    except (OSError,ValueError,subprocess.CalledProcessError) as e:p.exit(2,str(e)+'\n')
    Path(a.json).write_text(json.dumps(r,indent=1)+'\n');print(json.dumps(r['gnu']));print(json.dumps(r['survey']['mask_profiles']))

if __name__=='__main__':main()
