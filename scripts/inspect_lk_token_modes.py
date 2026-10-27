#!/usr/bin/env python3
"""Static HZC2 command-21 dispatch and token mode-bit writer. No execution."""
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
    'request_command_fragment': (0x1422e0, 0x142338),
    'dispatch_guard_fragment': (0x13214c, 0x132164),
    'dispatch1_fragment': (0x1323a8, 0x1323c0),
    'command21_label_fragment': (0x132498, 0x1324b4),
    'dispatch2_guard_fragment': (0x13233c, 0x13234c),
    'dispatch2_fragment': (0x132738, 0x132750),
    'command21_call_fragment': (0x1329a0, 0x1329b0),
    'command_result_fragment': (0x13275c, 0x132770),
    'mode_writer': (0x13a998, 0x13ada4),
    'publication_error_fragment': (0x15736c, 0x1573ac),
}


def relative_table(data, table, anchor):
    return [dict(command=i+1, slot=hex(table+2*i),
                 signed_halfword=struct.unpack_from('<h',data,table+2*i)[0],
                 target=hex(anchor+4*struct.unpack_from('<h',data,table+2*i)[0]))
            for i in range(35)]



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
               (0x2388a0,0x236638,0x236658,0x236500,0x2385e0,0x233f78)}
    packed = b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    return dict(mode='static_token_mode_writer',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        gnu_words=len(lines),gnu_relative_targets=len(branches),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc):dict(word=f'{raw:08x}',op=op,args=args)
                      for pc,(raw,op,args) in sorted(lines.items())},
        branches=branches,strings=strings,local_graphs=graphs,
        dispatch_tables=[relative_table(data,0x2384f8,0x1323c0),relative_table(data,0x238540,0x132750)],
        interpretation=dict(
            command=21, handler='0x13a998',
            parser='0x136eb0 input workspace+0x50e; output allocated parsed object',
            parsed_count_offset='0x5ca8', parsed_first_id_offset='0x5caa',
            count_max=128, id_max=255,
            destination='workspace+0x29f68+8*(id>>6)',
            operation='old_word OR (1 << (id & 63))',
            completed_flag='workspace+16 OR 0x20 after zero-count or completed loop',
            count_error='0xf03c0012', id_error='0xf03c0013',
            failure='later invalid ID leaves prior local OR stores; no local rollback before cleanup',
            publication='caller 0x157378 diverts on nonzero dispatcher return before response and bitmap copy'),
        limits=['dispatch tables are decoded independently of local graph BR frontiers',
                'request validation, parser 0x136eb0 and helper 0x138740 remain opaque',
                'other writers, memory aliases, initial bitmap and effects of opaque calls unknown',
                'partial workspace writes are not proof of global publication or image acceptance',
                'no firmware execution or token construction'])



if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot');args=parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as error:
        parser.exit(2,f'inspect_lk_token_modes: {error}\n')
