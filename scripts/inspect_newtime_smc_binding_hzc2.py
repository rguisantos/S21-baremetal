#!/usr/bin/env python3
"""Static nominal NEWTIME binding to SMC. No monitor call or firmware execution."""
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
from inspect_newtime_reloads_hzc2 import inspect as inspect_reloads

RANGES=((0x16420,0x16428),(0x17fb8,0x18004),(0x1dc90,0x1dcc0),(0x2d364,0x2d398))
SOURCE='https://github.com/xfwdrev/android_kernel_samsung_ex2100/blob/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0/include/soc/samsung/exynos-smc.h'


def sfr_write_candidate(identifier):
    """Inverse of the cited header's SFR_W encoding; not monitor validation."""
    if type(identifier) is not int or not 0<=identifier<=0xffffffff or identifier>>30 != 1:
        raise ValueError('not a u32 SFR_W identifier under the cited convention')
    return (identifier & 0x3fffffff)<<2


def inspect(path):
    data=read_exact(path,*IMAGES['sboot'])
    previous=inspect_reloads(path)
    root=Path(__file__).resolve().parent.parent
    command=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
             str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for first,last in RANGES:
        lines.update(parse_lines(subprocess.check_output(command+['-D','-b','binary','-m','aarch64',
            f'--start-address={first}',f'--stop-address={last}',str(Path(path).resolve())],text=True)))
    if set(lines)!={pc for a,b in RANGES for pc in range(a,b,4)}:raise ValueError('GNU coverage differs')
    relative=0
    for pc,(word,op,args) in lines.items():
        if word!=struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):raise ValueError('GNU word differs')
        kind,target=flow(word,pc)
        if kind in ('b','bl','conditional'):
            if target!=direct_target(op,args):raise ValueError('GNU relative target differs')
            relative+=1
    selected={0x17fbc:('adrp','x4, 0x30000'),0x17fc0:('add','x3, x4, #0x520'),
        0x17fc4:('add','x3, x3, #0x2c0'),0x18000:('bl','0x1dc90'),
        0x1dcb4:('cbz','x3, 0x1dcc0'),0x1dcb8:('add','x0, x19, #0x688'),
        0x1dcbc:('str','x3, [x0, #784]'),0x1dc94:('adrp','x19, 0x31000'),
        0x2d368:('adrp','x2, 0x31000'),0x2d374:('add','x2, x2, #0x688'),
        0x2d390:('cbz','x0, 0x2d398'),0x2d394:('str','x0, [x2, #784]'),
        0x16420:('smc','#0x0'),0x16424:('ret','')}
    for pc,expected in selected.items():
        if lines[pc][1:]!=expected:raise ValueError(f'operand differs at {pc:#x}')
    cells={a:struct.unpack_from('<Q',data,a)[0] for a in (0x31998,0x30828,0x31580)}
    if cells!={0x31998:0,0x30828:0x02100420,0x31580:0x02117364}:raise ValueError('initial binding data differs')
    events=previous['column1_other_reader']['events']
    payloads=previous['column1_other_reader']['supplied_payloads']
    derived=[]
    for i,event in enumerate(events):
        identifier=int(event['tag'],16);address=sfr_write_candidate(identifier)
        vals=[p['values'][i]['supplied_X2'] for p in payloads]
        derived.append(dict(index=i,X0='0xffffffffffffff9b',X1=hex(identifier),
            address_candidate_under_reference_macro=hex(address),
            row10_supplied_X2=vals[0],row15_supplied_X2=vals[1],different=vals[0]!=vals[1],X3=0))
    packed=b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    return dict(mode='static_newtime_smc_binding',sboot_sha256=IMAGES['sboot'][1],
        previous_instruction_index_sha256=previous['instruction_index_sha256'],
        previous_gnu_words=previous['gnu_words'],gnu_words=len(lines),gnu_relative_targets=relative,
        selected_operands=len(selected),instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        witnesses=[dict(pc=hex(pc),word=f'{word:08x}',op=op,args=args) for pc,(word,op,args) in sorted(lines.items())],
        ranges=[dict(first=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest()) for a,b in RANGES],
        primary_path=dict(call='0x18000',callee='0x1dc90',X3_file='0x307e0',
            X3_nominal='0x0211a7e0',conditional_store='0x1dcbc',cell='0x31998',
            method_offset=72,method_cell='0x30828',method_pointer=hex(cells[0x30828]),
            nominal_method_file='0x16420',method_instructions=['SMC #0','RET'],
            preservation_and_execution_observed=False),
        secondary_path=dict(entry='0x2d364',nominal_table='0x31408',index=47,cell='0x31580',
            pointer=hex(cells[0x31580]),store='0x2d394',argument='incoming X0 if nonzero',
            direct_candidates=branch_candidates(data,0x2d364),
            pointer_occurrences=[hex(x) for x in occurrences(data,struct.pack('<Q',cells[0x31580]))],
            incoming_argument_origin_resolved=False),
        reference_convention=dict(source=SOURCE,command_name='SMC_CMD_REG',command_signed=-101,
            write_identifier='(1 << 30) | (address >> 2)',macro_lines=[26,114,116,117],
            source_is_stock_HZC2_or_monitor=False),
        supplied_conditional_requests=derived,
        limits=['nominal pointer mapping and preservation remain conditions',
                'no monitor implementation, accepted request or response observed',
                'reference macro identifies candidate addresses, not physical field names',
                'secondary writer argument and complete alias/store inventory remain open'],
        firmware_executed=False,qemu_scope_extended=False,phone_access=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:result=inspect(args.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:parser.exit(2,f'{exc}\n')
    print(json.dumps(result,indent=2))
