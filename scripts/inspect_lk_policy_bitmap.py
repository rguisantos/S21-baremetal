#!/usr/bin/env python3
"""Static HZC2 token bitmap producer and readers. No firmware execution."""
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
    'bit_getter': (0x157230, 0x15726c),
    'export_bitmap': (0x157270, 0x157280),
    'word_getter': (0x157578, 0x157588),
    'get_token_mode': (0x157280, 0x157578),
    'prepare_payload': (0x156c00, 0x156d38),
    'cleanup': (0x156b70, 0x156c00),
    'read_token': (0x156e98, 0x156f48),
    'response_entry_fragment': (0x1427d8, 0x14282c),
    'response_gate_fragment': (0x142898, 0x1428b8),
    'response_copy_fragment': (0x1429a8, 0x1429cc),
    'caller_fragment': (0x158224, 0x158244),
    'caller_return_fragment': (0x1580f0, 0x158108),
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
               (0x23cb20,0x23e068,0x242df8,0x242e88,0x242ea8,0x238cb0,0x242190,0x2421a8,0x242130,0x242168)}
    packed = b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    return dict(mode='static_token_bitmap',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        gnu_words=len(lines),gnu_relative_targets=len(branches),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc):dict(word=f'{raw:08x}',op=op,args=args)
                      for pc,(raw,op,args) in sorted(lines.items())},
        branches=branches,strings=strings,local_graphs=graphs,
        interpretation=dict(
            bitmap_relative_address='0xcd6618', bitmap_bytes=32,
            getters='bit getter 0x157230; word getter 0x157578; 32-byte exporter 0x157270',
            nonnegative_index_formula='u64[B + 8*(index//64)] >> (index%64) & 1',
            index_validation_in_firmware=False,
            context_pointer_slots={'request':'0xcd6500','workspace':'0xcd64f0','response':'0xcd6608'},
            producer='0x1573e0 copies 32 bytes from reloaded response+0x120 to bitmap',
            response_copy='0x1429c0 copies workspace+0x29f68 to response+0x120 when workspace+16 bit5 is set',
            publication_checks=['0x1427d8 normal return W0=0','response+0 u32=0','response+24 bit5 set'],
            storage_label='STEADY', token_prefix_label='ENG',
            cleanup='selected body clears/frees three context buffers and zeroes their pointer slots, not the bitmap directly',
            unchanged_on_local_bypass='no direct clearing of bitmap in get_token_mode before copy; opaque effects remain unknown'),
        limits=['fragment graphs are local slices, not complete functions or a global path proof',
                'workspace producer 0x132130, storage I/O, other helpers and runtime values remain open',
                'no proof of signature acceptance, RAM retention, active token or physical loading',
                'no complete inventory of writers, aliases, or mutation through opaque calls'])



if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot');args=parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as error:
        parser.exit(2,f'inspect_lk_policy_bitmap: {error}\n')
