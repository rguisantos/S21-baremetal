#!/usr/bin/env python3
"""Bind HZC2 AVB metadata reads and the selected boot fallback, statically."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from capture_a0_formats import require
from capture_a0_inputs import read_checked, sealed_input
from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES
from inspect_lk_avb_trust import address_pair, load_x, pair_store_x
from inspect_lk_embedded_key import adrp
from inspect_lk_final_edges import flow
from inspect_lk_precopy_measurement import verify_disassembly

ROOT = Path(__file__).resolve().parents[1]
BLOCKS = {
    'caller_suffix': (0xfbc58, 0xfbc6c),
    'wrapper_entry': (0x17f5d0, 0x17f6b4),
    'slot_entry_and_root': (0x1244b0, 0x124754),
    'metadata_load': (0x122498, 0x12289c),
    'fallback_gate': (0x122b08, 0x122b80),
    'fallback_boot': (0x123030, 0x1230bc),
    'ops_installer': (0x180de8, 0x180e6c),
    'read_callback': (0x180448, 0x180720),
    'partition_size': (0x17fcb8, 0x17fd28),
    'uppercase_name': (0x125a68, 0x125a98),
    'partition_lookup': (0x14a1b0, 0x14a248),
    'name_and_suffix': (0x1253e0, 0x1254a4),
    'prefix_compare': (0x1b26b0, 0x1b2714),
    'name_compare': (0x1b2538, 0x1b2570),
    'name_copy': (0x1b2570, 0x1b2588),
    'prefix_thunk': (0x124f58, 0x124f5c),
    'length_thunk': (0x124f60, 0x124f64),
    'block_read_dispatch': (0x11b258, 0x11b2cc),
}
SELECTED = {
    0xfbc68: ('bl', '0x17f5d0'),
    0x17f608: ('mov', 'x19, x0'),
    0x17f678: ('bl', '0x180de8'),
    0x17f680: ('bl', '0x180e70'),
    0x17f698: ('ldrb', 'w3, [x29, #143]'),
    0x17f6a4: ('mov', 'x2, x19'),
    0x17f6ac: ('mov', 'w4, #0x0'),
    0x17f6b0: ('bl', '0x1244b0'),
    0x124504: ('mov', 'w19, w3'),
    0x124508: ('mov', 'x20, x1'),
    0x12453c: ('and', 'w0, w19, #0x4'),
    0x124544: ('tbz', 'w19, #2, 0x124650'),
    0x124594: ('and', 'w0, w19, #0x4'),
    0x124598: ('cbz', 'w0, 0x1246f8'),
    0x124700: ('mov', 'x0, x28'),
    0x12471c: ('mov', 'x7, x28'),
    0x124728: ('mov', 'w6, #0x0'),
    0x12473c: ('bl', '0x122498'),
    0x1224f8: ('cbnz', 'w6, 0x122b08'),
    0x1224fc: ('eor', 'x0, x23, #0x4'),
    0x122500: ('ubfx', 'x27, x0, #2, #1'),
    0x122524: ('bl', '0x124f58'),
    0x122528: ('mov', 'w26, w0'),
    0x1225e0: ('bl', '0x1253e0'),
    0x1225ec: ('cbz', 'w26, 0x122748'),
    0x122600: ('mov', 'x3, #0x40'),
    0x122604: ('mov', 'x2, #0xffffffffffffffc0'),
    0x122628: ('b.ne', '0x12423c'),
    0x122634: ('bl', '0x121588'),
    0x12263c: ('cbz', 'w0, 0x122c48'),
    0x12264c: ('cmp', 'x28, #0x10, lsl #12'),
    0x122650: ('b.hi', '0x122f84'),
    0x122748: ('mov', 'x0, #0x10000'),
    0x12275c: ('mov', 'x28, #0x10000'),
    0x1227b0: ('mov', 'x2, #0x0'),
    0x1227c0: ('mov', 'x3, x28'),
    0x1227d0: ('cmp', 'w0, #0x1'),
    0x1227d4: ('b.eq', '0x122ce8'),
    0x1227d8: ('cbnz', 'w0, 0x122b10'),
    0x1227f4: ('bl', '0x1262b0'),
    0x122b08: ('mov', 'w27, #0x0'),
    0x122b10: ('cmp', 'w0, #0x3'),
    0x122b14: ('cset', 'w0, eq'),
    0x122b18: ('cmp', 'w26, wzr'),
    0x122b1c: ('and', 'w0, w27, w0'),
    0x122b20: ('cset', 'w1, ne'),
    0x122b24: ('cmp', 'w1, w0'),
    0x122b30: ('b.cc', '0x123030'),
    0x122b38: ('mov', 'w20, #0x2'),
    0x123078: ('mov', 'x7, x19'),
    0x123084: ('mov', 'w6, #0x0'),
    0x1230b0: ('bl', '0x122498'),
    0x180e10: ('stp', 'x3, x2, [x1, #24]'),
    0x180e60: ('str', 'x4, [x1, #88]'),
    0x18047c: ('tbnz', 'x2, #63, 0x1806b0'),
    0x180488: ('bl', '0x1b2570'),
    0x180490: ('bl', '0x125a68'),
    0x180498: ('bl', '0x14a1b0'),
    0x1804a0: ('mov', 'w0, #0x3'),
    0x1804a4: ('cbz', 'x19, 0x1805f4'),
    0x1804bc: ('and', 'x24, x21, #0x1ff'),
    0x1804cc: ('lsr', 'x21, x21, #9'),
    0x1804f8: ('add', 'w26, w2, w21'),
    0x180514: ('bl', '0x11b258'),
    0x180518: ('add', 'x0, x26, #0x1'),
    0x180578: ('bl', '0x11b258'),
    0x18057c: ('mov', 'x0, x22'),
    0x1805d8: ('bl', '0x11b258'),
    0x1805dc: ('b', '0x18057c'),
    0x180670: ('bl', '0x11b258'),
    0x180674: ('ldr', 'x0, [x29, #96]'),
    0x18068c: ('str', 'x25, [x28]'),
    0x1806a4: ('mov', 'w0, #0x0'),
    0x1806b4: ('bl', '0x17fcb8'),
    0x1806bc: ('cbnz', 'w0, 0x1805e0'),
    0x1806c4: ('add', 'x21, x21, x0'),
    0x1806f0: ('bl', '0x11b258'),
    0x1806f4: ('b', '0x180518'),
    0x180708: ('bl', '0x11b258'),
    0x18070c: ('b', '0x180674'),
    0x180710: ('mov', 'w0, #0x1'),
    0x17fd04: ('lsl', 'x1, x1, #9'),
    0x17fd08: ('str', 'x1, [x19]'),
    0x17fd1c: ('mov', 'w0, #0x3'),
    0x125a74: ('sub', 'w1, w0, #0x61'),
    0x125a78: ('sub', 'w0, w0, #0x20'),
    0x125a80: ('cmp', 'w1, #0x19'),
    0x125a88: ('strb', 'w0, [x2]'),
    0x14a1cc: ('ldr', 'w22, [x20, #4]'),
    0x14a1d8: ('add', 'x20, x20, #0x40'),
    0x14a1fc: ('add', 'x20, x20, #0x84'),
    0x14a200: ('bl', '0x1b2538'),
    0x14a21c: ('add', 'x0, x0, #0x1c'),
    0x14a230: ('mov', 'x0, #0x0'),
    0x12546c: ('bl', '0x124f40'),
    0x12547c: ('bl', '0x124f40'),
    0x125484: ('strb', 'wzr, [x25, x0]'),
    0x1b2574: ('ldrb', 'w3, [x1, x2]'),
    0x1b2578: ('strb', 'w3, [x0, x2]'),
    0x1b2580: ('cbnz', 'w3, 0x1b2574'),
    0x11b280: ('ldr', 'x4, [x0, #168]'),
    0x11b29c: ('br', 'x4'),
}
STRINGS = {0x22d7e0:b'vbmeta',0x2169f0:b'boot',0x28ef80:b'',
    0x232838:b'BOOTLOADER',0x23d8a0:b'VBMETA_SAMSUNG',0x23d8b0:b'VBMETA_SYSTEM',
    0x22da70:b": No such partition. Trying 'boot' instead.\n",
    0x22da00:b"Loading vbmeta struct in footer from partition '",
    0x22da40:b"Loading vbmeta struct from partition '",
    0x2581a0:b'There is no partition [%s]\n'}


def store_x(word):
    require(word & 0xffc00000 == 0xf9000000, 'expected STR X unsigned-immediate')
    return word & 31, (word >> 5) & 31, ((word >> 10) & 0xfff)*8


def address_to(words,page_pc,add_pc,source,destination):
    reg,page=adrp(words[page_pc],page_pc);word=words[add_pc]
    require(reg==source and word & 0xff800000==0x91000000
        and word & 31==destination and (word>>5) & 31==source,'ADRP/ADD destination binding')
    return page+(((word>>10) & 0xfff) << (12 if word & (1<<22) else 0))


def resolve_bindings(words):
    table = address_pair(words,0x180de8,0x180df0,1)
    read = address_pair(words,0x180dec,0x180dfc,3)
    size = address_pair(words,0x180e28,0x180e48,4)
    a, b, base, slot = pair_store_x(words[0x180e10])
    require((a,b,base,slot)==(3,2,1,24) and read==BLOCKS['read_callback'][0], 'read callback store binding')
    for load, call in ((0x1225f4,0x122610),(0x1227b4,0x1227cc)):
        rd, rn, offset = load_x(words[load])
        require((rd,rn,offset)==(6,25,slot) and flow(words[call],call)==('blr',rd),
            'read callback consumer binding')
    require(store_x(words[0x180e60])==(4,1,88) and size==BLOCKS['partition_size'][0]
        and flow(words[0x1806b4],0x1806b4)==('bl',size), 'partition size binding')
    suffix = address_pair(words,0xfbc58,0xfbc64,0)
    initial_name = address_to(words,0x1246f8,0x1246fc,7,28)
    fallback_name = address_pair(words,0x123034,0x123060,19)
    require(initial_name==0x22d7e0 and fallback_name==0x2169f0, 'root/fallback name binding')
    return dict(ops_relative_address=hex(table),read_slot=slot,read_target=hex(read),
        size_slot=88,size_target=hex(size),selected_caller_suffix_offset=hex(suffix),
        initial_root_name_offset=hex(initial_name),fallback_name_offset=hex(fallback_name),
        runtime_binding_and_preservation_established=False)


def fallback_model(status,prefix_result,flags,chain_location=0):
    """Manual local predicate model only; not an execution or boot decision."""
    require(all(type(x) is int for x in (status,prefix_result,flags,chain_location))
        and 0 <= status < 2**32 and -2**31 <= prefix_result < 2**32
        and 0 <= flags < 2**32 and 0 <= chain_location < 2**32, 'invalid predicate model input')
    w27 = 0 if chain_location else (((flags ^ 4) >> 2) & 1)
    w0 = w27 & int(status == 3); w1 = int((prefix_result & 0xffffffff) != 0)
    return w1 < w0


def ascii_upper(data):
    """Model non-NUL bytes; the analyzer's bound is not a firmware bound."""
    require(type(data) is bytes and len(data)<=128 and b'\0' not in data, 'invalid name model input')
    return bytes(x-32 if 97<=x<=122 else x for x in data)


