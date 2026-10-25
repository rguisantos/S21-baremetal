#!/usr/bin/env python3
"""Exact HZC2 NEWTIME columns 1/12: lookup keys, payload layout and later readers."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_bl2_geometry_record import expect
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_hzc2 import embedded
from inspect_newtime_record_hzc2 import inspect as inspect_record, plan, unsigned

TEMPLATES = (
    (0x2d568, 'a9be53f3 2a0103f4 a9017bf5 2a0003f5 d286c200 f2a040e0 b9400001 5286c000 72a040e0 0b000020 528b3fe1 72a040e1 6b01001f 5400006d 52800080 97ffca05 d286fa00 90000026 f2a040e0 911a20c2 d2813781 d286cb03 f2a2b0c1 f2a040e3 b9400c00 390ac040 d2870200 f2a040e0 b9400800 391a20c0 d2870a00 f2a040e0 b9400c00 39004040 d286f400 f2a040e0 b9400407 5286c000 72a040e0 0b0000e7 b9400020 d3507800 93407ce7 1ad42800 360000c0 52800020 390b4440 52800020 b9000060 14000003 390b445f b900007f 7100169f d286ca82 f2a040e2 540002ad b9400020 53003c00 1ad42800 36000220 52800020 b9000040 d286f800 5286c002 f2a040e0 72a040e2 91008000 51001a94 b85e4008 b9400400 0b020108 0b020000 93407d08 93407c05 d2870000 1400000e d286f600 b900005f f2a040e0 5286c002 91008000 72a040e2 b85e4008 b9400400 0b020108 0b020000 93407d08 93407c05 d286fe00 f2a040e0 911a20d3 91010000 b85c4001 b85e4004 b9400400 0b020021 0b020084 f9405a69 0b020002 d2870a00 f2a040e0 93407c23 93407c84 93407c42 b9400401 5286c000 72a040e0 0b000021 93407c21 f9000e61 d2870c01 f2a040e1 b9400421 0b000021 93407c21 f9013661 d2870e01 f2a040e1 b9400421 0b000021 93407c21 f9001521 d2871001 f2a040e1 b9400421 0b000021 93407c21 f9017661 d2871201 f2a040e1 b9400421 f9006a67 93407e87 0b000020 8b071908 8b070c42 93407c00 f9015660 d286fa00 f2a040e0 b9400800 f9006662 531e7400 1b147c00 8b20c0a0 a90ba260 d286fe00 f2a040e0 b9400801 395a20c0 531e7421 d37ef400 1b157c35 9b071004 d286c000 f2a040e0 8b35c075 1b017e81 f9400000 f9017a60 8b21c061 f9000664 f9417a60 f9013a75 d3441c00 390ac660 d286ca80 f9013e61 f2a040e0 b9400000'),
    (0x2e4b4, 'f0000000 f943ac00 b9400401 52800000 36000141 52800080 1ac02422 36000062 11002000 14000005 11000400 71007c1f 54ffff41 52800000 d286cb81 f2a040e1 b9000020 d65f03c0'),
)


def column1_result(word1):
    """2e4b4 leaf: bit0 enables scan of bits4..30; hit publishes bit+8."""
    word1 = unsigned(word1,32)
    if word1 & 1:
        for bit in range(4,31):
            if word1 >> bit & 1: return bit+8
    return 0


def inspect(path):
    previous = inspect_record(path)
    data = read_exact(path,*IMAGES['sboot'])
    for pc,t in TEMPLATES: expect(data,pc,t)
    raw = embedded(data); tables = {t['key']:t for t in raw['parsed']['entries']}
    table = tables[0x11111111]
    a,b = (table['cells'][row*17:(row+1)*17] for row in (10,15))
    differences = [dict(column=i,row10=hex(x),row15=hex(y)) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
    if [d['column'] for d in differences] != [0,1,12]:
        raise ValueError('NEWTIME row differences changed')
    selected = []
    for key in (0x12b,0x11b,0x128,0x118,0x71,0x73):
        t = tables[key]; start = raw['block_file']+t['offset']+12
        size = t['columns']*t['rows']*4
        selected.append(dict(key=hex(key),mode=t['mode'],columns=t['columns'],rows=t['rows'],
            data_file=hex(start),bytes=size,sha256=hashlib.sha256(data[start:start+size]).hexdigest(),
            second_u32=hex(t['cells'][1]),
            derived_0207365c=column1_result(t['cells'][1]) if key in (0x12b,0x11b,0x128,0x118) else None))
    cases = []
    for row in (10,15):
        for mask in (0,511):
            p = plan(tables,row,mask)
            if p['status']!='complete': raise ValueError('selected conditional plan changed')
            cases.append(dict(row=row,supplied_branch_mask=hex(mask),used_bytes=hex(p['cursor']),
                columns=[dict(column=s['index']+1,key=hex(s['key']),
                    descriptor_offset=hex(s['descriptor_offset']),payload_offset=hex(s['payload_offset']),
                    bytes=s['bytes'],columns=s['columns'],rows=s['rows'])
                    for s in p['steps'] if s['index'] in (0,11)]))
    packed = b''.join(struct.pack('<II',pc+i*4,int(w,16))
        for pc,t in TEMPLATES for i,w in enumerate(t.split()))
    return dict(mode='static_newtime_columns_1_12',sboot_sha256=IMAGES['sboot'][1],
        previous_suffix_index_sha256=previous['instructions']['suffix_index_sha256'],
        new_instruction_words=len(packed)//8,new_instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        special_table=dict(data_file='0x706c8',rows=22,columns=17,row_stride='0x88'),
        differences=differences,selected_subtables=selected,conditional_record_plans=cases,
        callback=dict(scratch_tail_bytes_allocated=144,tail_cells_copied=16,
            parsed_metadata_entry_bytes=32,output_descriptor_bytes=16,
            column_to_loop_index='column-1',
            optional_key_transform='index<=8 and supplied gate branch: nibble8 ? key+3 : key-3',
            key_reads=['0x197a4','0x197d4','0x19804','0x19820','0x1988c'],
            subtable_lookup='0x1982c -> 0x1c83c',key_store='0x19890',
            payload_copy='0x19964 load u32 -> 0x19968 store u32',
            gate_before_key_read='0x19774: read AP0x158609bc'),
        later_static_consumers=dict(conditional_on_fixed_record_alias_and_success=True,
            column1=dict(descriptor='AP0x020737a0',offset_read='0x2d5f8',
                pointer_cached='0x2d774 -> relative global0x31758',
                pointer_load='0x2e4b8',second_u32_load='0x2e4bc',
                fixed_output_store='0x2e4f4 -> AP0x0207365c',
                arithmetic='if bit0 clear:0; else first set bit in4..30 plus8; no hit:0'),
            column12=dict(descriptor='AP0x02073850',rows_read='0x2d5e8',
                rows_cached='0x2d5ec -> relative global0x31698 byte',
                offset_read='0x2d708',pointer_cached='0x2d71c -> relative global0x316a0',
                next_payload_reader_resolved=False)),
        branch_values_or_live_record_observed=False,later_consumers_executed=False,
        final_controller_write_or_physical_timing_parameter_identified=False)


def gnu(path,report):
    command=['bash',str(Path(__file__).resolve().parent/'cross-run.sh'),
        str(Path(__file__).resolve().parent.parent/'tools/root'),
        str(Path(__file__).resolve().parent.parent/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for pc,t in TEMPLATES:
        output=subprocess.check_output(command+['-D','-b','binary','-m','aarch64',
            f'--start-address={pc}',f'--stop-address={pc+4*len(t.split())}',str(Path(path).resolve())],text=True)
        lines.update(parse_lines(output))
    expected={pc+i*4:int(w,16) for pc,t in TEMPLATES for i,w in enumerate(t.split())}
    if set(lines)!=set(expected):raise ValueError('GNU consumer coverage differs')
    targets=0
    for pc,(raw,op,args) in lines.items():
        if raw!=expected[pc] or op in ('.inst','udf'):raise ValueError('GNU consumer word differs')
        kind,target=flow(raw,pc)
        if kind in ('b','bl','conditional'):
            if direct_target(op,args)!=target:raise ValueError('GNU consumer target differs')
            targets+=1
    selected={0x2d5f8:('ldr','w7, [x0, #4]'),0x2d774:('str','x7, [x19, #208]'),
        0x2d5e8:('ldr','w0, [x0, #12]'),0x2d5ec:('strb','w0, [x2, #16]'),
        0x2d708:('ldr','w1, [x0, #4]'),0x2d71c:('str','x1, [x19, #24]'),
        0x2e4b8:('ldr','x0, [x0, #1880]'),0x2e4bc:('ldr','w1, [x0, #4]'),
        0x2e4e0:('cmp','w0, #0x1f'),0x2e4f4:('str','w0, [x1]')}
    if any(lines[pc][1:]!=text for pc,text in selected.items()):raise ValueError('GNU consumer operand differs')
    digest=hashlib.sha256(b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))).hexdigest()
    if digest!=report['new_instruction_index_sha256']:raise ValueError('GNU consumer index differs')
    return dict(mode='GNU_newtime_column_consumers',sboot_sha256=report['sboot_sha256'],
        instruction_index_sha256=digest,
        words_matched=len(lines),relative_targets_matched=targets,selected_operands_matched=len(selected),
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        firmware_or_controller_executed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot');parser.add_argument('--gnu',action='store_true');args=parser.parse_args()
    try:
        result=inspect(args.sboot)
        if args.gnu:result=gnu(args.sboot,result)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'inspect_newtime_columns_hzc2: {exc}\n')
    print(json.dumps(result,indent=2))
