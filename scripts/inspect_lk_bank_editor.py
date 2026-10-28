#!/usr/bin/env python3
"""Static HZC2 zero-size bank writer and FDT editor evidence. No execution."""
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
    'constructor_zero_size_fragment': (0xfaf28, 0xfaf5c),
    'create_node_helper': (0xf12c8, 0xf13ac),
    'property_helper': (0xf13b0, 0xf156c),
    'bank_writer': (0xf1570, 0xf164c),
    'set_property': (0x11fb48, 0x11fbb4),
    'add_subnode': (0x11fbb8, 0x11fce0),
    'add_subnode_name_wrapper': (0x11fce0, 0x11fd24),
    'walker_decode_callback_fragment': (0x148d08, 0x148d38),
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
               (0x20e520,0x20e530,0x20e540,0x20e558,0x20e560,0x20e568)}
    packed = b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    return dict(mode='static_lk_bank_editor',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        gnu_words=len(lines),gnu_relative_targets=len(branches),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc):dict(word=f'{raw:08x}',op=op,args=args)
                      for pc,(raw,op,args) in sorted(lines.items())},
        branches=branches,strings=strings,local_graphs=graphs,
        interpretation=dict(
            writer='0xf1570', zero_size_filtered=False,
            create_call='0xf15b8 -> 0xf12c8',
            reg_call='0xf1608 -> 0xf13b0',
            device_type_call='0xf1634 -> 0xf13b0',
            reg_cells='base high32, base low32, size low32; three big-endian cells',
            create_and_reg_returns_checked=False,
            final_return='W0 from last device_type helper; no composite status',
            rollback='no local rollback of earlier successful edits',
            walker='first 12 bytes of reg forwarded; no local zero-size filter'),
        limits=['Static graphs leave calls opaque; QEMU report tests synthetic editor effects separately',
                'No final device FDT or successful physical execution inferred',
                'No later firmware edits, Linux memory admission or uH acceptance established'])




if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot');args=parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as error:
        parser.exit(2,f'inspect_lk_bank_editor: {error}\n')
