#!/usr/bin/env python3
"""Static HZC2 post-copy policy calls and secure-service boundary. No execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_lk_payload_return import summarize_local

BLOCKS = {
    'v2_tail': (0x12e3cc, 0x12e408),
    'v3_tail': (0x12e84c, 0x12e880),
    'policy': (0x151b10, 0x151c00),
    'state_getter': (0x150320, 0x150330),
    'cp_debug': (0x151248, 0x151294),
    'cp_info': (0x151298, 0x151300),
    'fingerprint': (0x159028, 0x159120),
    'smc_wrapper': (0xf6088, 0xf6090),
}


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for a,b in BLOCKS.values():
        lines.update(parse_lines(subprocess.check_output(command + [
            '-D','-b','binary','-m','aarch64',f'--start-address={a}',
            f'--stop-address={b}',str(Path(path).resolve())], text=True)))
    expected = {pc for a,b in BLOCKS.values() for pc in range(a,b,4)}
    if set(lines) != expected:
        raise ValueError('GNU coverage differs')
    branches = {}
    for pc,(raw,op,args) in lines.items():
        if raw != struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):
            raise ValueError(f'GNU instruction differs at {pc:#x}')
        kind,target = flow(raw,pc)
        if kind in ('b','bl','conditional'):
            if target != direct_target(op,args):
                raise ValueError(f'GNU target differs at {pc:#x}')
            branches[hex(pc)] = dict(kind=kind,target=hex(target))
    graphs = {name:summarize_local(data,a,a,b) for name,(a,b) in BLOCKS.items()}
    strings = {hex(p):data[p:data.index(0,p)].decode('ascii') for p in
               (0x23fc08,0x23fc28,0x23fc48,0x242698,0x2426d8,0x242718,0x242750,0x242778,0x242ee0)}
    packed = b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    return dict(mode='static_postcopy_policy',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        gnu_words=len(lines),gnu_relative_targets=len(branches),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc):dict(word=f'{raw:08x}',op=op,args=args)
                      for pc,(raw,op,args) in sorted(lines.items())},
        branches=branches,strings=strings,local_graphs=graphs,
        interpretation=dict(
            caller_return='v2/v3 overwrite W0 with zero after normal return',
            policy_return='both local RET sites return W0=0 conditional on callees returning',
            cp_debug_smc='X0=0x82000701 X1=1 X2=0 X3=0',
            cp_info_smc='X0=0x82000702 X1=sign_extend_32(1 << (index & 31)) X2=0 X3=0',
            policy_cp_indices=[20,21,23],
            fingerprint_smc='X0=0xb2000201 X1=100 X2=1 then 6 X3=0',
            fingerprint_status='test returned X0 & 0xf0; first failure logs and continues',
            firmware_executed=False),
        limits=['local graph only; opaque calls have conditional normal-return edges',
                'secure provider, state, indirect effects and other callees unresolved',
                'no proof of image acceptance, no complete no-transformation claim',
                'strings describe intended purpose, not observed hardware effects'])



if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot');args=parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as error:
        parser.exit(2,f'inspect_lk_postcopy_policy: {error}\n')
