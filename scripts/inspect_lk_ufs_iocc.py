#!/usr/bin/env python3
"""Bound selected UFS PHY/IOCC writes; do not infer live DMA coherence."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES,read_exact
from inspect_lk_build_id import page_plus_add
from inspect_lk_payload_return import summarize_local
from inspect_lk_precopy_measurement import verify_disassembly
from inspect_lk_ufs_host import u64_table

BLOCKS={
    'first_query':(0x10e868,0x10e878),
    'table_pointer_loads':(0x10e8a4,0x10e8ac),
    'phy_and_iocc':(0x10e8c8,0x10e8f4),
    'second_query_and_alternate_mask':(0x10eba8,0x10ebcc),
    'configuration_getter':(0x147ea8,0x147eb4),
}
SELECTED={
    0x10e868:('bl','0x147ea8'),0x10e86c:('cbnz','w0, 0x10eba8'),
    0x10e870:('adrp','x20, 0x303000'),0x10e874:('add','x20, x20, #0x198'),
    0x10e8a4:('ldr','x0, [x20, #56]'),0x10e8a8:('ldp','x3, x4, [x20, #40]'),
    0x10e8c8:('ldr','w0, [x3]'),0x10e8cc:('orr','w0, w0, #0x1'),
    0x10e8d0:('str','w0, [x3]'),0x10e8d4:('cbz','x4, 0x10e8f4'),
    0x10e8d8:('bl','0x147ea8'),0x10e8dc:('cmp','w0, #0x1'),
    0x10e8e0:('ldr','x1, [x20, #48]'),0x10e8e4:('ldr','w0, [x1]'),
    0x10e8e8:('b.eq','0x10ebc0'),0x10e8ec:('orr','w0, w0, #0xc00000'),
    0x10e8f0:('str','w0, [x1]'),0x10eba8:('bl','0x147ea8'),
    0x10ebac:('cmp','w0, #0x1'),0x10ebb0:('b.ne','0x10e870'),
    0x10ebb4:('adrp','x20, 0x303000'),0x10ebb8:('add','x20, x20, #0x8d8'),
    0x10ebbc:('b','0x10e878'),0x10ebc0:('orr','w0, w0, #0x300000'),
    0x10ebc4:('str','w0, [x1]'),0x10ebc8:('b','0x10e8f4'),
    0x147ea8:('adrp','x0, 0xcd3000'),0x147eac:('ldr','w0, [x0, #456]'),
    0x147eb0:('ret',''),
}


def u32(value):
    if type(value) is not int or not 0<=value<1 << 32:raise ValueError('u32 required')
    return value


def select_table(first,second=None):
    """Values from distinct getter calls; second call is skipped if first=0."""
    u32(first)
    if first==0:
        if second is not None:raise ValueError('second query is not executed')
        return 0x303198
    u32(second)
    return 0x3038d8 if second==1 else 0x303198


def selected_writes(phy_before,iocc_before,query,*,enabled=True):
    u32(phy_before);u32(iocc_before);u32(query)
    if type(enabled) is not bool:raise ValueError('boolean gate required')
    mask=(0x300000 if query==1 else 0xc00000) if enabled else 0
    return dict(phy_after=phy_before|1,iocc_after=iocc_before|mask,
                iocc_or_mask=mask,iocc_store_executed=enabled)


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for a,b in BLOCKS.values():
        parsed=parse_lines(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','aarch64',f'--start-address={a}',f'--stop-address={b}',str(Path(path).resolve())],text=True))
        if lines.keys() & parsed.keys():raise ValueError('duplicate GNU PC')
        lines.update(parsed)
    branches=verify_disassembly(data,lines,BLOCKS,SELECTED)
    words={p:r[0] for p,r in lines.items()}
    _,primary=page_plus_add(words,0x10e870,0x10e874)
    _,alternate=page_plus_add(words,0x10ebb4,0x10ebb8)
    tables=[dict(file_offset=hex(p),phy=hex(v[5]),iocc_candidate=hex(v[6]),pad=hex(v[7]))
            for p in (primary,alternate) for v in [u64_table(data,p,8)]]
    if tables!=[dict(file_offset='0x303198',phy='0x15860728',iocc_candidate='0x13020700',pad='0x13040020'),
                dict(file_offset='0x3038d8',phy='0x15860728',iocc_candidate='0x11020700',pad='0x11040040')]:
        raise ValueError('selected table values differ')
    packed=b''.join(struct.pack('<II',p,r[0]) for p,r in sorted(lines.items()))
    return dict(mode='static_lk_ufs_phy_and_iocc_candidates',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,dma_coherence_established=False,
        gnu_words=len(lines),gnu_relative_targets=len(branches),selected_operand_checks=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        blocks={k:dict(start=hex(a),end_exclusive=hex(b)) for k,(a,b) in BLOCKS.items()},
        selected_instructions={hex(p):dict(word=f'{lines[p][0]:08x}',op=op,args=args) for p,(op,args) in sorted(SELECTED.items())},
        branches=branches,local_graphs={k:summarize_local(data,a,a,b) for k,(a,b) in BLOCKS.items()},
        configuration_tables=tables,query_storage_relative='0xcd31c8',
        selection=dict(first_zero='primary without second call',first_nonzero='second call selects alternate iff W0=1',
            third_query='independent later read selects OR mask 0x300000 iff W0=1, else 0xc00000',stability_observed=False),
        stores=dict(phy='0x10e8d0: old u32 OR1 at table+40 pointer',
            iocc='0x10e8f0 or0x10ebc4: old u32 OR selected mask at table+48 pointer',
            gate='X4 (loaded from table+48) zero skips the later query/read/store; both pinned tables contain nonzero pointers',
            clearing_old_bits=False),
        limits=['Selected local writes only; no census of all MMIO writers or preservation after initialization.',
            'The three getter calls read the same u32 storage at different times; producer, live value and stability remain open.',
            'The alternate address/mask can be cross-checked against a pinned kernel reference; primary address meaning is not established by that match.',
            'Nominal OR stores are not readback, IOCC activation, cache snooping, SMMU bypass or proof of coherent DMA.'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');args=p.parse_args()
    try:print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as exc:p.exit(2,f'inspect_lk_ufs_iocc: {exc}\n')
