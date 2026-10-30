#!/usr/bin/env python3
"""Inspect HZC2 Build-id consistency and selected partition processing, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_embedded_key import adrp
from inspect_lk_final_edges import flow
from inspect_lk_payload_return import summarize_local
from inspect_lk_precopy_measurement import verify_disassembly


BLOCKS = {
    'build_id_check': (0x17deb0, 0x17e004),
    'zero_test': (0x151018, 0x15109c),
    'signer_classifier': (0x150480, 0x150578),
    'super_info_getter': (0x154ba0, 0x154c38),
    'super_read_helper': (0x154018, 0x15412c),
    'partition_processor': (0x17e920, 0x17f374),
    'sign_info_extractor': (0x17e2c0, 0x17e828),
    'diagnostic_reporter': (0x17e828, 0x17e91c),
    'ascii_lower': (0x1afc88, 0x1afc9c),
    'string_length': (0x1b2660, 0x1b2688),
    'case_sensitive_compare': (0x1b26b0, 0x1b2714),
    'case_insensitive_compare': (0x1b2718, 0x1b27ec),
    'byte_compare': (0x1b2290, 0x1b22e0),
    'caller_processor_fragment': (0x17f7b8, 0x17f7e0),
    'caller_reporter_fragment': (0x17fbf0, 0x17fc04),
    'caller_check_fragment': (0x17fc80, 0x17fcb8),
}
SELECTED = {
    0x17deb4: ('mov', 'w1, #0x10'),
    0x17ded0: ('bl', '0x151018'),
    0x17ded4: ('cbnz', 'w0, 0x17df88'),
    0x17ded8: ('bl', '0x154ba0'),
    0x17dee0: ('bl', '0x150480'),
    0x17dee4: ('cbz', 'w0, 0x17df68'),
    0x17deec: ('add', 'x20, x20, #0x10'),
    0x17def0: ('bl', '0x1b2660'),
    0x17def4: ('mov', 'x2, x0'),
    0x17df00: ('bl', '0x1b26b0'),
    0x17df04: ('cbz', 'w0, 0x17df74'),
    0x17df0c: ('mov', 'w0, #0x0'),
    0x17df14: ('cbnz', 'w1, 0x17df74'),
    0x17df60: ('mov', 'w0, #0xffffffff'),
    0x17df70: ('cbz', 'w1, 0x17dfc8'),
    0x17df80: ('ret', ''),
    0x17dfc0: ('mov', 'w0, #0xffffffff'),
    0x17dffc: ('mov', 'w0, #0xffffffff'),
    0x151034: ('bl', '0x18fd50'),
    0x151048: ('bl', '0x1af540'),
    0x151058: ('bl', '0x1b2290'),
    0x151064: ('cset', 'w19, eq'),
    0x151090: ('mov', 'w19, #0xffffffff'),
    0x15048c: ('mov', 'x2, #0xb'),
    0x1504a0: ('bl', '0x1b2718'),
    0x150544: ('mov', 'w0, #0x1'),
    0x15051c: ('mov', 'w0, #0x2'),
    0x1504f4: ('mov', 'w0, #0x3'),
    0x150570: ('mov', 'w0, #0x0'),
    0x154bb4: ('cbz', 'x0, 0x154c10'),
    0x154bc8: ('cbnz', 'w0, 0x154be8'),
    0x154bf4: ('mov', 'x1, #0x100'),
    0x154c04: ('bl', '0x154018'),
    0x154c08: ('b', '0x154bcc'),
    0x1540b0: ('bl', '0x11b258'),
    0x1540c0: ('bl', '0x1af3c0'),
    0x1540cc: ('mov', 'w0, #0x1'),
    0x17e320: ('cbz', 'w0, 0x17e338'),
    0x17e470: ('blr', 'x6'),
    0x17e488: ('cmp', 'x0, #0x40'),
    0x17e498: ('bl', '0x121588'),
    0x17e524: ('bl', '0x1af3c0'),
    0x17e5c0: ('bl', '0x150480'),
    0x17e5d4: ('bl', '0x1af3c0'),
    0x17e7a4: ('bl', '0x1af3c0'),
    0x17e880: ('bl', '0x1b2718'),
    0x17e898: ('bl', '0x17e2c0'),
    0x17e8d8: ('bl', '0x17e2c0'),
    0x17e8e0: ('bl', '0x150480'),
    0x17e94c: ('bl', '0x1b2570'),
    0x17e9d4: ('bl', '0x11b258'),
    0x17ea1c: ('bl', '0x1526f8'),
    0x17ea54: ('bl', '0x1af3c0'),
    0x17ea7c: ('bl', '0x150aa8'),
    0x17ea80: ('tbnz', 'w0, #31, 0x17f138'),
    0x17ea94: ('bl', '0x1b26b0'),
    0x17eac0: ('bl', '0x1b26b0'),
    0x17eaf4: ('str', 'w1, [x0, #1808]'),
    0x17eb08: ('ret', ''),
    0x17eb2c: ('blr', 'x6'),
    0x17eb44: ('cmp', 'x0, #0x40'),
    0x17eb54: ('bl', '0x121588'),
    0x17eb9c: ('cbnz', 'w0, 0x17ed08'),
    0x17ec3c: ('bl', '0x150aa8'),
    0x17ecd8: ('mov', 'w0, #0xa'),
    0x17ecdc: ('bl', '0x11e040'),
    0x17ed70: ('bl', '0x1526f8'),
    0x17edc8: ('bl', '0x150aa8'),
    0x17ee2c: ('b', '0x17ee2c'),
    0x17efe0: ('bl', '0x1b26b0'),
    0x17eff0: ('bl', '0x1516b8'),
    0x17f044: ('bl', '0x150480'),
    0x17f0ac: ('str', 'w2, [x1, #1808]'),
    0x17f0d0: ('bl', '0x1516b8'),
    0x17f2dc: ('b', '0x17f2dc'),
    0x17f370: ('bl', '0x124f68'),
    0x17f7c4: ('bl', '0x17e920'),
    0x17f7c8: ('add', 'x19, x19, #0x8'),
    0x17f7cc: ('cmp', 'x19, #0x28'),
    0x17f7d0: ('b.ne', '0x17f758'),
    0x17fbfc: ('bl', '0x17e828'),
    0x17fc00: ('b', '0x17f7fc'),
    0x17fc80: ('bl', '0x17deb0'),
    0x17fc88: ('b.lt', '0x17fc94'),
    0x17fcb4: ('b', '0x17f848'),
}
STRINGS = {
    0x2579d0: b'(VBMETA): SignInfo(Build-id) is NULL\n',
    0x2579f8: b'SUPER: Build-id does not match with the reference\n',
    0x257a30: b'(SUPER) : %s, (VBMETA) : %s\n',
    0x257a50: b'SUPER: SignInfo(Build-id) is NULL\n',
    0x232610: b'SUPER', 0x232848: b'VBMETA',
    0x23f7b0: b'SignerVer01', 0x23f7c0: b'SignerVer02', 0x23f7d0: b'SignerVer03',
    0x23da20: b'usr', 0x23da60: b'mrk',
    0x257c18: b'VBMETA %s, %s\n', 0x257c28: b'SAMSUNG %s, %s, %s\n',
    0x257c40: b'CUSTOM %s\n', 0x257c60: b'recovery kernel rp check fail\n',
    0x257b58: b'%s : No sign info\n', 0x23ff10: b'green', 0x257c50: b'red',
}


def add_immediate_x(word):
    if type(word) is not int or word & 0xff800000 != 0x91000000 or not 0 <= word <= 0xffffffff:
        raise ValueError('expected ADD X unsigned immediate')
    return word & 31, (word >> 5) & 31, ((word >> 10) & 0xfff) << (12 if word & (1 << 22) else 0)


def load_unsigned_w(word):
    if type(word) is not int or word & 0xffc00000 != 0xb9400000 or not 0 <= word <= 0xffffffff:
        raise ValueError('expected LDR W unsigned immediate')
    return word & 31, (word >> 5) & 31, ((word >> 10) & 0xfff)*4


def page_plus_add(words, page_pc, add_pc):
    register, page = adrp(words[page_pc], page_pc)
    destination, source, displacement = add_immediate_x(words[add_pc])
    if register != source:
        raise ValueError('ADRP and ADD source differ')
    return destination, page+displacement


def build_id_binding(words):
    consumer_reg, consumer = page_plus_add(words, 0x17dec0, 0x17dec8)
    producer_reg, producer = page_plus_add(words, 0x17ea48, 0x17ea50)
    super_reg, super_cache = page_plus_add(words, 0x154bc4, 0x154bd4)
    if (consumer_reg, producer_reg, super_reg) != (19, 0, 0):
        raise ValueError('unexpected cache address register')
    if consumer != producer:
        raise ValueError('Build-id producer and consumer addresses differ')
    if add_immediate_x(words[0x17deec]) != (20, 20, 16):
        raise ValueError('unexpected reference string displacement')
    register, page = adrp(words[0x17df08], 0x17df08)
    destination, base, offset = load_unsigned_w(words[0x17df10])
    if (register, destination, base) != (1, 1, 1):
        raise ValueError('unexpected policy load register')
    return dict(vbmeta_build_id_relative_address=hex(consumer),
        selected_producer_relative_address=hex(producer),
        super_sign_info_cache_relative_address=hex(super_cache),
        super_build_id_offset=16, policy_word_relative_address=hex(page+offset),
        runtime_alias_preservation_and_freshness_established=False)


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
    binding = build_id_binding(words)
    for offset, value in STRINGS.items():
        if data[offset:offset+len(value)+1] != value+b'\0':
            raise ValueError(f'literal differs at {offset:#x}')
    guard, = struct.unpack_from('<I', data, 0x17f374)
    if flow(guard, 0x17f374) != ('udf', None):
        raise ValueError('post-assertion guard differs')
    packed = b''.join(struct.pack('<II', pc, row[0]) for pc, row in sorted(lines.items()))
    return dict(mode='static_build_id_consistency_and_partition_processing',
        sboot_sha256=IMAGES['sboot'][1], firmware_executed=False,
        hardware_observed=False, image_acceptance_established=False,
        gnu_words=len(lines), gnu_relative_targets=len(branches),
        selected_operand_checks=len(SELECTED), instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc): dict(word=f'{raw:08x}', op=op, args=args)
                      for pc, (raw, op, args) in sorted(lines.items())},
        branches=branches, binding=binding,
        strings={hex(pc): value.decode('ascii') for pc, value in STRINGS.items()},
        local_graphs={name: summarize_local(data, low, low, high)
                      for name, (low, high) in BLOCKS.items()},
        partition_local_exits=dict(return_pcs=[hex(pc) for pc in range(0x17e920, 0x17f374, 4)
            if flow(words[pc], pc)[0] == 'ret'],
            fixed_self_loops=[hex(pc) for pc in range(0x17e920, 0x17f374, 4)
                if flow(words[pc], pc) == ('b', pc)],
            post_assertion_guard=dict(pc='0x17f374', word=f'{guard:08x}', kind='udf')),
        interpretation=dict(
            check='compares cached vbmeta Build-id to prefix of super SignInfo+16, after a 16-byte zero test',
            zero_test='allocates and clears a reference buffer; returns 1 if all bytes zero, 0 if different, -1 on allocation failure',
            signer_class='ASCII-case-insensitive first 11 bytes SignerVer01/02/03 map to 1/2/3; unrecognized/null returns 0',
            comparison='case-sensitive; length is strlen(vbmeta Build-id), not the reference length or fixed 16',
            selected_check_results={'zero_test_nonzero': -1,
                'recognized_super_and_prefix_equal': 0,
                'recognized_super_mismatch_policy_nonzero': 0,
                'recognized_super_mismatch_policy_zero': -1,
                'unrecognized_super_policy_nonzero': 0, 'unrecognized_super_policy_zero': -1},
            super_freshness='getter returns cache address even on allocation/selection failure; selected read result is ignored',
            super_reader='storage-helper result is not checked before copying bytes and returning 1; not proof of successful I/O',
            producer='selected vbmeta path copies strlen(SignInfo+16) bytes into the same cache; no terminator copy at this call',
            extractor='selected error exits have no explicit caller-output write; other paths copy 256 bytes, without a universal status contract',
            reporter='extracts and logs SignInfo; selected callers do not consume its return as authorization',
            processor='reads partition/footer metadata, dispatches Samsung checks and policy/reporting effects; no universal success bool is established',
            processor_opaque_checks=['0x1526f8', '0x150aa8', '0x1516b8', '0x157230'],
            processor_state='selected paths write type 1 or 3 to relative 0xaaa710; paths also update other state via helpers',
            wrapper='tests signed check result: negative forces red; partition-processor return is not tested by the name loop'),
        limits=[
            'local control, bindings and literals only; storage, cryptographic/policy callees and monitor remain opaque',
            'returning a cache pointer does not prove fresh, valid, terminated or authenticated contents',
            'prefix comparison success is not full string equality or physical image acceptance',
            'producer copy capacity, termination and overwrite history are not established by these local blocks',
            'no live policy word, Build-id, footer, SignInfo or final FDT was acquired',
            'graphs retain opaque normal-return edges and do not prove register values, feasibility or runtime preservation'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_build_id: {error}\n')


if __name__ == '__main__':
    main()
