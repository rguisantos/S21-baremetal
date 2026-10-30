#!/usr/bin/env python3
"""Inspect the HZC2 vbmeta crypto path and tables without executing firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_avb_trust import address_pair, SOURCE_COMMIT
from inspect_lk_final_edges import signed
from inspect_lk_payload_return import DELTA, summarize_local
from inspect_lk_precopy_measurement import verify_disassembly


BLOCKS = {
    'image_verifier': (0x1262b0, 0x1269a4),
    'result_name_lookup': (0x1269a8, 0x126a18),
    'montgomery_multiply': (0x126a18, 0x126b30),
    'rsa_verifier': (0x126b30, 0x127168),
    'algorithm_lookup': (0x120cd8, 0x120d08),
    'safe_add_helpers': (0x125310, 0x1253e0),
    'safe_byte_comparison': (0x1250b8, 0x1250f8),
    'slot_crypto_call_fragment': (0x1227dc, 0x122840),
    'slot_result_dispatch_fragment': (0x122cf8, 0x122e8c),
}
SELECTED = {
    0x1262dc: ('str', 'xzr, [x2]'),
    0x1262e4: ('str', 'xzr, [x19]'),
    0x1262e8: ('cmp', 'x21, #0xff'),
    0x126324: ('mov', 'w0, #0x2'),
    0x126350: ('bl', '0x1250b8'),
    0x1263b0: ('bl', '0x125b48'),
    0x1263b8: ('cmp', 'w0, #0x1'),
    0x126404: ('mov', 'w0, #0x3'),
    0x126414: ('cmp', 'w0, #0x1'),
    0x12641c: ('ldrb', 'w0, [x29, #479]'),
    0x1264c8: ('bl', '0x125310'),
    0x126520: ('bl', '0x125310'),
    0x126580: ('bl', '0x1253b0'),
    0x12670c: ('mov', 'w0, #0x1'),
    0x126710: ('cbz', 'w1, 0x126328'),
    0x126718: ('bl', '0x120cd8'),
    0x126724: ('ldr', 'x0, [x0, #16]'),
    0x12672c: ('cmp', 'x1, x0'),
    0x1267e8: ('sub', 'w0, w0, #0x1'),
    0x1267ec: ('cmp', 'w0, #0x5'),
    0x126804: ('ldrb', 'w0, [x1, w0, uxtw]'),
    0x12680c: ('add', 'x0, x1, w0, sxtb #2'),
    0x126810: ('br', 'x0'),
    0x126854: ('bl', '0x127330'),
    0x126858: ('mov', 'x2, #0x100'),
    0x126864: ('bl', '0x127388'),
    0x12687c: ('bl', '0x127388'),
    0x126884: ('bl', '0x127460'),
    0x126894: ('bl', '0x1250b8'),
    0x126898: ('cbz', 'w0, 0x126950'),
    0x1268d0: ('mov', 'w0, #0x4'),
    0x1268dc: ('bl', '0x1277f8'),
    0x1268ec: ('bl', '0x127890'),
    0x126904: ('bl', '0x127890'),
    0x12690c: ('bl', '0x127968'),
    0x12695c: ('ldp', 'x6, x7, [x24]'),
    0x12696c: ('bl', '0x126b30'),
    0x126974: ('mov', 'w0, #0x5'),
    0x126978: ('cbz', 'w1, 0x126328'),
    0x126990: ('str', 'x21, [x20]'),
    0x126998: ('str', 'x1, [x19]'),
    0x12699c: ('mov', 'w0, #0x0'),
    0x126a08: ('ldr', 'x0, [x1, w0, uxtw #3]'),
    0x126be4: ('bl', '0x120d08'),
    0x126cb0: ('cmp', 'x19, x2'),
    0x126d98: ('cmp', 'x28, x2'),
    0x126e00: ('sub', 'x20, x28, x24'),
    0x126e04: ('cmp', 'x20, x23'),
    0x126f1c: ('bl', '0x126a18'),
    0x126f20: ('mov', 'w18, #0x8'),
    0x126f34: ('bl', '0x126a18'),
    0x126f48: ('bl', '0x126a18'),
    0x126f4c: ('subs', 'w18, w18, #0x1'),
    0x126f64: ('bl', '0x126a18'),
    0x127044: ('bl', '0x1250b8'),
    0x127048: ('cbz', 'w0, 0x1270b8'),
    0x1270c4: ('mov', 'w20, #0x1'),
    0x1270c8: ('bl', '0x1250b8'),
    0x1270cc: ('cbz', 'w0, 0x127084'),
    0x1270d4: ('mov', 'w20, #0x0'),
    0x120cd8: ('cmp', 'w0, #0x6'),
    0x120cf4: ('add', 'x0, x2, x0, lsl #3'),
    0x1227f4: ('bl', '0x1262b0'),
    0x1227f8: ('cmp', 'w0, #0x5'),
    0x122800: ('b.ls', '0x122cf8'),
    0x122d00: ('ldrb', 'w0, [x0, w26, uxtw]'),
    0x122d08: ('add', 'x0, x1, w0, sxtb #2'),
    0x122d0c: ('br', 'x0'),
    0x122d14: ('mov', 'w20, #0x6'),
    0x122db4: ('mov', 'w20, #0x3'),
    0x122de0: ('cbz', 'w0, 0x122b7c'),
    0x122de4: ('b', '0x122808'),
    0x122df8: ('cbnz', 'x0, 0x122808'),
    0x122e3c: ('mov', 'w20, #0x7'),
}
RESULT_NAMES = ('OK', 'OK_NOT_SIGNED', 'INVALID_VBMETA_HEADER',
                'UNSUPPORTED_VERSION', 'HASH_MISMATCH', 'SIGNATURE_MISMATCH')
DER_PREFIX = {
    32: bytes.fromhex('3031300d060960864801650304020105000420'),
    64: bytes.fromhex('3051300d060960864801650304020305000440'),
}
SOURCE_HASHES = {
    'libavb/avb_vbmeta_image.c': '7d31dd9f0157d966e034e42de94066a242bb745e993904fe3f373d201a5a2c56',
    'libavb/avb_vbmeta_image.h': '0979deac8902cbcbd0ec1d2f94af6692ab954fe698b1bd2e8b193b7eec3a3607',
    'libavb/avb_rsa.c': '9e7d6c0b0daa3d5ea502202476d9628cb3af9a7f668f7cfd9742dfa8890fa306',
    'libavb/avb_crypto.c': 'c467f2962a7aeabc62c46727be7d112db15e9eac7d909186f06734906168989c',
}


def window(data, offset, length):
    if (type(offset) is not int or type(length) is not int or offset < 0
            or length <= 0 or offset > len(data) or length > len(data)-offset):
        raise ValueError('invalid file extent')
    return data[offset:offset+length]


def adr(word, pc):
    if word & 0x9f000000 != 0x10000000:
        raise ValueError('expected ADR')
    immediate = ((word >> 29) & 3) | (((word >> 5) & 0x7ffff) << 2)
    return word & 31, pc + signed(immediate, 21)


def relative_targets(data, table, count, base, low, high):
    """Decode signed byte offsets scaled by four, with a bounded code window."""
    if (any(type(x) is not int for x in (base, low, high)) or low < 0
            or low % 4 or high % 4 or base % 4 or not low <= base < high <= len(data)):
        raise ValueError('invalid jump code bounds')
    result = [base+signed(value, 8)*4 for value in window(data, table, count)]
    if any(not low <= target < high for target in result):
        raise ValueError('jump target outside code bounds')
    return result


def algorithm_table(data, offset, va_delta):
    """Check the seven reference-format records and all PKCS1-v1.5 prefixes.

    This is a conservative analyzer policy, not firmware input validation.
    It does not exponentiate a signature or authenticate a key.
    """
    if type(va_delta) is not int or va_delta < 0:
        raise ValueError('invalid virtual address delta')
    records = window(data, offset, 7*24)
    if records[:24] != bytes(24):
        raise ValueError('NONE algorithm record must be zero')
    result = []
    for index in range(1, 7):
        pointer, padding_size, digest_size = struct.unpack_from('<QQQ', records, index*24)
        expected_digest = 32 if index <= 3 else 64
        rsa_bytes = (256, 512, 1024)[(index-1) % 3]
        if digest_size != expected_digest or padding_size != rsa_bytes-digest_size:
            raise ValueError('algorithm sizes differ from reference format')
        padding_offset = pointer-va_delta
        padding = window(data, padding_offset, padding_size)
        prefix = DER_PREFIX[digest_size]
        fill = padding_size-3-len(prefix)
        if fill < 8 or padding != b'\x00\x01'+b'\xff'*fill+b'\x00'+prefix:
            raise ValueError('PKCS1-v1.5 padding differs')
        result.append(dict(algorithm=index, hash=f'SHA{digest_size*8}',
            rsa_bits=rsa_bytes*8, digest_bytes=digest_size,
            padding_bytes=padding_size, padding_file_offset=hex(padding_offset),
            padding_sha256=hashlib.sha256(padding).hexdigest()))
    return result


def table_locations(words):
    result = dict(
        algorithms=address_pair(words, 0x120ce4, 0x120cec, 2),
        hash_switch=address_pair(words, 0x1267fc, 0x126800, 1),
        slot_switch=address_pair(words, 0x122cf8, 0x122cfc, 0),
        result_names=address_pair(words, 0x126a00, 0x126a04, 1))
    for name, pc in (('hash_base', 0x126808), ('slot_base', 0x122d04)):
        register, target = adr(words[pc], pc)
        if register != 1:
            raise ValueError('unexpected jump base register')
        result[name] = target
    return result


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
    locations = table_locations({pc: row[0] for pc, row in lines.items()})
    hashes = relative_targets(data, locations['hash_switch'], 6, locations['hash_base'],
                              *BLOCKS['image_verifier'])
    slots = relative_targets(data, locations['slot_switch'], 6, locations['slot_base'],
                             *BLOCKS['slot_result_dispatch_fragment'])
    names = []
    for index, name in enumerate(RESULT_NAMES):
        pointer, = struct.unpack('<Q', window(data, locations['result_names']+index*8, 8))
        offset = pointer-DELTA
        if window(data, offset, len(name)+1) != name.encode()+b'\0':
            raise ValueError('vbmeta result name differs')
        names.append(dict(result=index, name=name, name_file_offset=hex(offset),
                          slot_dispatch_target=hex(slots[index])))
    algorithms = algorithm_table(data, locations['algorithms'], DELTA)
    for row, target in zip(algorithms, hashes):
        row['hash_dispatch_target'] = hex(target)
    packed = b''.join(struct.pack('<II', pc, row[0]) for pc, row in sorted(lines.items()))
    return dict(mode='static_avb_image_signature_path', sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False, hardware_observed=False,
        signature_validity_observed=False, image_acceptance_established=False,
        gnu_words=len(lines), gnu_relative_targets=len(branches),
        selected_operand_checks=len(SELECTED), instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc): dict(word=f'{raw:08x}', op=op, args=args)
                      for pc, (raw, op, args) in sorted(lines.items())},
        branches=branches, table_locations={key: hex(value) for key, value in locations.items()},
        algorithms=algorithms, vbmeta_results=names,
        local_graphs={name: summarize_local(data, low, low, high)
                      for name, (low, high) in BLOCKS.items()},
        indirect_graph_note='local_graphs stop at BR; hash/slot targets are separately decoded above',
        source_reference=dict(repository='AndroidBootloader/platform_external_avb',
            commit=SOURCE_COMMIT, files=SOURCE_HASHES,
            scope='format/algorithm/result correspondence, not corresponding Samsung source'),
        interpretation=dict(
            verifier='0x1262b0 receives data X0, length X1, optional key pointer X2 and key length X3 outputs',
            header='256-byte minimum; AVB0 comparison; host-order conversion 0x125b48 is an opaque callee in this report',
            version='selected host-order major equals 1 and minor <= 1, otherwise result 3',
            bounds='local alignment, overflow and range checks precede crypto; not a complete memory-safety proof',
            unsigned='algorithm zero returns 1 (OK_NOT_SIGNED), not result 0',
            hashed_bytes='original 256-byte header followed by the entire auxiliary block; excludes authentication block',
            hash_result='computed digest compared to authentication-block hash; mismatch returns 4',
            rsa_inputs='key in auxiliary block, signature and hash in authentication block; padding from algorithm table',
            rsa_result='false from 0x126b30 returns 5; true publishes optional key outputs then returns 0',
            rsa_checks='supported serialized key bit counts 2048/4096/8192, exact key/signature lengths, padding and digest comparisons',
            rsa_exponent='Montgomery conversion, eight pairs of squarings, final multiplication; corresponds to exponent 65537',
            slot_result_0='requires nonzero key pointer and length before selected normal continuation',
            slot_results_1_4_5='sets slot result 3; frame+248 decides cleanup versus continued processing with retained error',
            slot_result_2='sets slot result 6 then cleanup',
            slot_result_3='sets slot result 7 then cleanup',
            trust='crypto success is followed by separate key trust and remaining slot checks'),
        limits=[
            'no signature, live vbmeta, trusted monitor key or physical image acceptance was measured',
            'hash implementation, header conversion, allocations, logging and other external callees remain opaque',
            'RSA code/table correspondence does not certify arithmetic correctness, memory safety or failure handling',
            'internal modpow allocation-failure paths rejoin byte comparisons; no all-path fail-closed proof is claimed',
            'slot continuation flag origin and complete wrapper actions/return remain separate frontiers',
            'all local call continuations depend on callees returning and preserving the required state'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_avb_signature: {error}\n')


if __name__ == '__main__':
    main()
