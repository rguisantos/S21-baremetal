#!/usr/bin/env python3
"""Identify the file-backed AVB RSA key supplied to the nominal HZC2 SHA request."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import signed
from inspect_lk_precopy_measurement import verify_disassembly


SOURCE_COMMIT = 'b27a9aa53d2db7720e4d88d6950dcd979da97de3'
SOURCE_PATH = 'libavb/avb_crypto.h'
SOURCE_SHA256 = '5aa8c148e0951a241080446456ff8ed32364918273f8b771683dcad51519c07a'
BLOCKS = {'sha_input_fragment': (0x151a74, 0x151a98)}
SUPPORTED_BITS = (2048, 4096, 8192)
SELECTED = {
    0x151a74: ('adrp', 'x1, 0x31d000'),
    0x151a78: ('adrp', 'x3, 0xcd6000'),
    0x151a7c: ('add', 'x3, x3, #0x240'),
    0x151a80: ('adrp', 'x0, 0x31d000'),
    0x151a84: ('add', 'x3, x3, #0x10'),
    0x151a88: ('mov', 'w2, #0x1'),
    0x151a8c: ('ldr', 'w1, [x1, #1848]'),
    0x151a90: ('add', 'x0, x0, #0x740'),
    0x151a94: ('bl', '0x17dae8'),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def adrp(word, pc):
    """Return destination register and signed PC-relative page, not a RAM claim."""
    if word & 0x9f000000 != 0x90000000:
        raise ValueError('expected ADRP')
    immediate = ((word >> 29) & 3) | (((word >> 5) & 0x7ffff) << 2)
    return word & 31, (pc & ~0xfff) + signed(immediate, 21)*4096


def input_locations(words):
    """Decode only the exact consumer's ADRP+ADD and ADRP+LDR W forms."""
    reg, page = adrp(words[0x151a80], 0x151a80)
    add = words[0x151a90]
    if (reg != 0 or add & 0xff800000 != 0x91000000
            or add & 31 != 0 or (add >> 5) & 31 != reg):
        raise ValueError('expected ADD X0 from its ADRP page')
    displacement = ((add >> 10) & 0xfff) << (12 if add & (1 << 22) else 0)
    blob_offset = page + displacement
    reg, page = adrp(words[0x151a74], 0x151a74)
    load = words[0x151a8c]
    if (reg != 1 or load & 0xffc00000 != 0xb9400000
            or load & 31 != 1 or (load >> 5) & 31 != reg):
        raise ValueError('expected unsigned-immediate LDR W1 from its ADRP page')
    length_offset = page + ((load >> 10) & 0xfff)*4
    return blob_offset, length_offset


def inspect_avb_rsa_key(blob):
    """Conservative format/arithmetic checks; does not verify trust or a signature."""
    if len(blob) < 8:
        raise ValueError('truncated AVB RSA header')
    bits, n0inv = struct.unpack_from('>2I', blob)
    if bits not in SUPPORTED_BITS:
        raise ValueError('unsupported AVB RSA bit count')
    width = bits//8
    if len(blob) != 8 + 2*width:
        raise ValueError('AVB RSA extent differs from its bit count')
    modulus_bytes, rr_bytes = blob[8:8+width], blob[8+width:]
    modulus = int.from_bytes(modulus_bytes, 'big')
    rr = int.from_bytes(rr_bytes, 'big')
    if modulus.bit_length() != bits:
        raise ValueError('AVB RSA modulus has inconsistent bit length')
    if not modulus & 1:
        raise ValueError('AVB RSA modulus must be odd')
    relation = (modulus*n0inv) & 0xffffffff
    if relation != 0xffffffff:
        raise ValueError('AVB RSA n0inv congruence differs')
    if rr != pow(2, 2*bits, modulus):
        raise ValueError('AVB RSA rr differs from R squared modulo n')
    return dict(format='AVB_serialized_RSA_public_key', serialized_bytes=len(blob),
        key_num_bits=bits, modulus_bit_length=modulus.bit_length(),
        implicit_exponent_from_format=65537, exponent_stored_in_blob=False,
        header_byte_order='big', modulus_bytes=width, rr_bytes=width,
        n0inv=hex(n0inv), n_times_n0inv_mod_2_to_32=hex(relation),
        rr_matches_r_squared_mod_n=True,
        host_blob_sha256=digest(blob), modulus_sha256=digest(modulus_bytes),
        rr_sha256=digest(rr_bytes),
        modulus_factorization_verified=False, signature_verified=False,
        key_trust_established=False, runtime_bytes_observed=False)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    low, high = BLOCKS['sha_input_fragment']
    lines = parse_lines(subprocess.check_output(command + [
        '-D', '-z', '-b', 'binary', '-m', 'aarch64',
        f'--start-address={low}', f'--stop-address={high}',
        str(Path(path).resolve())], text=True))
    branches = verify_disassembly(data, lines, BLOCKS, SELECTED)
    blob_offset, length_offset = input_locations({pc: row[0] for pc, row in lines.items()})
    if not 0 <= length_offset <= len(data)-4:
        raise ValueError('length field outside the identified file')
    size = struct.unpack_from('<I', data, length_offset)[0]
    if not 8 <= size <= 8+2*max(SUPPORTED_BITS)//8:
        raise ValueError('serialized key length exceeds the supported format')
    if not 0xec000 <= blob_offset <= 0x36c000-size:
        raise ValueError('serialized key outside the selected file-backed LK interval')
    key = inspect_avb_rsa_key(data[blob_offset:blob_offset+size])
    packed = b''.join(struct.pack('<II', pc, row[0]) for pc, row in sorted(lines.items()))
    return dict(mode='static_embedded_avb_key_identification',
        sboot_sha256=IMAGES['sboot'][1], firmware_executed=False,
        hardware_observed=False, image_authentication_established=False,
        source_reference=dict(repository='AndroidBootloader/platform_external_avb',
            commit=SOURCE_COMMIT, path=SOURCE_PATH, sha256=SOURCE_SHA256,
            purpose='AVB serialization reference; not the corresponding Samsung source'),
        gnu_words=len(lines), gnu_relative_targets=len(branches),
        selected_operand_checks=len(SELECTED),
        instruction_index_sha256=digest(packed),
        instructions={hex(pc): dict(word=f'{raw:08x}', op=op, args=args)
                      for pc, (raw, op, args) in sorted(lines.items())},
        branches=branches,
        input_binding=dict(blob_file_offset=hex(blob_offset),
            length_field_file_offset=hex(length_offset), length_field_byte_order='little',
            length_field_width_bytes=4, length_field_hex=data[length_offset:length_offset+4].hex(),
            length_value=size, blob_end_exclusive=hex(blob_offset+size),
            binding='initial file bytes plus the selected PC-relative consumer',
            preservation_until_call_established=False),
        key=key,
        interpretation='The initial nominal SHA input is a 1032-byte AVB RSA-4096 public key object embedded in LK, conditional on its preservation until the call.',
        limits=[
            'host hashes identify received bytes; they are not monitor output or a signature check',
            'no exhaustive writer/alias census or observation of the active input was performed',
            'format compatibility does not prove use as the trusted key for a live vbmeta image',
            'the implicit exponent is a format assumption, not a separate field measured in the blob',
            'this does not identify the monitor SHA algorithm, output or persistence',
            'image acceptance, physical load, owned RAM, entry state and record acquisition remain open'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_embedded_key: {error}\n')


if __name__ == '__main__':
    main()
