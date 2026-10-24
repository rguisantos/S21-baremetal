#!/usr/bin/env python3
"""Static frontier of the HZC2 EPBL prefix, refusing pending code bytes.

Explores both conditional paths; call fallthrough assumes normal return.
No exception-vector edges, MMIO, hardware or secure code are executed.
"""
import argparse
import hashlib
import json
import struct

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_epbl_preparation import evidence as preparation
from inspect_lk_final_edges import flow, signed
from inspect_monitor_preparation import word


def adr_target(data,pc,register):
    w=word(data,pc)
    if w & 0x9f00001f != 0x10000000 | register:
        raise ValueError('expected ADR to declared register')
    return pc+signed(((w>>29)&3)|(((w>>5)&0x7ffff)<<2),21)


def prefix_graph(data,roots,*,start=0x3000,end=0x4540,pending_range=(0x4700,0xfde0),bindings=None,limit=2048):
    low,high=pending_range
    if not 0<=start<end<=low<high<=len(data) or any(x%4 for x in (start,end,low,high)):
        raise ValueError('invalid prefix/pending code bounds')
    if type(limit) is not int or limit<=0:
        raise ValueError('invalid PC budget')
    bindings={} if bindings is None else bindings
    for pc,targets in bindings.items():
        if type(pc) is not int or pc%4 or not start<=pc<end or not targets:
            raise ValueError('invalid BR binding')
        if any(type(t) is not int or t%4 or not start<=t<end for t in targets):
            raise ValueError('bound target outside aligned prefix')
    todo=list(roots);seen={};frontier={};indirect={};exits={}
    if not todo:
        raise ValueError('prefix roots required')
    while todo:
        pc=todo.pop()
        if type(pc) is not int or pc%4 or not start<=pc<end:
            raise ValueError('PC outside aligned prefix')
        if pc in seen:
            continue
        if len(seen)>=limit:
            raise ValueError('prefix PC budget exceeded')
        w=word(data,pc);kind,target=flow(w,pc);seen[pc]=w
        if pc in bindings and kind!='br':
            raise ValueError('only declared BR table expansion is supported')
        if kind in ('b','bl','conditional'):
            if start<=target<end:
                todo.append(target)
            elif low<=target<high and target%4==0:
                frontier[pc]=dict(kind=kind,target=hex(target),target_executed=False)
            else:
                raise ValueError('unclassified control target')
        elif kind in ('br','blr'):
            targets=bindings.get(pc,[])
            indirect[pc]=dict(kind=kind,register=target,declared_targets=[hex(t) for t in targets])
            todo.extend(targets)
        elif kind in ('eret','exception_call','udf','ret'):
            exits[pc]=kind
            if kind=='udf':
                raise ValueError('UDF in prefix graph')
        if kind not in ('b','br','ret','eret','exception_call','udf'):
            todo.append(pc+4)
    packed=b''.join(struct.pack('<II',p,w) for p,w in sorted(seen.items()))
    ranges=[]
    for pc in sorted(seen):
        if ranges and ranges[-1][1]==pc:ranges[-1][1]=pc+4
        else:ranges.append([pc,pc+4])
    return dict(instruction_count=len(seen),instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
                file_ranges=[[hex(a),hex(b)] for a,b in ranges],
                pending_edges={hex(p):e for p,e in sorted(frontier.items())},
                indirect_edges={hex(p):e for p,e in sorted(indirect.items())},
                exits={hex(p):k for p,k in sorted(exits.items())},
                vbar_el3_write_sites=[hex(p) for p,w in sorted(seen.items()) if w==0xd51ec000],
                common_dispatcher_nodes_reached=any(p in seen for p in (0x43d8,0x4424,0x4494)),
                call_fallthrough_assumes_normal_return=True,exception_edges_modelled=False,
                path_feasibility_proven=False,runtime_execution_observed=False)


