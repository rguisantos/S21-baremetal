#!/usr/bin/env python3
"""Audit selected fixed copies and parameterized-copy entry points. Static only."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_descriptor_provenance import COPY_LOOPS, copy_loop, overlap, wide_candidates
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_consumers_hzc2 import branch_candidates, occurrences

CELL=0x0211b580
TABLE=(0x0211b408,0x0211b588)
EXTRA=((0x1db1c,0x1db30),(0x1db44,0x1db5c),(0x1fcc4,0x1fce8),(0x2e8a0,0x2e8bc))


def project_cell(source,end,destination,cell,width=8):
    """Project a whole field only; half-open, unsigned, non-wrapping intervals."""
    if any(type(v) is not int for v in (source,end,destination,cell,width)):
        raise ValueError('integer interval required')
    if not (0<=source<end<=1<<64 and 0<=destination<1<<64 and width>0 and
            0<=cell<1<<64 and cell+width<=1<<64 and destination+end-source<=1<<64):
        raise ValueError('invalid unsigned interval')
    return destination+cell-source if source<=cell and cell+width<=end else None


def inspect(path):
    data=read_exact(path,*IMAGES['sboot'])
    copies=[]
    for pc,stride in COPY_LOOPS:
        c=copy_loop(data,pc,stride)
        src,end=map(lambda x:int(x,16),c['source']);dst,dend=map(lambda x:int(x,16),c['destination'])
        projected=project_cell(src,end,dst,CELL)
        copies.append(dict(**c,source_overlaps_table=overlap(src,end,*TABLE),
            destination_overlaps_table=overlap(dst,dend,*TABLE),
            projected_cell=None if projected is None else hex(projected)))
    calls=branch_candidates(data,0x1fcc4,last=0xec000)
    ranges=[(pc,pc+40) for pc,_ in COPY_LOOPS]+list(EXTRA)
    # Include each parameterized B/BL word; do not infer its argument values.
    pcs={pc for a,b in ranges for pc in range(a,b,4)}|{int(c['pc'],16) for c in calls}
    ordered=sorted(pcs);runs=[]
    for pc in ordered:
        if runs and runs[-1][1]==pc:runs[-1][1]=pc+4
        else:runs.append([pc,pc+4])
    root=Path(__file__).resolve().parent.parent
    command=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
             str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for a,b in runs:
        lines.update(parse_lines(subprocess.check_output(command+['-D','-b','binary','-m','aarch64',
            f'--start-address={a}',f'--stop-address={b}',str(Path(path).resolve())],text=True)))
    if set(lines)!=pcs:raise ValueError('GNU coverage differs')
    relative=0
    for pc,(raw,op,args) in lines.items():
        if raw!=struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):raise ValueError('GNU word differs')
        kind,target=flow(raw,pc)
        if kind in ('b','bl','conditional'):
            if target!=direct_target(op,args):raise ValueError('GNU target differs')
            relative+=1
    selected={0x1db1c:('adrp','x1, 0x31000'),0x1db28:('add','x1, x1, #0x630'),
        0x1db48:('adrp','x1, 0x31000'),0x1db4c:('mov','w2, #0x20'),
        0x1db50:('add','x1, x1, #0x668'),0x2e8a4:('mov','x1, #0xb6a4'),
        0x2e8a8:('mov','w2, #0x34'),0x2e8ac:('movk','x1, #0x21a, lsl #16'),
        0x1fcd4:('ldrb','w4, [x1, x3]'),0x1fcd8:('strb','w4, [x0, x3]'),
        0x1fce0:('b','0x1fcc8')}
    for pc,operand in selected.items():
        if lines[pc][1:]!=operand:raise ValueError(f'operand differs at{pc:#x}')
    values=(TABLE[0],CELL,0x02117364)
    packed=b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in ordered)
    return dict(mode='static_newtime_transports',sboot_sha256=IMAGES['sboot'][1],
        cell_file='0x31580',nominal_delta='0x020ea000',cell_nominal=hex(CELL),
        table_window=[hex(x) for x in TABLE],fixed_copies=copies,
        parameterized_copy_candidates=dict(target='0x1fcc4',first='0x16000',end_exclusive='0xec000',
            aligned_words=(0xec000-0x16000)//4,B=sum(c['kind']=='b' for c in calls),
            BL=sum(c['kind']=='bl' for c in calls),sites=calls,
            selected_argument_windows=[dict(call='0x1db2c',source_nominal='0x0211b630',
                length='W19, not reconstructed here',whole_cell_transport=False),
                dict(call='0x1db58',source_nominal='0x0211b668',bytes=32,whole_cell_transport=False),
                dict(call='0x2e8b8',source_nominal='0x021ab6a4',bytes=52,whole_cell_transport=False)],
            other_sites_not_analyzed=len(calls)-3),
        extended_direct_target_candidates=branch_candidates(data,0x2d364,last=0xec000),
        literal_occurrences={hex(v):{str(w):[hex(x) for x in occurrences(data,v.to_bytes(w,'little'))]
            for w in (4,8)} for v in values},
        wide_move_candidates=wide_candidates(data,set(values)),
        gnu_words=len(lines),gnu_relative_targets=relative,selected_operands=len(selected),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        witnesses=[dict(pc=hex(pc),word=f'{w:08x}',op=op,args=args) for pc,(w,op,args) in sorted(lines.items())],
        limits=['only seven exact fixed-copy bodies, literal parameters and nominal mapping',
                'source non-overlap excludes transporting these field bytes, not writes through unknown destinations',
                'parameterized copies, aliases, received bases and other modules remain open',
                'aligned B/BL and selected wide-move encodings are candidates, not full reachability',
                'no export, indirect caller, incoming X0 or runtime preservation established'],
        transport_of_cell_found=False,incoming_X0_resolved=False,firmware_executed=False,qemu_scope_extended=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:result=inspect(args.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:parser.exit(2,f'{exc}\n')
    print(json.dumps(result,indent=2))
