#!/usr/bin/env python3
"""Static ACPM dispatcher completion after the selected FVP callback."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
from check_acpm_handshake_gnu import parse_thumb
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_acpm_handshake_hzc2 import thumb_target

U32=0xffffffff
SELECTED={
 0x391f8:('str','r3, [sp, #4]'),
 0x3929a:('blx','r3'),0x3929c:('str','r0, [sp, #4]'),
 0x392d4:('ldr','r2, [sp, #4]'),0x392dc:('bl','0x38684'),
 0x392e0:('mov','r2, r9'),0x392e4:('adds','r2, #1'),
 0x392f0:('ldr','r3, [r1, #52]'),0x392f2:('subs','r3, r3, r2'),
 0x392f4:('subs','r0, r3, #1'),0x392f6:('sbcs','r3, r0'),
 0x392f8:('negs','r3, r3'),0x392fa:('ands','r2, r3'),
 0x392fc:('ldr','r3, [r1, #16]'),0x392fe:('str','r2, [r3, #0]'),
 0x39300:('b.n','0x391fe'),0x39312:('movs','r0, #0'),
 0x39328:('movw','r1, #28432'),0x3933a:('b.n','0x3929e'),
}


def next_index(old,count):
    for x in (old,count):
        if type(x) is not int or not 0<=x<=U32:raise ValueError('expected u32')
    inc=(old+1)&U32
    return 0 if inc==count else inc


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    out=subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb','--start-address=0x391ee','--stop-address=0x3933c',str(Path(path).resolve())],text=True)
    rows=parse_thumb(out);relative=0
    for pc,(raw,op,args) in rows.items():
        if data[pc:pc+len(raw)]!=raw or op.startswith('.') or op=='udf':raise ValueError('invalid word')
        target=thumb_target(data,pc)
        if target is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=target:raise ValueError('branch mismatch')
            relative+=1
    if {x for pc,(raw,_,_) in rows.items() for x in range(pc,pc+len(raw),2)}!=set(range(0x391ee,0x3933c,2)):raise ValueError('coverage mismatch')
    for pc,expected in SELECTED.items():
        _,op,args=rows[pc]
        if (op,args.split('@')[0].strip())!=expected:raise ValueError(f'operand mismatch {pc:#x}')
    return dict(scope='static dispatcher continuation after selected callback',
        gnu=dict(instructions=len(rows),halfwords=(0x3933c-0x391ee)//2,relative_targets=relative,selected_operands=len(SELECTED)),
        callback_result=dict(saved='0x3929c -> frame+4',logged='0x392d4 -> R2 for logging call0x392dc',
            local_result_guard_before_index_store=False),
        index=dict(captured='R9 from selected index before callback',count='descriptor+52 reloaded after callback',
            formula='inc=u32(old+1); next=(inc==count ? 0 : inc)',store='0x392fe -> M32[descriptor+16]',
            modulo_for_arbitrary_invalid_indices=False),
        exit=dict(pc='0x39312',result=0,condition='pending mask emptied through selected empty-channel arm',
            aggregate_callback_errors=False),
        missing_callback='0x39328..0x3933a logs and joins0x3929e without replacing frame+4; initial zero is before loop',
        conditions=['selected nominal Thumb copy and compatible descriptor/channel layout',
            'intervening hooks/logging return and preserve carried state; aliases/side effects remain open',
            'count and index pointers are live reads, not file constants',
            'no automatic retry, hardware acknowledgement or global queue behavior inferred'],
        witnesses=[dict(pc=hex(pc),bytes=raw.hex(),op=op,args=args) for pc,(raw,op,args) in sorted(rows.items())],
        literals={},firmware_executed=False,slot47_resolved=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');a=p.parse_args()
    try:r=inspect(a.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as e:p.exit(2,f'{e}\n')
    print(json.dumps(r,indent=2))
