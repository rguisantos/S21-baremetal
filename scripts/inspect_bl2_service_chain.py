#!/usr/bin/env python3
"""Hash-bound BL2 caller models: explicit X2 input, partial descriptor writes.

Interprets only a small constructor in host memory; never executes a secure
service or supplies a measured response. Unknown descriptor fields stay unknown.
"""
import argparse
import hashlib
import json
import struct

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import DELTA, END, START, flow, signed
from inspect_monitor_preparation import word

U64 = (1 << 64) - 1
DESCRIPTOR = 0xe7ffe000


def unsigned(value, bits):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'explicit unsigned {bits}-bit input required')
    return value


def select_mode(response_x2, table):
    """W0 truncation, UBFIZ, LSRV W (shift modulo 32), unsigned table bound."""
    value = unsigned(response_x2, 64) & 0xffffffff
    if not isinstance(table, (bytes, bytearray)) or len(table) != 11:
        raise ValueError('requires eleven byte entries')
    shift = ((value & 15) << 2) & 31
    nibble = (value >> shift) & 15
    index = (nibble - 1) & 0xffffffff
    return dict(response_x2=hex(response_x2), w0=hex(value), shift=shift,
                nibble=nibble, table_index=index if index <= 10 else None,
                mode_w19=hex(table[index] if index <= 10 else 0),
                response_is_measured=False)


def descriptor_request(data, mode, *, start=0x1643c, veneer=0x16420):
    """Restricted A64 constructor interpreter, stopping before secure BL.

Unknown registers cannot be read. Only the fixed 28-byte descriptor window
can receive W stores. Stack prologue and frame-pointer setup are validated
and abstracted; no guest stack or physical address is touched.
"""
    if word(data,start+8) != 0xa9bf7bfd or word(data,start+0x14) != 0x910003fd:
        raise ValueError('unexpected abstracted stack prologue')
    regs = [None] * 31 + [0]
    regs[0] = unsigned(mode, 32)
    writes, fields, pcs = [], {}, []
    pc, equal = start, None

    def get(reg):
        if regs[reg] is None:
            raise ValueError('unknown register input')
        return regs[reg]

    def put(reg, value, width):
        if reg == 31:
            raise ValueError('unsupported destination register')
        regs[reg] = value & ((1 << width) - 1)

    for _ in range(64):
        if not start <= pc < start + 0x8c or pc in pcs:
            raise ValueError('constructor escaped bounds or looped')
        pcs.append(pc)
        w = word(data, pc)
        kind, target = flow(w, pc)
        if kind == 'bl':
            if target != veneer or (word(data, veneer), word(data, veneer+4)) != (0xd4000003, 0xd65f03c0):
                raise ValueError('unexpected secure boundary')
            return dict(mode_w0=hex(mode), registers={f'x{i}': hex(get(i)) for i in range(4)},
                        descriptor_address=hex(DESCRIPTOR),
                        fields={hex(i): hex(fields[i]) if i in fields else None for i in range(0,28,4)},
                        writes=writes, instruction_offsets=[hex(p) for p in pcs],
                        stopped_before_smc=True, unknown_fields_are_inherited=True)
        if pc == start+8 and w == 0xa9bf7bfd:
            pass
        elif pc == start+0x14 and w == 0x910003fd:
            pass
        elif w & 0x7f800000 in (0x12800000, 0x52800000, 0x72800000):
            width = 64 if w >> 31 else 32
            shift = ((w >> 21) & 3) * 16
            if shift >= width:
                raise ValueError('invalid move-wide shift')
            rd, val, op = w & 31, ((w >> 5) & 0xffff) << shift, w & 0x7f800000
            if op == 0x12800000:
                val = ~val
            elif op == 0x72800000:
                val |= get(rd) & ~(0xffff << shift)
            put(rd, val, width)
        elif w & 0xffe0ffe0 == 0x2a0003e0:
            put(w & 31, get((w >> 16) & 31), 32)
        elif w & 0xffc003ff == 0x7100001f:
            equal = (get(0) & 0xffffffff) == ((w >> 10) & 4095)
        elif w & 0x7f000000 == 0x35000000 and w & 31 == 0:
            if get(0) & (U64 if w >> 31 else 0xffffffff):
                pc = target
                continue
        elif w & 0xff000010 == 0x54000000 and w & 15 == 1:
            if equal is None:
                raise ValueError('unknown condition flags')
            if not equal:
                pc = target
                continue
        elif kind == 'b':
            pc = target
            continue
        elif w & 0xffc00000 in (0xb9000000, 0x29000000):
            pair = w & 0xffc00000 == 0x29000000
            offset = signed((w >> 15) & 127,7)*4 if pair else ((w >> 10) & 4095)*4
            address = get((w >> 5) & 31) + offset
            stores = [(address, get(w & 31) & 0xffffffff)]
            if pair:
                stores.append((address+4, get((w >> 10) & 31) & 0xffffffff))
            for at, value in stores:
                if not DESCRIPTOR <= at <= DESCRIPTOR+24 or at % 4:
                    raise ValueError('store outside descriptor window')
                fields[at-DESCRIPTOR] = value
                writes.append(dict(pc=hex(pc), offset=hex(at-DESCRIPTOR), value=hex(value)))
        else:
            raise ValueError(f'unsupported constructor instruction {w:08x} at {pc:#x}')
        pc += 4
    raise ValueError('constructor instruction budget exceeded')


