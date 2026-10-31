#!/usr/bin/env python3
"""Inspect and model the pinned LK pool's selected EL1/4K table construction."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_avb_boot import wide_constant
from inspect_lk_build_id import page_plus_add
from inspect_lk_payload_return import DELTA, summarize_local
from inspect_lk_precopy_measurement import verify_disassembly

FLAGS = 0x20000000000745
MAIR = 0xff44
TABLE_LOW, TABLE_HIGH = 0x322000, 0x363000
MASK = 0xffffff000
LAB_DELTAS = (0x3ff14000, 0x41f14000)
BLOCKS = {
    'startup_fragment': (0xfa990, 0xfa9cc),
    'board_init_fragment': (0xee730, 0xee744),
    'register_writers': (0x189450, 0x189460),
    'control_writer': (0x1894a0, 0x1894a8),
    'table_writers': (0x1894e8, 0x1894f8),
    'upper_table_writer': (0x189500, 0x189508),
    'mair_valid_case': (0x189e10, 0x189e20),
    'mapper': (0x189f68, 0x18a164),
    'install': (0x18a168, 0x18a1f0),
    'build': (0x18a1f0, 0x18a30c),
    'update': (0x18a348, 0x18a390),
    'build_wrapper': (0x18a390, 0x18a3a8),
}
SELECTED = {
    0xfa99c: ('bl', '0xfa7b0'),
    0xfa9a0: ('bl', '0xee660'),
    0xfa9c8: ('bl', '0x18fd30'),
    0xee738: ('bl', '0x18a390'),
    0x189450: ('msr', 'mair_el1, x0'),
    0x1894a0: ('msr', 'tcr_el1, x0'),
    0x1894e8: ('msr', 'ttbr0_el1, x0'),
    0x189500: ('msr', 'ttbr1_el1, x0'),
    0x189e10: ('cmp', 'w0, #0x1'),
    0x189e18: ('mov', 'x0, #0xff44'),
    0x189e1c: ('b', '0x189450'),
    0x189f8c: ('bl', '0x189404'),
    0x189f94: ('bl', '0x189e50'),
    0x189f98: ('lsr', 'x19, x0, #3'),
    0x189f9c: ('mul', 'x19, x19, x0'),
    0x189fa4: ('bl', '0x189e50'),
    0x189fac: ('mov', 'x9, #0x0'),
    0x189fbc: ('udiv', 'x22, x22, x19'),
    0x189fcc: ('mul', 'x10, x22, x19'),
    0x189fdc: ('adrp', 'x9, 0x323000'),
    0x189fe0: ('add', 'x9, x9, #0x0'),
    0x189ff0: ('adrp', 'x3, 0xec000'),
    0x189ff8: ('adrp', 'x23, 0x18ec000'),
    0x18a000: ('and', 'x17, x20, #0xffdfffffffffffff'),
    0x18a004: ('adrp', 'x14, 0x322000'),
    0x18a008: ('adrp', 'x30, 0x363000'),
    0x18a010: ('add', 'x3, x3, #0x0'),
    0x18a01c: ('add', 'x23, x23, #0x0'),
    0x18a024: ('orr', 'x17, x17, #0x80'),
    0x18a028: ('add', 'x14, x14, #0x0'),
    0x18a02c: ('add', 'x30, x30, #0x0'),
    0x18a034: ('orr', 'x22, x20, #0x80'),
    0x18a038: ('adrp', 'x13, 0x353000'),
    0x18a03c: ('cmp', 'x8, x3'),
    0x18a048: ('cmp', 'x8, x23'),
    0x18a060: ('ubfiz', 'w2, w2, #9, #4'),
    0x18a070: ('and', 'x1, x1, #0xffffff000'),
    0x18a074: ('orr', 'x1, x1, #0x3'),
    0x18a078: ('str', 'x1, [x4]'),
    0x18a07c: ('udiv', 'x12, x19, x0'),
    0x18a090: ('cmp', 'x2, x16'),
    0x18a098: ('cmp', 'x18, x2'),
    0x18a09c: ('csel', 'x4, x17, x22, hi'),
    0x18a0a4: ('orr', 'x4, x24, x4'),
    0x18a0b4: ('str', 'x4, [x6, w1, sxtw #3]'),
    0x18a0cc: ('ubfiz', 'w1, w1, #9, #4'),
    0x18a0d0: ('orr', 'x24, x2, #0x3'),
    0x18a0e0: ('cmp', 'x2, x14'),
    0x18a0ec: ('cmp', 'x2, x30'),
    0x18a108: ('str', 'x4, [x6, w1, sxtw #3]'),
    0x18a144: ('orr', 'x1, x20, x10'),
    0x18a14c: ('str', 'x1, [x4]'),
    0x18a17c: ('bl', '0x189e10'),
    0x18a180: ('cmp', 'w19, #0x1'),
    0x18a1b0: ('adrp', 'x19, 0x322000'),
    0x18a1b4: ('add', 'x19, x19, #0x0'),
    0x18a1bc: ('bl', '0x1894e8'),
    0x18a1c4: ('bl', '0x189500'),
    0x18a1cc: ('bl', '0x189500'),
    0x18a1d0: ('mov', 'x0, #0x351c'),
    0x18a1d4: ('movk', 'x0, #0xb51c, lsl #16'),
    0x18a1d8: ('movk', 'x0, #0x11, lsl #32'),
    0x18a1dc: ('bl', '0x1894a0'),
    0x18a204: ('bl', '0x189404'),
    0x18a20c: ('bl', '0x189404'),
    0x18a214: ('bl', '0x189e10'),
    0x18a224: ('adrp', 'x22, 0x322000'),
    0x18a228: ('add', 'x22, x22, #0x0'),
    0x18a238: ('str', 'xzr, [x22, w19, uxtw #3]'),
    0x18a244: ('bl', '0x189e50'),
    0x18a248: ('lsr', 'x0, x0, #3'),
    0x18a258: ('adrp', 'x23, 0x323000'),
    0x18a264: ('add', 'x19, x23, #0x0'),
    0x18a270: ('bl', '0x189e50'),
    0x18a274: ('madd', 'x0, x0, x20, x19'),
    0x18a278: ('orr', 'x0, x0, #0x3'),
    0x18a27c: ('str', 'x0, [x22, x20, lsl #3]'),
    0x18a284: ('cmp', 'x20, #0x30'),
    0x18a28c: ('adrp', 'x19, 0x31f000'),
    0x18a290: ('add', 'x19, x19, #0xd28'),
    0x18a294: ('add', 'x20, x19, #0x1b8'),
    0x18a298: ('ldp', 'x1, x2, [x19, #8]'),
    0x18a29c: ('ldr', 'x3, [x19, #24]'),
    0x18a2a0: ('ldr', 'x0, [x19], #40'),
    0x18a2a4: ('bl', '0x189f68'),
    0x18a2b0: ('bl', '0x11b6f0'),
    0x18a2b8: ('fcmpe', 'd0, d1'),
    0x18a2d8: ('bl', '0x189f68'),
    0x18a2e0: ('bl', '0x18a168'),
    0x18a2f4: ('bl', '0x189cc8'),
    0x18a308: ('b', '0x189c30'),
    0x18a354: ('adrp', 'x19, 0x31f000'),
    0x18a35c: ('add', 'x19, x19, #0xcb0'),
    0x18a364: ('add', 'x20, x19, #0x78'),
    0x18a374: ('bl', '0x189f68'),
    0x18a380: ('dsb', 'sy'),
    0x18a38c: ('b', '0x189d60'),
    0x18a398: ('bl', '0x18990c'),
    0x18a39c: ('bl', '0x18a1f0'),
}


def u64(value):
    if type(value) is not int or not 0 <= value < 1 << 64:
        raise ValueError('u64 integer required')
    return value


def leaf_attributes(word, level, mair=MAIR):
    u64(word);u64(mair)
    if type(level) is not int or level not in (2,3) or word & 3 != (1 if level==2 else 3):
        raise ValueError('expected selected L2 block or L3 page descriptor')
    if level==2 and word & 0x1ff000:
        raise ValueError('misaligned L2 block output address')
    if word & 0xfff000000000:raise ValueError('output address exceeds selected 36-bit IPS')
    index=(word >> 2) & 7
    attribute=(mair >> (index*8)) & 255
    if attribute not in (0x44,0xff):raise ValueError('MAIR attribute outside selected normal-memory profile')
    return dict(attr_index=index,mair_byte=hex(attribute),
        memory='normal_write_back' if attribute==255 else 'normal_noncacheable',
        shareability=(word >> 8) & 3,access_flag=bool(word & 0x400),
        ap_bits=(word >> 6) & 3,read_only=bool(word & 0x80),
        privileged_execute_never=bool(word & (1 << 53)),user_execute_never=bool(word & (1 << 54)))


def walk_tables(data, table_base, root, va):
    """Read only a supplied image: L1 table, L2 block/table, L3 page. No AT/MMU."""
    for v in (table_base,root,va):u64(v)
    if table_base % 4096 or root % 4096 or max(table_base+len(data),root+4096,va+1) > 1 << 36 or len(data) % 4096:
        raise ValueError('selected 36-bit/4K walk bounds differ')
    def read(address):
        offset=address-table_base
        if offset < 0 or offset % 8 or offset+8 > len(data):raise ValueError('table read outside supplied image')
        return struct.unpack_from('<Q',data,offset)[0]
    first=read(root+((va >> 30) & 511)*8)
    if first & 3 != 3 or first & ~(MASK|3):raise ValueError('unsupported L1 table descriptor')
    second=read((first & MASK)+((va >> 21) & 511)*8)
    if second & 3==1:
        return dict(level=2,physical_address=hex((second & MASK)+(va & 0x1fffff)),
                    descriptor=hex(second),attributes=leaf_attributes(second,2))
    if second & 3!=3 or second & ~(MASK|3):raise ValueError('unsupported L2 table descriptor')
    third=read((second & MASK)+((va >> 12) & 511)*8)
    attributes=leaf_attributes(third,3)
    return dict(level=3,physical_address=hex((third & MASK)+(va & 4095)),descriptor=hex(third),attributes=attributes)


def build_lk_tables(delta):
    """Selected LK record only; other L2/L3 entries are supplied zeros."""
    if type(delta) is not int or delta not in (DELTA,*LAB_DELTAS):
        raise ValueError('unsupported nominal/laboratory placement')
    base=delta+TABLE_LOW
    image=bytearray(TABLE_HIGH-TABLE_LOW)
    def put(address,value):struct.pack_into('<Q',image,address-base,value)
    for i in range(48):put(base+i*8,(delta+0x323000+i*4096)|3)
    for va in range(delta+0xec000,delta+0x18ec000,4096):
        index=(va >> 21) & 15
        l3=delta+0x353000+index*4096
        put(delta+0x323000+(va >> 21)*8,l3|3)
        flags=FLAGS
        if va < delta+0x20d000:
            flags=(flags & ~(1 << 53)) | 0x80
        elif delta+TABLE_LOW <= va < delta+TABLE_HIGH:
            flags |= 0x80
        put(l3+((va >> 12) & 511)*8,va|flags|3)
    return bytes(image)


def register_bindings(words):
    root_reg,root=page_plus_add(words,0x18a1b0,0x18a1b4)
    build_reg,build_root=page_plus_add(words,0x18a224,0x18a228)
    second_reg,second=page_plus_add(words,0x189fdc,0x189fe0)
    third_reg,third=page_plus_add(words,0x18a038,0x18a054)
    start_reg,start=page_plus_add(words,0x189ff0,0x18a010)
    end_reg,end=page_plus_add(words,0x189ff8,0x18a01c)
    reg,width,tcr=wide_constant([words[p] for p in (0x18a1d0,0x18a1d4,0x18a1d8)])
    mreg,mwidth,mair=wide_constant([words[0x189e18]])
    if (root_reg,build_reg,second_reg,third_reg,start_reg,end_reg,reg,width,mreg,mwidth)!=(19,22,9,1,3,23,0,64,0,64) or root!=build_root:
        raise ValueError('MMU root/argument binding differs')
    return dict(root_relative=hex(root),l2_relative=hex(second),l3_relative=hex(third),
        lk_start_relative=hex(start),lk_end_relative=hex(end),mair=hex(mair),tcr=hex(tcr),
        t0sz=tcr & 63,tg0=(tcr >> 14) & 3,ips=(tcr >> 32) & 7,
        active_registers_observed=False)


def records(data, offset, count):
    if type(offset) is not int or type(count) is not int or offset < 0 or offset % 8 or not 1<=count<=16 or offset+40*count>len(data):
        raise ValueError('mapping record bounds differ')
    rows=[]
    for i in range(count):
        va,end,pa,flags,name=struct.unpack_from('<5Q',data,offset+i*40)
        n=name-DELTA
        if not 0<=n<len(data):raise ValueError('mapping name outside file')
        end_name=data.find(b'\0',n,min(n+65,len(data)))
        if end_name<0:raise ValueError('mapping name is not bounded')
        rows.append(dict(file_offset=hex(offset+i*40),va=hex(va),end_argument=hex(end),
                         pa=hex(pa),flags=hex(flags),name=data[n:end_name].decode('ascii')))
    return rows


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    command=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for a,b in BLOCKS.values():
        parsed=parse_lines(subprocess.check_output(command+['-D','-z','-b','binary','-m','aarch64',f'--start-address={a}',f'--stop-address={b}',str(Path(path).resolve())],text=True))
        if lines.keys() & parsed.keys():raise ValueError('duplicate GNU PC')
        lines.update(parsed)
    branches=verify_disassembly(data,lines,BLOCKS,SELECTED)
    bindings=register_bindings({p:row[0] for p,row in lines.items()})
    mappings=records(data,0x31fd28,11);updates=records(data,0x31fcb0,3)
    lk=mappings[4]
    if (lk['va'],lk['end_argument'],lk['pa'],lk['flags'],lk['name'])!=('0xe8000000','0xe9800000','0xe8000000',hex(FLAGS),'LK'):
        raise ValueError('selected LK mapping record differs')
    image=build_lk_tables(DELTA);base=DELTA+TABLE_LOW
    samples={k:walk_tables(image,base,base,a) for k,a in (
        ('text_start',DELTA+0xec000),('table_root',base),('pool_first',0xe8c1d000),('pool_last_byte',0xe97fffff))}
    for a in range(0xe8c1d000,0xe9800000,4096):
        row=walk_tables(image,base,base,a)
        if row['physical_address']!=hex(a) or row['attributes']!=samples['pool_first']['attributes']:
            raise ValueError('modeled pool translation/attributes differ')
    packed=b''.join(struct.pack('<II',p,row[0]) for p,row in sorted(lines.items()))
    return dict(mode='static_lk_pool_mmu_construction',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,dma_coherence_established=False,
        gnu_words=len(lines),gnu_relative_targets=len(branches),selected_operand_checks=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        blocks={k:dict(start=hex(a),end_exclusive=hex(b)) for k,(a,b) in BLOCKS.items()},
        selected_instructions={hex(p):dict(word=f'{lines[p][0]:08x}',op=op,args=args) for p,(op,args) in sorted(SELECTED.items())},
        branches=branches,register_bindings=bindings,mapping_records=mappings,update_records=updates,
        selected_model=dict(table_image_sha256=hashlib.sha256(image).hexdigest(),
            pool_pages_verified=3043,samples=samples,other_l2_l3_entries_supplied_zero=True),
        local_graphs={k:summarize_local(data,a,a,b) for k,(a,b) in BLOCKS.items()},
        interpretation=dict(
            construction='selected EL1/4K construction maps every pool page to the same CPU stage1 output address, AttrIndx1 -> MAIRff, inner-shareable, AP01, AF1, PXN1',
            setup='ee738 ->18a390 ->18a1f0 builds mappings;18a168 requests MAIRff44, TTBR0/1 root322000 and TCR11b51c351c; later calls set M/C/I under normal returns',
            granule='mapper uses the supplied/inherited TCR TG0 via189e50 before the installer writes its new TCR; the selected 4K result is conditional on that input',
            ordering='selected fa9a0 board initialization precedes heap initialization fa9c8; physical execution/preservation not observed',
            updates='three selected later update records target high RAM, not the nominal LK pool; no census of all runtime edits',
            dma='CPU stage1 identity and cacheable attributes do not prove SMMU/bus translation, IOCC, buffer ownership or fresh device writes'),
        limits=['Software model of selected EL1/4K builder; not a recovered page-table image or hardware AT result.',
                'Other table entries are supplied zero; the model covers only the selected LK record.',
                'Mair/TCR/TTBR values are requested writes, not acquired live system registers.',
                'No proof of later preservation, cache geometry, DMA identity/coherence, loading or physical capture.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'inspect_lk_pool_mmu: {exc}\n')
