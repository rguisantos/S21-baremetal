#!/usr/bin/env python3
"""Inspect selected HZC2 Samsung signature, rollback and custom-policy paths."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_avb_boot import wide_constant
from inspect_lk_avb_trust import pair_store_x
from inspect_lk_build_id import page_plus_add
from inspect_lk_final_edges import flow
from inspect_lk_payload_return import DELTA, summarize_local
from inspect_lk_precopy_measurement import verify_disassembly


BLOCKS = {
    'signature_selector': (0x1526f8, 0x152818),
    'binary_name_check': (0x152428, 0x1525f4),
    'binary_name_exemptions': (0x1523d0, 0x152428),
    'signature_request_caller': (0x1525f8, 0x1526f8),
    'monitor_request': (0x17dbc0, 0x17dc48),
    'rollback_check': (0x150aa8, 0x150c30),
    'rollback_index': (0x1506f0, 0x1507fc),
    'rollback_counter_getter': (0x1509b0, 0x150aa4),
    'custom_policy': (0x1516b8, 0x1519bc),
    'custom_state_getter': (0x1558a8, 0x155904),
    'custom_policy_tail': (0x150330, 0x1503b4),
    'smc_instruction_wrapper': (0xf6088, 0xf6090),
    'exact_name_compare': (0x1b2538, 0x1b2570),
    'context_pointer_getter': (0x14f500, 0x14f50c),
}
SELECTED = {
    0x15271c: ('mov', 'x2, #0xd0'),
    0x152730: ('bl', '0x1af3c0'),
    0x15273c: ('b.eq', '0x1527f8'),
    0x15274c: ('bl', '0x1b2538'),
    0x152754: ('sxtw', 'x19, w22'),
    0x15275c: ('sub', 'x1, x19, #0x310'),
    0x152764: ('bl', '0x152428'),
    0x15276c: ('cmp', 'w22, #0x200'),
    0x152770: ('b.le', '0x1527d0'),
    0x152774: ('sub', 'x2, x19, #0x210'),
    0x15278c: ('bl', '0x1525f8'),
    0x152804: ('mov', 'w0, #0x0'),
    0x152810: ('mov', 'w0, #0xffffffff'),
    0x152448: ('tbz', 'w0, #17, 0x15245c'),
    0x152450: ('bl', '0x1523d0'),
    0x152474: ('bl', '0x150480'),
    0x152488: ('add', 'x21, x21, #0x9c'),
    0x15248c: ('add', 'x22, x0, #0x44'),
    0x1524a4: ('bl', '0x1b26b0'),
    0x15263c: ('bl', '0x12dbc8'),
    0x15264c: ('b.hi', '0x1526a0'),
    0x152650: ('sxtw', 'x1, w19'),
    0x152660: ('cmp', 'x2, x0'),
    0x152664: ('b.hi', '0x1526a8'),
    0x152668: ('mov', 'w3, #0xe'),
    0x152674: ('bl', '0x17dbc0'),
    0x152678: ('cmn', 'w0, #0x1'),
    0x152680: ('b.eq', '0x1526c8'),
    0x152684: ('mov', 'w0, #0x0'),
    0x1526b8: ('mov', 'w3, #0x10'),
    0x1526d4: ('mov', 'w0, #0x0'),
    0x1526f0: ('mov', 'w0, #0xffffffff'),
    0x17dbe0: ('and', 'x19, x19, #0xffffffffffffff80'),
    0x17dbf8: ('str', 'x2, [x19, #56]'),
    0x17dbfc: ('stp', 'x21, x22, [x19, #40]'),
    0x17dc10: ('add', 'x1, x20, #0x210'),
    0x17dc20: ('mov', 'w1, w23'),
    0x17dc24: ('mov', 'x3, #0x0'),
    0x17dc28: ('mov', 'x0, #0xffffffffffffff10'),
    0x17dc2c: ('bl', '0xf6088'),
    0x150abc: ('cbz', 'x0, 0x150c14'),
    0x150acc: ('ldr', 'x0, [x0, #64]'),
    0x150ad0: ('cbz', 'x0, 0x150b88'),
    0x150ad4: ('ldrb', 'w5, [x19, #136]'),
    0x150adc: ('ldrb', 'w3, [x19, #137]'),
    0x150ae4: ('ldrb', 'w19, [x19, #138]'),
    0x150b18: ('bl', '0x1509b0'),
    0x150b24: ('b.hi', '0x150bb8'),
    0x150b28: ('b.cc', '0x150b60'),
    0x150b6c: ('bl', '0x150800'),
    0x150b74: ('mov', 'w0, #0x0'),
    0x150c0c: ('mov', 'w0, #0xffffffff'),
    0x1509d4: ('cmp', 'w19, #0x40'),
    0x1509e4: ('cmp', 'w1, #0x1'),
    0x150a00: ('mov', 'w0, #0x13'),
    0x150a04: ('cmp', 'w19, #0x6'),
    0x150a08: ('csel', 'w0, w0, wzr, cc'),
    0x150a4c: ('bl', '0x10ada0'),
    0x150a60: ('cmp', 'w0, #0x3e7'),
    0x1516ec: ('bl', '0x1558a8'),
    0x1516f0: ('cmp', 'w0, #0x1'),
    0x151710: ('bl', '0x1b2718'),
    0x151728: ('bl', '0x1b2718'),
    0x151740: ('bl', '0x1b2718'),
    0x151758: ('bl', '0x1b2718'),
    0x151764: ('mov', 'w0, #0xffffff84'),
    0x1517e8: ('bl', '0x14e380'),
    0x1517f4: ('mov', 'w0, #0xffffff80'),
    0x1518c8: ('b', '0x150330'),
    0x151920: ('mov', 'w0, #0x100'),
    0x151928: ('cbz', 'w0, 0x151920'),
    0x151934: ('b', '0x151920'),
    0x1558b8: ('ldr', 'x0, [x0, #160]'),
    0x1558cc: ('ldr', 'x1, [x1, #168]'),
    0xf6088: ('smc', '#0x0'),
}
STRINGS = {
    0x23f9c8: b'KERNEL REV. CHECK FAIL. DEVICE:%d, BINARY:%d (%s)\n',
    0x23fa00: b'KERNEL RB count: DEVICE:%d, BINARY:%d (%s)\n',
    0x23fe38: b'Only official released binaries are allowed to be flashed\n',
    0x23fe78: b'Custom binary blocked due to remaining installment balance\n',
    0x23feb8: b'Custom binary(%s) blocked by OEM Lock.\n',
    0x23fee0: b'Custom binary(%s) blocked by CC Mode.\n',
    0x2401c8: b'No signinfo : (%s)\n',
    0x240200: b'Binaryname has changed (%s) -> (%s)\n',
    0x240228: b'%s: Binaryname is valid (%s)\n',
    0x240270: b' This is a non-secure chip. Skip.\n',
    0x2402c0: b'%s: There is no signature\n',
    0x242a98: b'Verify_Signature_Ecdsa',
    0x23d8d0: b'Prenormal', 0x229d10: b'Locked',
    0x23d8e0: b'Active', 0x262180: b'Error',
    0x23f700: b'[EFUSE] ARP device. skip WB fusing.\n',
    0x23f728: b'[EFUSE] Set warranty bit(0x%llx)\n',
    0x23f750: b'[EFUSE] warranty bit is already set.\n',
}


def pointer_names(data, table, count, delta, max_length=127):
    """Read bounded file-backed C strings, preserving exact names and order."""
    if (any(type(x) is not int for x in (table, count, delta, max_length))
            or table < 0 or not 1 <= count <= 256 or delta < 0 or max_length < 1
            or table > len(data) or count*8 > len(data)-table):
        raise ValueError('invalid name-table bounds')
    result = []
    for index in range(count):
        pointer, = struct.unpack_from('<Q', data, table+index*8)
        offset = pointer-delta
        if not 0 <= offset < len(data):
            raise ValueError('name pointer outside file')
        end = data.find(b'\0', offset, min(len(data), offset+max_length+1))
        if end <= offset:
            raise ValueError('name is empty or not terminated within bound')
        try:
            name = data[offset:end].decode('ascii')
        except UnicodeError as error:
            raise ValueError('name is not ASCII') from error
        result.append(dict(index=index, pointer=hex(pointer), file_offset=hex(offset), name=name))
    return result


def store_unsigned_x(word):
    if type(word) is not int or not 0 <= word <= 0xffffffff or word & 0xffc00000 != 0xf9000000:
        raise ValueError('expected STR X unsigned immediate')
    return word & 31, (word >> 5) & 31, ((word >> 10) & 0xfff)*8


def request_fields(words):
    first, second, base, offset = pair_store_x(words[0x17dbfc])
    source, single_base, single_offset = store_unsigned_x(words[0x17dbf8])
    if (first, second, base, offset, source, single_base, single_offset) != (21, 22, 19, 40, 2, 19, 56):
        raise ValueError('request descriptor field binding differs')
    return {'40': 'original X0: image pointer (u64)',
            '48': 'original X1: sign-extended W length represented as u64',
            '56': 'original X2: signature/trailer pointer (u64)'}


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for low, high in BLOCKS.values():
        parsed = parse_lines(subprocess.check_output(command + [
            '-D', '-z', '-b', 'binary', '-m', 'aarch64', f'--start-address={low}',
            f'--stop-address={high}', str(Path(path).resolve())], text=True))
        if lines.keys() & parsed.keys():
            raise ValueError('duplicate GNU PC across blocks')
        lines.update(parsed)
    branches = verify_disassembly(data, lines, BLOCKS, SELECTED)
    words = {pc: row[0] for pc, row in lines.items()}
    register, table = page_plus_add(words, 0x1526fc, 0x152724)
    length_register, width, size = wide_constant([words[0x15271c]])
    if (register, length_register, width) != (1, 2, 64) or size % 8:
        raise ValueError('unexpected selector table location or extent')
    names = pointer_names(data, table, size//8, DELTA)
    fields = request_fields(words)
    register, width, smc = wide_constant([words[0x17dc28]])
    if (register, width) != (0, 64):
        raise ValueError('unexpected monitor identifier register')
    for offset, value in STRINGS.items():
        if data[offset:offset+len(value)+1] != value+b'\0':
            raise ValueError(f'literal differs at {offset:#x}')
    packed = b''.join(struct.pack('<II', pc, row[0]) for pc, row in sorted(lines.items()))
    return dict(mode='static_samsung_signature_rollback_and_custom_policy',
        sboot_sha256=IMAGES['sboot'][1], firmware_executed=False,
        hardware_observed=False, image_acceptance_established=False,
        gnu_words=len(lines), gnu_relative_targets=len(branches),
        selected_operand_checks=len(SELECTED), instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc): dict(word=f'{raw:08x}', op=op, args=args)
                      for pc, (raw, op, args) in sorted(lines.items())}, branches=branches,
        name_table=dict(file_offset=hex(table), bytes=size, count=len(names), entries=names,
            names_normalized_or_repaired=False),
        monitor_request=dict(x0=hex(smc), x1='u32 mode 14 or 16',
            x2='128-byte-aligned stack descriptor', x3=0, fields=fields,
            descriptor_cache_clean_bytes=192, signature_cache_clean_bytes=528,
            remaining_descriptor_bytes_initialization_established=False,
            monitor_implementation_and_result_observed=False),
        strings={hex(pc): value.decode('ascii') for pc, value in STRINGS.items()},
        local_graphs={name: summarize_local(data, low, low, high)
                      for name, (low, high) in BLOCKS.items()},
        interpretation=dict(
            selector='exact name miss returns 0 without this request; match proceeds through binary-name check, signed size >512 and monitor request',
            table_last_entry='literal VDDCAL_FWINIT_BOOT is one C string; INIT_BOOT alone is not a separate table entry',
            offsets='SignInfo pointer = base + SXTW(size)-0x310; trailer pointer = base + SXTW(size)-0x210',
            size_limit='SignInfo pointer is formed before the signed >512 guard; no complete range-validation proof',
            precheck='flag bit17 clear or an exempt name skips this binary-name check; otherwise compares SignInfo+156 prefix to partition-info+68',
            request_modes='default14; selected getter(4)==0 and unsigned base<=0x94000000 and wrapped end>0x93ffffff select16',
            request_result='low32 0 and 0xffffffff map to local0; every other nonzero low32 maps to -1',
            diagnostic_nonsecure='0xffffffff branch prints non-secure skip; this is not a live chip-security measurement',
            rollback='when context+64 nonzero, computes a u32 decimal-like revision from bytes136..138 without local digit validation',
            rollback_decision='unsigned device>binary returns -1; equal returns0; device<binary calls setter then forces0 without testing setter result',
            counter_getter='index0..5 fallback is19 when selected provisioning/read/value checks fail; index>64 returns0; not a measured hardware counter',
            custom='context getter1 or cached KG-prefix matches enter diagnostic paths; OEM/CC queries and UI/mode helpers remain opaque',
            custom_getter='context u64 pair (0,0)->0, (0,1)->1, (1,1)->2, all other combinations->-1',
            custom_returns='no local RET; one tail edge to0x150330 plus conditional call continuations and input loop at0x151920',
            custom_tail='EFUSE warranty-bit diagnostics; context+72/+80 select skips versus opaque f88c0/f8968 calls; no hardware effect observed'),
        limits=[
            'three local layers are distinct; none alone establishes physical image acceptance or a bypass',
            'monitor service, live revision counters, provisioning, KG/OEM/CC state and descriptor contents were not acquired',
            'ECDSA is a diagnostic name here, not a verified identification of the secure implementation',
            'no claim of initialized descriptor padding, valid complete memory extents or successful counter persistence',
            'name matching and returned zero apply only to the selected local path, not the whole boot chain',
            'graphs keep opaque normal-return edges; labels, repeated getters and runtime preservation are not evaluated'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_samsung_checks: {error}\n')


if __name__ == '__main__':
    main()