def address_candidates(data, targets, start=START, end=END):
    """Narrow ADRP + ADD witnesses, optionally separated by one safe X MOV.

    These are address producers, not a writer census or pointer-flow proof.
    A MOV to the ADRP base invalidates the candidate. Other intervening
    instructions are deliberately not interpreted.
    """
    if not 0 <= start < end <= len(data) or start % 4 or end % 4:
        raise ValueError('invalid code scan bounds')
    result=[]
    for pc in range(start,end-4,4):
        w=word(data,pc)
        if w & 0x9f000000 != 0x90000000:
            continue
        base=w & 31
        if base == 31:
            continue
        page=(pc & ~4095)+(signed(((w >> 29)&3)|(((w >> 5)&0x7ffff)<<2),21)<<12)
        for gap in (4,8):
            if pc+gap >= end:
                break
            if gap == 8:
                m=word(data,pc+4)
                if m & 0xffe0ffe0 != 0xaa0003e0 or m & 31 in (base,31):
                    break
            add=word(data,pc+gap)
            if add & 0xffc00000 != 0x91000000 or (add >> 5)&31 != base or add & 31 == 31:
                continue
            address=page+((add >> 10)&4095)
            if address in targets:
                result.append(dict(adrp=hex(pc),add=hex(pc+gap),address_file_offset=hex(address)))
    return result


def evidence(path, response_x2=None):
    data = read_exact(path, *IMAGES['sboot'])
    table = data[0x2fdf8:0x2fe03]
    # Explicit gate witnesses: the getter copies X2 after SMC; do not substitute X0.
    expected = {0x16554:0x92801d00, 0x16428:0xd2800002, 0x1642c:0xd5033f9f,
                0x16430:0xd4000003, 0x16434:0xaa0203e0, 0x16438:0xd65f03c0}
    if any(word(data,p) != w for p,w in expected.items()):
        raise ValueError('getter response provenance changed')
    blocks = {'getter':(0x1654c,0x16568), 'x2_return_veneer':(0x16428,0x1643c),
              'descriptor_constructor':(0x1643c,0x164c8), 'optional_request':(0x164c8,0x16500),
              'caller':(0x1cb04,0x1cb80), 'intermediate_mmio_write':(0x1caf4,0x1cb04),
              'epbl_vector_install':(0x3064,0x3070), 'epbl_vector_raw':(0xe800,0xe820),
              'stdout_cell_address':(0x170154,0x17016c),
              'stream_array_address':(0x1b154c,0x1b1578)}
    return dict(date='2026-10-23', mode='read_only_BL2_caller_model', sboot_sha256=IMAGES['sboot'][1],
                mode_table=dict(offset='0x2fdf8', bytes_hex=table.hex(), values=list(table)),
                getter=dict(service_id='-0xe9', veneer='0x16428', input_x1='0x0',
                            initial_x2='0x0', result_register='x2', caller_consumes='w0 after MOV X0,X2',
                            service_x2_preservation_known=False, actual_response_known=False),
                supplied_response=select_mode(response_x2, table) if response_x2 is not None else None,
                nibble_cases=[dict(nibble=n, mode_w19=hex(table[n-1] if 1<=n<=11 else 0)) for n in range(16)],
                descriptor_requests=[descriptor_request(data,m) for m in sorted(set(table))],
                optional_request=dict(service_id='-0xed', skip_if_mode='0x40',
                                      x1='0xf0005000', x2='0x2000',
                                      x3_by_mode={'0x0':'0x751','0x20':'0xea','other':'0x0'},
                                      caller_does_not_test_return=True),
                caller_checks=dict(descriptor_service='-0xe6', response_test='W0==0 at 0x1cb58',
                                   nonzero_self_loop='0x1cb5c', next_mmio_write='0x1caf4',
                                   next_service='-0xe7', final_response_test='W0==0 at 0x1cb6c'),
                epbl_boundary=dict(vbar_adr='0x3064', vector_file_offset='0xe800',
                                   first_word=f'{word(data,0xe800):08x}',
                                   handler_linked=False, bytes_proven_plaintext_code=False),
                console_initial_references=dict(
                    address_producer_candidates=address_candidates(data,{0x31ffe8,0x31fff0,0x3218b0,0x3218b8,0x2906f8,0x3218c0}),
                    aligned_initial_pointer_cells={hex(target):[hex(p) for p in range(START,0x36c000,8)
                        if struct.unpack_from('<Q',data,p)[0] == DELTA+target]
                        for target in (0x3218b0,0x2906f8,0x3218c0)},
                    pointer_or_list_immutability_proven=False),
                blocks={n:dict(start=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest())
                        for n,(a,b) in blocks.items()},
                secure_service_executed=False, runtime_observed=False,
                memory_ownership_proven=False, physical_device_tested=False,
                limitations=['X2 and descriptor residuals are not measured; initial X2=0 is not a response',
                             'W shift wraps modulo 32; full X2 is not shifted as a 64-bit value',
                             'Constructor model does not execute BL, stack accesses, MMIO or secure firmware',
                             'Storage units, service actions and secure dispatch remain unresolved',
                             'Address/pointer scans cover only declared encodings and alignment, not aliases, indirect writers or runtime mutation'])


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sboot');p.add_argument('--response-x2',type=lambda s:int(s,0))
    args=p.parse_args()
    try:
        print(json.dumps(evidence(args.sboot,args.response_x2),indent=2))
    except (OSError,ValueError,struct.error) as exc:
        p.exit(2,'BL2 caller audit failed: '+str(exc)+'\n')