def disassemble(data,blocks):
    require(type(data) is bytes and blocks and all(type(lo) is int and type(hi) is int
        and lo%4==hi%4==0 and 0<=lo<hi<=len(data) for lo,hi in blocks.values()), 'GNU block bound')
    command=['bash',str(ROOT/'scripts/cross-run.sh'),str(ROOT/'tools/root'),
        str(ROOT/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={};pin=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    with sealed_input(data,pin) as(fd,path):
        for lo,hi in blocks.values():
            raw=subprocess.check_output(command+['-D','-z','-b','binary','-m','aarch64',
                f'--start-address={lo}',f'--stop-address={hi}',path],pass_fds=(fd,),text=True,timeout=30)
            parsed=parse_lines(raw)
            require(not lines.keys() & parsed.keys(), 'duplicate GNU PC')
            lines.update(parsed)
    return lines


def inspect(path):
    size,sha=IMAGES['sboot'];data=read_checked(path,dict(bytes=size,sha256=sha))
    lines=disassemble(data,BLOCKS)
    branches=verify_disassembly(data,lines,BLOCKS,SELECTED)
    words={pc:r[0] for pc,r in lines.items()};binding=resolve_bindings(words)
    for pc,value in STRINGS.items():
        require(data[pc:pc+len(value)+1]==value+b'\0',f'literal differs at {pc:#x}')
    require(binding['selected_caller_suffix_offset']=='0x28ef80','caller suffix binding differs')
    packed=b''.join(struct.pack('<II',pc,r[0]) for pc,r in sorted(lines.items()))
    return dict(mode='static_hzc2_vbmeta_read_and_fallback',sboot_bytes=size,sboot_sha256=sha,
        firmware_executed=False,hardware_observed=False,installed_parent_identity_established=False,
        device_key_trust_established=False,image_acceptance_established=False,a0_complete=False,a1_started=False,
        binding=binding,gnu_words=len(lines),gnu_relative_targets=len(branches),selected_operand_checks=len(SELECTED),
        same_verified_firmware_buffer_parsed_and_disassembled=True,gnu_input_sealed=True,
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        blocks={k:[hex(lo),hex(hi)] for k,(lo,hi) in BLOCKS.items()},
        instructions={hex(pc):dict(word=f'{raw:08x}',op=op,args=args) for pc,(raw,op,args) in sorted(lines.items())},
        branches=branches,strings={hex(pc):value.decode('ascii') for pc,value in STRINGS.items()},
        interpretation=dict(initial_request='vbmeta + suffix; selected caller points to an empty file-backed suffix',
            read_lookup='copy name, uppercase ASCII a..z, query 0x14a1b0 live table',
            table='LK-relative 0xcd36b8: u32 count at +4; names at +0x40+i*0x84; returned record at +0x1c+i*0x84',
            initial_metadata_read='offset 0, requested 65536 bytes for vbmeta prefix',
            non_vbmeta_read='footer: offset -64 length 64; decoded metadata offset/length then read, capped at 65536',
            negative_offset='partition_size + signed_offset; size is LE32(record+24)<<9',
            sector_address='LE32(record+20) + (byte_offset>>9) with W32 addition; not observed geometry',
            read_backends='0x11b258 with 512-byte requests; BOOTLOADER uses selector 1, others LE32(record+28)',
            backend_return='selected read calls do not test returned W0 before copies/output; no read-success proof',
            success_path='out_num_read=requested_length; W0=0, conditional on opaque callees returning normally',
            no_partition='lookup null returns callback W0=3; allocation null returns W0=1',
            fallback='only initial read status 3, vbmeta prefix equal, flags bit2 clear, zero chain location; recurse on boot',
            fallback_is_not_unsigned_boot_acceptance=True,
            samsung_system_strings='exist in file, but no alternate-name selection in the selected read/size callback bodies',
            trust='separate callback 0x180d50 requests key using label vbmeta; installed root/trusted key not measured'),
        limits=['selected static path, not a census of every indirect entry or mode',
            'PIT/runtime table, backend dispatch target and installed partition bytes remain unobserved',
            'presence of the BL candidate and matching stock digests does not identify installed data',
            'no SMC, firmware instruction, flash, OEM decision or device collection performed'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot',type=Path)
    parser.add_argument('--output',type=Path);a=parser.parse_args()
    try:
        report=inspect(a.sboot);out=json.dumps(report,indent=2)+'\n'
        if a.output:
            with a.output.open('x') as f:f.write(out)
        else:print(out,end='')
    except (ValueError,OSError,subprocess.SubprocessError) as exc:parser.exit(2,str(exc)+'\n')


if __name__=='__main__':main()
