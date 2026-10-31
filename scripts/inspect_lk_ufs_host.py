#!/usr/bin/env python3
"""Inspect pinned HZC2 UFS host/buffer origins and raw address programming."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_avb_boot import wide_constant
from inspect_lk_avb_trust import load_x
from inspect_lk_build_id import load_unsigned_w, page_plus_add
from inspect_lk_embedded_key import adrp
from inspect_lk_final_edges import flow
from inspect_lk_payload_return import summarize_local
from inspect_lk_precopy_measurement import verify_disassembly
from inspect_lk_samsung_checks import store_unsigned_x


BLOCKS = {
    'host_and_buffer_allocator': (0x10ec98, 0x10ede8),
    'host_initialize': (0x10e7c8, 0x10ec30),
    'malloc_wrapper': (0x18fd50, 0x18fd90),
    'aligned_malloc_wrapper': (0x18fd90, 0x18fde8),
    'gateway': (0x10e758, 0x10e7c8),
}
SELECTED = {
    0x10e768: ('adrp', 'x21, 0x8a7000'),
    0x10e770: ('adrp', 'x20, 0x8a7000'),
    0x10e778: ('add', 'x20, x20, #0x718'),
    0x10e780: ('ldr', 'w1, [x21, #1808]'),
    0x10e788: ('ldr', 'x0, [x20, w1, sxtw #3]'),
    0x10e7a0: ('b', '0x10e568'),
    0x10e834: ('adrp', 'x21, 0x8a7000'),
    0x10e844: ('ldr', 'x19, [x21, #1816]'),
    0x10e86c: ('cbnz', 'w0, 0x10eba8'),
    0x10e874: ('add', 'x20, x20, #0x198'),
    0x10e878: ('ldr', 'x0, [x20]'),
    0x10e880: ('str', 'x0, [x19, #24]'),
    0x10e884: ('ldr', 'x0, [x20, #8]'),
    0x10e888: ('str', 'x0, [x19, #32]'),
    0x10e88c: ('ldr', 'x0, [x20, #16]'),
    0x10e890: ('str', 'x0, [x19, #40]'),
    0x10e894: ('ldr', 'x0, [x20, #24]'),
    0x10e898: ('str', 'x0, [x19, #48]'),
    0x10e89c: ('ldr', 'x0, [x20, #32]'),
    0x10e8a0: ('str', 'x0, [x19, #64]'),
    0x10e8a8: ('ldp', 'x3, x4, [x20, #40]'),
    0x10e8ac: ('ldr', 'w1, [x0, #8]'),
    0x10e8b4: ('str', 'w1, [x0, #8]'),
    0x10e8c4: ('str', 'w1, [x0]'),
    0x10e8d0: ('str', 'w0, [x3]'),
    0x10e8e8: ('b.eq', '0x10ebc0'),
    0x10e8f0: ('str', 'w0, [x1]'),
    0x10e8fc: ('bl', '0xef580'),
    0x10e91c: ('bl', '0x18fd50'),
    0x10e92c: ('str', 'x0, [x3, #1008]'),
    0x10e934: ('bl', '0x1af540'),
    0x10e944: ('bl', '0x1af540'),
    0x10e948: ('ldp', 'x0, x1, [x19, #144]'),
    0x10e95c: ('strb', 'w0, [x1, #16]'),
    0x10e960: ('strb', 'w3, [x1, #27]'),
    0x10e964: ('strb', 'w3, [x1, #25]'),
    0x10e96c: ('strb', 'wzr, [x1, #26]'),
    0x10e974: ('strb', 'w3, [x1, #18]'),
    0x10e978: ('strb', 'w0, [x1, #19]'),
    0x10e988: ('strb', 'w5, [x1, #17]'),
    0x10e990: ('str', 'w4, [x2, #112]'),
    0x10e998: ('str', 'wzr, [x2, #116]'),
    0x10e99c: ('str', 'w1, [x2, #80]'),
    0x10e9a0: ('str', 'wzr, [x2, #84]'),
    0x10ea24: ('ldr', 'x24, [x25]'),
    0x10eb88: ('str', 'wzr, [x0, #1808]'),
    0x10ebb8: ('add', 'x20, x20, #0x8d8'),
    0x10ebc4: ('str', 'w0, [x1]'),
    0x10ec28: ('str', 'w3, [x23, #1792]'),
    0x10ec98: ('stp', 'x29, x30, [sp, #-32]!'),
    0x10ec9c: ('adrp', 'x1, 0x8a7000'),
    0x10eca0: ('mov', 'x0, #0x1ff0'),
    0x10eca4: ('mov', 'x29, sp'),
    0x10eca8: ('str', 'x19, [sp, #16]'),
    0x10ecac: ('str', 'wzr, [x1, #1808]'),
    0x10ecb0: ('bl', '0x18fd50'),
    0x10ecb4: ('adrp', 'x1, 0x8a7000'),
    0x10ecb8: ('str', 'x0, [x1, #1816]'),
    0x10ecbc: ('cbz', 'x0, 0x10ed6c'),
    0x10ecc0: ('mov', 'x2, #0x1ff0'),
    0x10ecc4: ('mov', 'w1, #0x0'),
    0x10ecc8: ('mov', 'x19, x0'),
    0x10eccc: ('bl', '0x1af540'),
    0x10ecd0: ('mov', 'x0, #0x20'),
    0x10ecd4: ('bl', '0x18fd50'),
    0x10ecd8: ('str', 'x0, [x19, #8112]'),
    0x10ecdc: ('cbz', 'x0, 0x10ed6c'),
    0x10ece0: ('mov', 'x1, #0x2000'),
    0x10ece4: ('mov', 'x0, #0x1000'),
    0x10ece8: ('bl', '0x18fd90'),
    0x10ecec: ('str', 'x0, [x19, #144]'),
    0x10ecf0: ('cbz', 'x0, 0x10ed88'),
    0x10ecf4: ('and', 'x0, x0, #0xfff'),
    0x10ecf8: ('cbnz', 'x0, 0x10eda0'),
    0x10ecfc: ('mov', 'x1, #0x40'),
    0x10ed00: ('mov', 'x0, #0x1000'),
    0x10ed04: ('bl', '0x18fd90'),
    0x10ed08: ('str', 'x0, [x19, #152]'),
    0x10ed0c: ('cbz', 'x0, 0x10edb8'),
    0x10ed10: ('and', 'x0, x0, #0xfff'),
    0x10ed14: ('cbnz', 'x0, 0x10edd0'),
    0x10ed18: ('mov', 'x1, #0xa0'),
    0x10ed1c: ('mov', 'x0, #0x1000'),
    0x10ed20: ('bl', '0x18fd90'),
    0x10ed24: ('str', 'x0, [x19, #160]'),
    0x10ed28: ('cbz', 'x0, 0x10ed6c'),
    0x10ed2c: ('and', 'x0, x0, #0xfff'),
    0x10ed30: ('cbnz', 'x0, 0x10ed6c'),
    0x10ed34: ('mov', 'x0, #0xc00'),
    0x10ed38: ('bl', '0x18fd50'),
    0x10ed3c: ('adrp', 'x1, 0x8a7000'),
    0x10ed40: ('str', 'x0, [x1, #1800]'),
    0x10ed44: ('cbz', 'x0, 0x10ed58'),
    0x10ed48: ('mov', 'w0, #0x0'),
    0x10ed4c: ('ldr', 'x19, [sp, #16]'),
    0x10ed50: ('ldp', 'x29, x30, [sp], #32'),
    0x10ed54: ('ret', ''),
    0x10ed7c: ('mov', 'w0, #0xffffffff'),
    0x10ed84: ('ret', ''),
    0x18fd64: ('mov', 'w1, #0x0'),
    0x18fd68: ('b', '0x20c098'),
    0x18fd7c: ('bl', '0x18fbf0'),
    0x18fd88: ('mov', 'w1, #0x0'),
    0x18fd8c: ('b', '0x20c098'),
    0x18fda4: ('mov', 'x19, x1'),
    0x18fdb4: ('mov', 'w1, w0'),
    0x18fdb8: ('mov', 'x0, x19'),
    0x18fdc4: ('b', '0x20c098'),
    0x18fdcc: ('bl', '0x18fbf0'),
    0x18fdd4: ('mov', 'w1, w0'),
    0x18fdd8: ('mov', 'x0, x19'),
    0x18fde4: ('b', '0x20c098'),
}
STRINGS = {
    0x2275e8: b'UFS: %s: cmd_desc_addr memory alloc error!!!\n',
    0x227618: b'UFS: %s: allocated cmd_desc_addr memory align error!!!\n',
    0x227650: b'UFS: %s: utrd_addr memory alloc error!!!\n',
    0x227680: b'UFS: %s: allocated utrd_addr memory align error!!!\n',
    0x2276b8: b'UFS: %s: ufs_dev memory allocation failed\n',
    0x2276e8: b'##### LK memory allocation fails !!! #####\n',
    0x226dc8: b'UFS Invalid host structure: %d\n',
}


def store_unsigned_w(word):
    if (type(word) is not int or not 0 <= word <= 0xffffffff
            or word & 0xffc00000 != 0xb9000000):
        raise ValueError('expected STR W unsigned immediate')
    return word & 31, (word >> 5) & 31, ((word >> 10) & 0xfff)*4


def u64_table(data, offset, count):
    if (type(offset) is not int or type(count) is not int or offset < 0 or offset % 8
            or not 1 <= count <= 64 or offset > len(data) or count*8 > len(data)-offset):
        raise ValueError('invalid u64 table bounds')
    return list(struct.unpack_from('<'+'Q'*count, data, offset))


def host_binding(words):
    pub_reg, pub_page = adrp(words[0x10ecb4], 0x10ecb4)
    source, pub_base, pub_offset = store_unsigned_x(words[0x10ecb8])
    use_reg, use_page = adrp(words[0x10e834], 0x10e834)
    destination, use_base, use_offset = load_x(words[0x10e844])
    table_reg, table = page_plus_add(words, 0x10e770, 0x10e778)
    if ((pub_reg, source, pub_base, use_reg, destination, use_base, table_reg)
            != (1, 0, 1, 21, 19, 21, 20)
            or pub_page+pub_offset != use_page+use_offset or table != pub_page+pub_offset):
        raise ValueError('host publication/consumer binding differs')
    index_addresses = []
    for page_pc, store_pc, expected_base in ((0x10ec9c,0x10ecac,1),(0x10eb7c,0x10eb88,0)):
        register, page = adrp(words[page_pc],page_pc)
        source, base, offset = store_unsigned_w(words[store_pc])
        if (register,source,base) != (expected_base,31,expected_base):
            raise ValueError('host index reset binding differs')
        index_addresses.append(page+offset)
    reg, page = adrp(words[0x10e768],0x10e768)
    dest, base, offset = load_unsigned_w(words[0x10e780])
    if (reg,dest,base)!=(21,1,21) or set(index_addresses+[page+offset]) != {table-8}:
        raise ValueError('host index consumer binding differs')
    return dict(host_table_relative_address=hex(table), initialized_slot=0,
        host_index_relative_address=hex(table-8), selected_reset_value=0,
        allocator_publication_precedes_null_check=True, active_host_established=False)


def allocation_fields(words):
    rows = []
    for name, size_pc, align_pc, call_pc, store_pc, expected_slot in (
            ('metadata',0x10ecd0,None,0x10ecd4,0x10ecd8,8112),
            ('command',0x10ece0,0x10ece4,0x10ece8,0x10ecec,144),
            ('transfer',0x10ecfc,0x10ed00,0x10ed04,0x10ed08,152),
            ('task',0x10ed18,0x10ed1c,0x10ed20,0x10ed24,160)):
        register,width,size=wide_constant([words[size_pc]])
        if (register,width) != (1 if align_pc else 0,64):
            raise ValueError('allocation size argument binding differs')
        source,base,slot=store_unsigned_x(words[store_pc])
        expected_allocator=0x18fd90 if align_pc else 0x18fd50
        if ((source,base,slot)!=(0,19,expected_slot)
                or flow(words[call_pc],call_pc)!=('bl',expected_allocator)):
            raise ValueError('allocation result/call binding differs')
        alignment=None
        if align_pc:
            reg,width,alignment=wide_constant([words[align_pc]])
            if (reg,width)!=(0,64):
                raise ValueError('allocation alignment argument binding differs')
        rows.append(dict(name=name,bytes=size,alignment_argument=alignment,
            host_pointer_offset=slot,allocator=hex(expected_allocator)))
    return rows


def config_bindings(words):
    reg,primary=page_plus_add(words,0x10e870,0x10e874)
    alt_reg,alternate=page_plus_add(words,0x10ebb4,0x10ebb8)
    if (reg,alt_reg)!=(20,20):
        raise ValueError('config table register differs')
    rows=[]
    for load_pc,store_pc,source_offset,dest_offset in (
            (0x10e878,0x10e880,0,24),(0x10e884,0x10e888,8,32),
            (0x10e88c,0x10e890,16,40),(0x10e894,0x10e898,24,48),
            (0x10e89c,0x10e8a0,32,64)):
        if (load_x(words[load_pc])!=(0,20,source_offset)
                or store_unsigned_x(words[store_pc])!=(0,19,dest_offset)):
            raise ValueError('config field copy binding differs')
        rows.append(dict(table_offset=source_offset,host_offset=dest_offset))
    return primary,alternate,rows


def address_projection(pointer):
    """Synthetic address bits programmed by the selected low32/zero-high stores."""
    if type(pointer) is not int or not 0 <= pointer <= 0xffffffffffffffff:
        raise ValueError('u64 pointer bits required')
    return dict(input_pointer=hex(pointer),programmed_low32=hex(pointer & 0xffffffff),
        programmed_high32=0,pointer_bits_preserved=pointer <= 0xffffffff,
        dma_mapping_or_extent_established=False)


def inspect(path):
    data=read_exact(path,*IMAGES['sboot'])
    root=Path(__file__).resolve().parent.parent
    command=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
             str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for low,high in BLOCKS.values():
        parsed=parse_lines(subprocess.check_output(command+['-D','-z','-b','binary','-m','aarch64',
            f'--start-address={low}',f'--stop-address={high}',str(Path(path).resolve())],text=True))
        if lines.keys() & parsed.keys():
            raise ValueError('duplicate GNU PC across blocks')
        lines.update(parsed)
    branches=verify_disassembly(data,lines,BLOCKS,SELECTED)
    words={pc:row[0] for pc,row in lines.items()}
    bindings=host_binding(words);allocations=allocation_fields(words)
    primary,alternate,copies=config_bindings(words)
    for pc,expected in ((0x10e990,(4,2,112)),(0x10e998,(31,2,116)),
                         (0x10e99c,(1,2,80)),(0x10e9a0,(31,2,84))):
        if store_unsigned_w(words[pc])!=expected:
            raise ValueError('DMA base register store binding differs')
    for offset,value in STRINGS.items():
        if data[offset:offset+len(value)+1]!=value+b'\0':
            raise ValueError(f'literal differs at {offset:#x}')
    packed=b''.join(struct.pack('<II',pc,row[0]) for pc,row in sorted(lines.items()))
    return dict(mode='static_lk_ufs_host_allocation_and_address_programming',
        sboot_sha256=IMAGES['sboot'][1],firmware_executed=False,hardware_observed=False,
        dma_coherence_established=False,counter_persistence_established=False,
        gnu_words=len(lines),gnu_relative_targets=len(branches),selected_operand_checks=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        blocks={name:dict(start=hex(low),end_exclusive=hex(high)) for name,(low,high) in BLOCKS.items()},
        selected_instructions={hex(pc):dict(word=f'{lines[pc][0]:08x}',op=op,args=args)
                               for pc,(op,args) in sorted(SELECTED.items())},
        branches=branches,bindings=bindings,host_allocation_bytes=8176,allocations=allocations,
        config_tables=[dict(file_offset=hex(offset),qwords=[hex(v) for v in u64_table(data,offset,8)])
                       for offset in (primary,alternate)],config_field_copies=copies,
        synthetic_address_projections=[address_projection(p) for p in (0x1000,0xfffff000,0x100001000)],
        strings={hex(pc):value.decode('ascii') for pc,value in STRINGS.items()},
        local_graphs={name:summarize_local(data,low,low,high) for name,(low,high) in BLOCKS.items()},
        interpretation=dict(
            host='allocator publishes host pointer to relative8a7718 before null check; init reads slot0 and selected exits reset relative8a7710 to0',
            partial_failure='allocator local error return-1 does not explicitly undo earlier publications or free the selected buffers',
            alignment='command/transfer/task pointers are requested with alignment4096 and checked for low12 zero; no DMA mapping or ownership proof',
            wrappers='malloc wrapper supplies alignment0; aligned wrapper passes size inX0 and low32 alignment inW1 to0x20c098, with optional opaque18fbf0 first',
            configuration='default303198 or alternate3038d8 chosen through repeated opaque147ea8 queries; first five pointer values copied to host24/32/40/48/64',
            bases='both tables encode HCI13100000 and vendor13101100, with other MMIO context values; no live power/clock/mapping measurement',
            address_programming='transfer/task bases use pointer low32 and explicit high32 zero; command address low32 copied into transfer descriptor with zeroed high dword',
            separate_scratch='init allocates8192 into relative8a73f0 in addition to the descriptor buffers; this local allocation result is not checked before publication',
            coherence='static alignment, DSB and nominal addresses do not establish CPU/DMA address identity, cache attributes or coherent device writes'),
        limits=[
            'selected local initialization only; not a census of all runtime writes, aliases or host users',
            'allocator internals20c098, deferred work18fbf0, board queries and hardware helpers remain opaque',
            'addresses above4GiB illustrate truncation only; no actual allocated address or extent was acquired',
            'Linux DMA API and Exynos quirks are reference context, not proof of the LK active configuration',
            'no firmware, MMIO, storage request or phone action was executed; capture and persistence remain unproved'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot',type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as error:
        parser.exit(2,f'inspect_lk_ufs_host: {error}\n')


if __name__=='__main__':
    main()
