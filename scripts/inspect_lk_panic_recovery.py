#!/usr/bin/env python3
"""Static, exact-image evidence for HZC2 panic halt/context recovery. No execution."""
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
    'panic': (0x18f8a8, 0x18f950),
    'halt': (0x17d880, 0x17d89c),
    'context_count': (0x205788, 0x205794),
    'register_and_call': (0x205798, 0x205814 + 4),
    'recover': (0x205818, 0x2058d0),
    'save_context': (0x202800, 0x2028dc),
    'restore_context': (0x2028e0, 0x202978),
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
               (0x257900,0x28e4d0,0x28e530,0x28e548,0x28e588)}
    packed = b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    return dict(mode='static_panic_context_recovery',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        gnu_words=len(lines),gnu_relative_targets=len(branches),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc):dict(word=f'{raw:08x}',op=op,args=args)
                      for pc,(raw,op,args) in sorted(lines.items())},
        branches=branches,strings=strings,local_graphs=graphs,
        interpretation=dict(
            count_relative_address='0xd08490',slots_relative_address='0xd08498',
            slot_stride_bytes=16,slot_fields={'0':'saved context pointer','8':'optional callback'},
            registration='0x205798 stores X2 and X1, increments count, calls X0; normal return decrements count',
            no_context='panic count zero -> 0x17d880 -> print -> DAIFSet #2 -> self branch 0x17d898',
            context_available='0x205818 selects last slot, optionally calls callback, decrements count, tails to 0x2028e0',
            restore='load ELR/SPSR from frame +0x100/+0x108; restore registers/SP; X0=-1; ERET',
            saved_target='0x202864 stores incoming X30 at frame+0x100; not a fixed RDX target',
            invalid_context='count zero or context pointer null -> diagnostic print tail; conditional normal return leads to halt',
            runtime_count_callbacks_frame_and_EL_unknown=True,
            rdx_acquisition_or_RAM_retention_demonstrated=False),
        limits=['local static graphs retain conditional normal returns for opaque calls',
                'print/callback effects, asynchronous events, frame mutation and external callers remain frontiers',
                'save wrapper assumes usable active stack across SPSel change; no callable ABI validated',
                'no global absence-of-RDX claim; no firmware execution, reset, patch or phone operation'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot');args=parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as error:
        parser.exit(2,f'inspect_lk_panic_recovery: {error}\n')