def evidence(path):
    data=read_exact(path,*IMAGES['sboot'])
    earlier=preparation(path)
    continuation=adr_target(data,0x3020,30)
    if continuation!=0x3028 or flow(word(data,0x3024),0x3024)!=('b',0x3128) or word(data,0x3128)!=0xd65f03c0:
        raise ValueError('entry ADR/RET veneer changed')
    if word(data,0x3c30)!=0xd61f0120 or word(data,0x3bcc)!=0x71000d1f:
        raise ValueError('bounded prefix table dispatch changed')
    entries=struct.unpack_from('<4b',data,0x4228)
    targets=sorted({0x3c34+4*x for x in entries})
    if any(not 0x3c34<=p<=0x3c40 for p in targets):
        raise ValueError('unexpected prefix jump table target')
    graph=prefix_graph(data,[continuation],bindings={0x3c30:targets})
    relative_vector=adr_target(data,0x3064,0)
    ldr=word(data,0x4354)
    if ldr & 0xff00001f != 0x58000000 or word(data,0x4358)!=0xd51ec000:
        raise ValueError('second vector writer changed')
    slot=0x4354+4*signed((ldr>>5)&0x7ffff,19)
    if slot<0 or slot%8 or slot+8>len(data):raise ValueError('invalid vector literal')
    literal_vector=struct.unpack_from('<Q',data,slot)[0]
    delta=literal_vector-relative_vector
    if delta!=int(earlier['nominal_mapping']['delta'],16):
        raise ValueError('independent nominal vector delta disagrees')
    blocks={'entry_veneer':(0x3020,0x3028),'entry_return':(0x3128,0x312c),
            'vbar_relative':(0x3064,0x3070),'vbar_literal_path':(0x4344,0x4364),
            'zero_return_helper':(0x431c,0x4324)}
    return dict(date='2026-10-23',mode='static_EPBL_prefix_frontier',sboot_sha256=IMAGES['sboot'][1],
                continuation=hex(continuation),prefix_bounds=['0x3000','0x4540'],
                pending_bounds=['0x4700','0xfde0'],prefix_graph=graph,
                table_expansion=dict(branch='0x3c30',table='0x4228',signed_bytes=list(entries),
                                     target_base='0x3c34',targets=[hex(p) for p in targets],
                                     bound_cmp='0x3bcc: CMP W8,#3'),
                vector_corroboration=dict(relative_writer='0x3068',relative_target_file_offset=hex(relative_vector),
                    literal_writer='0x4358',literal_slot=hex(slot),literal_value=hex(literal_vector),
                    matching_candidate_delta=hex(delta),pending_call_before_second_writer='0x4350 -> 0xc9ec',
                    physical_mapping_verified=False,vector_entries_verified=False),
                vector_window=dict(candidate_file_range=['0xe800','0xf000'],
                                   entirely_inside_pending_region=True,entries=16,stride=128,
                                   sha256=hashlib.sha256(data[0xe800:0xf000]).hexdigest(),
                                   decoded_as_runtime_code=False),
                classification_table_initialization_linked=False,actual_handler_linked=False,
                blocks={n:dict(start=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest())
                        for n,(a,b) in blocks.items()},
                firmware_executed=False,physical_device_tested=False,
                limitations=['Graph omits exception entry and does not prove the dispatcher unreachable at runtime',
                             'Conditional paths may be infeasible; pending calls are not executed, return is assumed for their continuation',
                             'Only one fixed four-byte jump table is expanded; BR X0 remains a conservative frontier',
                             'Second VBAR path contains a pending call; matched nominal targets are not physical state',
                             'Pending bytes, classification contents and hardware transformation remain unverified'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');args=p.parse_args()
    try:
        print(json.dumps(evidence(args.sboot),indent=2))
    except (OSError,ValueError,struct.error) as exc:
        p.exit(2,'EPBL frontier audit failed: '+str(exc)+'\n')
