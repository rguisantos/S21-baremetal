#!/usr/bin/env python3
"""Static FVP cap/enable setters and their selected completion paths."""
import argparse
import json
import struct
import subprocess
from inspect_newtime_fvp_effective_hzc2 import inspect as inspect_fvp, STATE, CAP_ENABLE, u32

SELECTED={
 0x3f17c:('ldr','r2, [r3, #4]'),0x3f180:('mov','r8, r2'),
 0x3f18a:('movw','r6, #65535'),0x3f190:('ands','r6, r4'),
 0x3f184:('ldr','r2, [r3, #12]'),
 0x3f33c:('cmp','r7, #1'),0x3f33e:('bne.n','0x3f342'),
 0x3f340:('b.n','0x3f598'),0x3f35e:('cmp','r2, #2'),
 0x3f362:('b.n','0x3f692'),0x3f598:('movs','r2, #140'),
 0x3f59a:('muls','r6, r2'),0x3f5aa:('str','r2, [r6, #16]'),
 0x3f5ae:('movs','r0, #1'),0x3f5b0:('blx','r3'),
 0x3f5b2:('movs','r5, #0'),0x3f5b6:('b.n','0x3f1e0'),
 0x3f692:('movw','r2, #8352'),
 0x3f696:('mov','r1, r8'),0x3f69c:('str','r1, [r2, #0]'),
 0x3f6a2:('b.n','0x3f1d6'),0x3f1d6:('add','r1, sp, #12'),
 0x3f1da:('blx','r3'),0x3f1f2:('blx','r3'),0x3f202:('movs','r0, r5'),
}


def cap_store(domain,value):
    for v in (domain,value):u32(v)
    if domain>65535:raise ValueError('packet domain is low16')
    return dict(core=(STATE+140*domain+16)&0xffffffff,value=value)


def enable_store(value):
    u32(value);return dict(core=CAP_ENABLE,value=value)


def inspect(path):
    source=inspect_fvp(path)
    rows={int(r['pc'],16):r for r in source['witnesses']}
    for pc,expected in SELECTED.items():
        r=rows[pc]
        if (r['op'],r['args'].split('@')[0].strip())!=expected:raise ValueError(f'operand mismatch {pc:#x}')
    return dict(scope='static selected FVP command4/channel1 and command5/subselector2',
        firmware_size=4194304,firmware_sha256='a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91',
        cap=dict(command=4,channel=1,domain='packet word0 low16',value='packet word1 full u32',
                 store='0x3f5aa: STATE+140*domain+16',later_domain_bound_in_selected_arm=False,
                 response_allocator='0x3f5b0: API+12, R0=1',direct_relay_call=False),
        enable=dict(command=5,subselector='packet word3 ==2',value='packet word1 full u32',
                    store='0x3f69c: core120a0',boolean_normalization=False,
                    selected_channel_guard=False,direct_relay_call=False),
        result=dict(local_return=0,condition='response allocator, publisher and logging return normally',
                    selected_arbitration=False,selected_effective_or_cache_store=False,
                    next_command6='reloads cap and enable as part of its arbitration; no automatic event inferred'),
        conditions=['selected nominal copy, input packet and compatible API roots',
                    'private frame and carried registers preserved by opaque API/logging calls',
                    'no overlapping/concurrent writes; cap and enable may change elsewhere',
                    'absence of direct relay call does not exclude side effects inside opaque calls'],
        witnesses=[rows[p] for p in sorted(rows) if p in SELECTED or any(lo<=p<hi for lo,hi in ((0x3f1d6,0x3f210),(0x3f32c,0x3f36a),(0x3f598,0x3f5b8),(0x3f692,0x3f6a4)))],
        selected_operands=len(SELECTED),gnu=source['gnu'],
        firmware_executed=False,slot47_resolved=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');a=p.parse_args()
    try:r=inspect(a.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as e:p.exit(2,f'{e}\n')
    print(json.dumps(r,indent=2))
