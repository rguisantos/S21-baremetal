#!/usr/bin/env python3
"""Static separation of full FVP return, cache decision and projected reply."""
import argparse
import json
from inspect_newtime_fvp_effective_hzc2 import inspect as inspect_fvp, returned_cache, u32
from inspect_newtime_command6_hzc2 import response_projection

SELECTED = {
    0x3f120: ('movs','r4, r0'), 0x3f130: ('cbnz','r4, 0x3f15c'),
    0x3f144: ('movs','r0, r4'), 0x3f160: ('movs','r1, r4'),
    0x3f166: ('bl','0x3f088'), 0x3f16a: ('b.n','0x3f144'),
    0x3f2d0: ('movw','r6, #65535'), 0x3f2d4: ('movs','r5, r0'),
    0x3f2d6: ('movs','r1, r0'), 0x3f2d8: ('ands','r6, r0'),
    0x3f1de: ('orrs','r4, r6'), 0x3f1e0: ('str','r4, [r0, #0]'),
    0x3f1f2: ('blx','r3'), 0x3f202: ('movs','r0, r5'),
}


def outcome(result, frame_value, index=5, header=0):
    for v in (result,frame_value,index,header): u32(v)
    reply=response_projection(header,result)
    return dict(full_callback_return=result,cache_write=returned_cache(index,result,frame_value),
                constructed_word=reply['constructed'],published_word=reply['published'],
                bl2_exact_zero=reply['published']==0,
                physical_success_established=False)


def inspect(path):
    source=inspect_fvp(path)  # hash/size + independent GNU validation, no firmware execution
    rows={int(r['pc'],16):r for r in source['witnesses']}
    for pc,expected in SELECTED.items():
        r=rows[pc]
        if (r['op'],r['args'].split('@')[0].strip())!=expected:
            raise ValueError(f'return instruction differs at {pc:#x}')
    return dict(scope='static command6/domain0/channel1 return planes',
        witnesses=[rows[p] for p in SELECTED],
        scenarios=[dict(result=r,**outcome(r,300)) for r in (0,1,10,65536,0x80000000,0xffffffff)],
        conditions=['selected copy mapping and stable roots/private frames',
                    'logging/publication calls return and preserve carried r4/r5/r6',
                    'reply allocation returns a valid stable slot; no alias/concurrent writes',
                    'non-returning polls/calls do not produce a completed response'],
        boundaries=['caller of the FVP callback may interpret its full return separately',
                    'no automatic retry or physical hardware result established',
                    'cache is not a hardware acknowledgement'],
        firmware_executed=False,slot47_resolved=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');a=p.parse_args()
    try: report=inspect(a.sboot)
    except Exception as e:p.exit(2,f'{e}\n')
    print(json.dumps(report,indent=2))
