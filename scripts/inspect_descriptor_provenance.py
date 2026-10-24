#!/usr/bin/env python3
"""Bounded static witnesses for the HZC2 descriptor's unresolved prior state.

No generic writer proof, memory initialization, secure service or firmware
execution. Copy intervals describe fixed loops only, not a measured boot path.
"""
import argparse
import hashlib
import json
import struct

from inspect_bl2_service_chain import DESCRIPTOR, descriptor_request
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow, signed
from inspect_monitor_preparation import branch_candidates, word

COPY_LOOPS = ((0x161b0,16),(0x161d8,4),(0x16200,4),(0x16228,16),
              (0x16250,16),(0x16278,16),(0x162b4,16))
LIMIT = 0xe7fffe00


def overlap(a,b,c,d):
    if not 0 <= a < b <= 1 << 64 or not 0 <= c < d <= 1 << 64:
        raise ValueError('requires nonempty unsigned intervals')
    return a < d and c < b


def copy_loop(data, start, stride):
    """Match three LDR X literal producers and a fixed do/while copy body."""
    if stride not in (4,16):
        raise ValueError('unsupported copy stride')
    values, literals = [], []
    for register in range(3):
        pc=start+register*4;w=word(data,pc)
        if w & 0xff00001f != 0x58000000 | register:
            raise ValueError('expected LDR X literal for copy parameter')
        at=pc+signed((w >> 5)&0x7ffff,19)*4
        if at < 0 or at % 8 or at+8 > len(data):
            raise ValueError('copy literal outside aligned bytes')
        literals.append(hex(at));values.append(struct.unpack_from('<Q',data,at)[0])
    expected = ((0xa8c11003,0xa8811043) if stride==16 else (0xb8404403,0xb8004443))
    expected += (0xeb01001f,0x54ffffab,0xd5033f9f,0xd5033fdf,0xd65f03c0)
    if tuple(word(data,start+12+i*4) for i in range(7)) != expected:
        raise ValueError('unsupported copy loop or barriers')
    src,end,dst=values
    if not 0 <= src < end < 1 << 63 or dst >= 1 << 63 or (end-src)%stride:
        raise ValueError('unsupported signed copy bounds or partial iteration')
    size=end-src
    if dst+size > 1 << 64:
        raise ValueError('copy destination overflow')
    return dict(start=hex(start), end_exclusive=hex(start+40), literal_offsets=literals,
                source=[hex(src),hex(end)], destination=[hex(dst),hex(dst+size)],
                stride=stride, iterations=size//stride, bytes=size,
                destination_overlaps_descriptor=overlap(dst,dst+size,DESCRIPTOR,DESCRIPTOR+28),
                loop_execution_observed=False,
                code_sha256=hashlib.sha256(data[start:start+40]).hexdigest())


def wide_candidates(data, targets, start=0, end=None):
    """MOVZ X + up to three instructions ending in MOVK X, high half 16.

    Only other-register wide moves, W register moves, and the exact FP/stack
    prologue may intervene. Unsupported instructions invalidate the witness.
    The scan is of aligned words, not all possible code or address producers.
    """
    end=len(data) if end is None else end
    if not 0 <= start < end <= len(data) or start%4 or end%4:
        raise ValueError('invalid address scan bounds')
    found=[]
    for pc in range(start,end-4,4):
        w=word(data,pc)
        if w & 0xffe00000 != 0xd2800000 or w & 31 == 31:
            continue
        reg=w&31;low=(w>>5)&65535
        for gap in (4,8,12):
            if pc+gap >= end:
                break
            m=word(data,pc+gap)
            if m & 0xffe0001f == 0xf2a00000 | reg:
                address=low|(((m>>5)&65535)<<16)
                if address in targets:
                    found.append(dict(movz=hex(pc),movk=hex(pc+gap),register=f'x{reg}',address=hex(address)))
                break
            safe = ((m & 0x7f800000 in (0x12800000,0x52800000,0x72800000) or
                     m & 0xffe0ffe0 == 0x2a0003e0) and m & 31 not in (reg,31))
            safe |= m == 0xa9bf7bfd and reg != 31
            safe |= m == 0x910003fd and reg != 29
            if not safe:
                break
    return found


def evidence(path):
    data=read_exact(path,*IMAGES['sboot'])
    if data[0x1643c:0x164c8] != data[0x36154:0x361e0]:
        raise ValueError('descriptor constructor copies differ')
    copies=[]
    for mode in (0,0x14,0x20,0x40):
        a=descriptor_request(data,mode)
        b=descriptor_request(data,mode,start=0x36154,veneer=0x36138)
        if (a['registers'],a['fields']) != (b['registers'],b['fields']):
            raise ValueError('duplicate constructor behavior differs')
        copies.append(dict(mode=hex(mode),registers_equal=True,fields_equal=True,
                           unknown_offsets=[off for off,v in a['fields'].items() if v is None]))
    limit_blocks=((0x12e220,0x12e240),(0x12e2a0,0x12e2b8),
                  (0x12e6d8,0x12e6ec),(0x12e93c,0x12e954))
    blocks={'constructor_a':(0x1643c,0x164c8),'constructor_b':(0x36154,0x361e0)}
    blocks.update({f'lk_limit_{i}':bounds for i,bounds in enumerate(limit_blocks)})
    return dict(date='2026-10-23',mode='static_descriptor_prior_state_audit',sboot_sha256=IMAGES['sboot'][1],
                descriptor_window=[hex(DESCRIPTOR),hex(DESCRIPTOR+28)],
                copies_byte_identical=True,duplicate_constructor_checks=copies,
                direct_branch_candidates={hex(target):branch_candidates(data,target,0x16000,0xec000)
                                          for target in (0x1643c,0x36154)},
                literal_byte_matches={hex(target):{str(width):[hex(pc) for pc in range(len(data)-width+1)
                    if data[pc:pc+width] == target.to_bytes(width,'little')] for width in (4,8)}
                    for target in (DESCRIPTOR,LIMIT)},
                wide_address_candidates=wide_candidates(data,{DESCRIPTOR,LIMIT}),
                fixed_copy_loops=[copy_loop(data,pc,stride) for pc,stride in COPY_LOOPS],
                lk_limit=dict(value=hex(LIMIT),distance_above_descriptor=hex(LIMIT-DESCRIPTOR),
                              use='SUB / CMP / conditional branch, not a descriptor store',
                              memory_ownership_proven=False),
                blocks={name:dict(start=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest())
                        for name,(a,b) in blocks.items()},
                initializer_identified=False,prior_field_values_known=False,complete_writer_census=False,
                firmware_executed=False,physical_device_tested=False,
                limitations=['Only seven fixed copy bodies and declared MOVZ/MOVK/LDR literal forms are matched',
                             'Aligned word candidates do not prove code reachability or exclude other encodings/aliases',
                             'No direct B/BL to a copy does not prove that copy unreachable after relocation or via pointers',
                             'Non-overlap of selected loops does not exclude arbitrary writes, secure service effects or earlier stages',
                             'LK comparison limit is not RAM ownership, free memory or a descriptor initialization guarantee'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:
        print(json.dumps(evidence(args.sboot),indent=2))
    except (OSError,ValueError,struct.error) as exc:
        parser.exit(2,'Descriptor provenance audit failed: '+str(exc)+'\n')
