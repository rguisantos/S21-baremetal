#!/usr/bin/env python3
"""Trace the selected HZC2 AVB key-trust callback, without executing firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_embedded_key import adrp
from inspect_lk_final_edges import flow, signed
from inspect_lk_payload_return import summarize_local
from inspect_lk_precopy_measurement import verify_disassembly


BLOCKS = {
    'boot_avb_calls_fragment': (0x17f674, 0x17f6b4),
    'wrapper_classification_fragment': (0x17f6b4, 0x17f724),
    'wrapper_orange_fragment': (0x17f960, 0x17f988),
    'wrapper_yellow_fragment': (0x17fc1c, 0x17fc30),
    'ops_installer': (0x180de8, 0x180e6c),
    'ops_exporter': (0x180e70, 0x180e9c),
    'key_callback': (0x180d50, 0x180de4),
    'secure_key_request': (0x180c50, 0x180d4c),
    'byte_comparison': (0x1b2290, 0x1b22e0),
    'key_consumer_fragment': (0x122864, 0x12289c),
    'key_rejected_fragment': (0x122bec, 0x122c48),
    'io_error_fragment': (0x123b8c, 0x123be0),
    'oom_fragment': (0x122ce8, 0x122cf0),
    'verification_epilogue': (0x122594, 0x1225bc),
    'read_unlocked_callback': (0x17ffd0, 0x180058),
    'cached_state_getter': (0x10b8f8, 0x10b92c),
    'smc_wrapper': (0xf6088, 0xf6090),
}
SELECTED = {
    0x180e58: ('stp', 'x9, x8, [x1, #40]'),
    0x180e5c: ('stp', 'x6, x5, [x1, #72]'),
    0x180e80: ('str', 'x1, [x0]'),
    0x17f690: ('ldr', 'x2, [x2, #72]'),
    0x17f694: ('blr', 'x2'),
    0x17f698: ('ldrb', 'w3, [x29, #143]'),
    0x17f6ac: ('mov', 'w4, #0x0'),
    0x17f6b0: ('bl', '0x1244b0'),
    0x17f6b4: ('mov', 'w24, w0'),
    0x17f6bc: ('cbz', 'w0, 0x17f6f8'),
    0x17f6c0: ('cbz', 'w24, 0x17f960'),
    0x17f6cc: ('b.ls', '0x17f960'),
    0x17f6fc: ('b.eq', '0x17fc1c'),
    0x17f700: ('cbnz', 'w24, 0x17f6d0'),
    0x122870: ('ldr', 'x6, [x25, #48]'),
    0x122880: ('blr', 'x6'),
    0x122888: ('b.eq', '0x122ce8'),
    0x12288c: ('cbnz', 'w0, 0x123b8c'),
    0x122890: ('ldrb', 'w0, [x29, #520]'),
    0x122894: ('cbz', 'w0, 0x122bec'),
    0x122c20: ('mov', 'w20, #0x5'),
    0x122c40: ('cbz', 'w0, 0x122b7c'),
    0x122c44: ('b', '0x122898'),
    0x123b90: ('mov', 'w20, #0x2'),
    0x122ce8: ('mov', 'w20, w0'),
    0x122598: ('mov', 'w0, w20'),
    0x180d8c: ('bl', '0x180c50'),
    0x180d90: ('mov', 'w20, w0'),
    0x180d98: ('strb', 'wzr, [x22]'),
    0x180da8: ('bl', '0x1b2290'),
    0x180db0: ('cset', 'w1, eq'),
    0x180db4: ('strb', 'w1, [x22]'),
    0x180dcc: ('mov', 'w0, w20'),
    0x180c90: ('bl', '0x1af540'),
    0x180c94: ('str', 'x23, [x21, #2240]'),
    0x180ca0: ('str', 'x22, [x19, #8]'),
    0x180ca4: ('str', 'x2, [x19, #24]'),
    0x180cd4: ('bl', '0x1af3c0'),
    0x180cfc: ('mov', 'x1, #0x10'),
    0x180d04: ('bl', '0xf6088'),
    0x17ffec: ('str', 'w2, [x29, #44]'),
    0x180034: ('bl', '0x10b8f8'),
    0x18003c: ('mov', 'w0, #0x0'),
    0x180048: ('strb', 'w1, [x19]'),
}
STRINGS = {
    0x22d7e0: b'vbmeta',
    0x258290: b'[AVB 2.0 ERR] Fail to read AVB pubkey [ret: 0x%X]\n',
    0x2582c8: b'[AVB 2.0 ERR] AVB pubkey is not matched with vbmeta\n',
    0x258300: b'avbops functions are set successfully\n',
    0x258418: b'exynos_read_is_device_unlocked',
    0x22de50: b': Error while checking public key used to sign data.\n',
    0x22ded0: b': Public key used to sign data rejected.\n',
    0x257c50: b'red', 0x257dc0: b'yellow',
    0x23ff08: b'orange', 0x23ff10: b'green',
}
SOURCE_COMMIT = 'b27a9aa53d2db7720e4d88d6950dcd979da97de3'
SOURCE_HASHES = {
    'libavb/avb_ops.h': '04e2adaaf6aae58073376afebbd6e9d699d44557681374905561e93a479f0774',
    'libavb/avb_slot_verify.h': '21bd02f65875e7cbdbd7166cee8a50d099bd9564883a50eb5342229ed7900ed4',
}


def address_pair(words, page_pc, add_pc, register):
    reg, page = adrp(words[page_pc], page_pc)
    word = words[add_pc]
    if (reg != register or word & 0xff800000 != 0x91000000
            or word & 31 != register or (word >> 5) & 31 != register):
        raise ValueError('unexpected ADRP/ADD register or encoding')
    shift = 12 if word & (1 << 22) else 0
    return page + (((word >> 10) & 0xfff) << shift)


def pair_store_x(word):
    """Decode STP X offset addressing only; reject pre/post-index and W pairs."""
    if word & 0xffc00000 != 0xa9000000:
        raise ValueError('expected STP X offset addressing')
    return word & 31, (word >> 10) & 31, (word >> 5) & 31, signed((word >> 15) & 127, 7)*8


def load_x(word):
    if word & 0xffc00000 != 0xf9400000:
        raise ValueError('expected LDR X unsigned-immediate addressing')
    return word & 31, (word >> 5) & 31, ((word >> 10) & 0xfff)*8


def resolve_bindings(words):
    table = address_pair(words, 0x180de8, 0x180df0, 1)
    exported = address_pair(words, 0x180e78, 0x180e7c, 1)
    callback = address_pair(words, 0x180e18, 0x180e3c, 8)
    unlocked = address_pair(words, 0x180e20, 0x180e40, 6)
    if exported != table:
        raise ValueError('exported ops table differs from installed table')
    first, second, base, displacement = pair_store_x(words[0x180e58])
    destination, consumer_base, slot = load_x(words[0x122870])
    if ((first, second, base) != (9, 8, 1) or (destination, consumer_base) != (6, 25)
            or slot != displacement+8 or flow(words[0x122880], 0x122880) != ('blr', destination)):
        raise ValueError('key-trust slot/register binding differs')
    first, second, base, displacement = pair_store_x(words[0x180e5c])
    destination, consumer_base, unlock_slot = load_x(words[0x17f690])
    if ((first, second, base) != (6, 5, 1) or (destination, consumer_base) != (2, 2)
            or unlock_slot != displacement or flow(words[0x17f694], 0x17f694) != ('blr', destination)):
        raise ValueError('read-unlocked slot/register binding differs')
    return dict(ops_relative_address=hex(table), exported_ops_relative_address=hex(exported),
        validate_key_slot=slot, validate_key_target_file_offset=hex(callback),
        read_unlocked_slot=unlock_slot, read_unlocked_target_file_offset=hex(unlocked),
        runtime_binding_and_preservation_established=False)


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
    binding = resolve_bindings({pc: row[0] for pc, row in lines.items()})
    for offset, value in STRINGS.items():
        if data[offset:offset+len(value)+1] != value+b'\0':
            raise ValueError(f'literal differs at {offset:#x}')
    packed = b''.join(struct.pack('<II', pc, row[0]) for pc, row in sorted(lines.items()))
    return dict(mode='static_avb_key_trust_binding', sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False, hardware_observed=False, image_acceptance_established=False,
        binding=binding, gnu_words=len(lines), gnu_relative_targets=len(branches),
        selected_operand_checks=len(SELECTED), instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc): dict(word=f'{raw:08x}', op=op, args=args)
                      for pc, (raw, op, args) in sorted(lines.items())},
        branches=branches, strings={hex(pc): value.decode('ascii') for pc, value in STRINGS.items()},
        local_graphs={name: summarize_local(data, low, low, high)
                      for name, (low, high) in BLOCKS.items()},
        source_reference=dict(repository='AndroidBootloader/platform_external_avb',
            commit=SOURCE_COMMIT, files=SOURCE_HASHES,
            scope='ABI/result-name reference, not corresponding Samsung source'),
        interpretation=dict(
            candidate_key='callback X1 is candidate bytes, X2 length, X5 out_is_trusted',
            request='0x180c50 uses label vbmeta and caller-provided stack output buffer/length',
            request_smc={'x0': '0xc200101d', 'x1': 16, 'x2': 'relative request 0xd058c0', 'x3': 0},
            request_fields={'0': 'output buffer pointer (u64)', '8': 'length (u64)',
                            '16': 'name bytes (at most eight)', '24': 'name length (u64)'},
            callback_return='request W0 is saved in W20 and returned separately from trust byte',
            callback_trust='byte comparison runs even after request error; final trust byte reflects equality',
            consumer='tests callback I/O result before trust byte; nonzero result cannot pass by a true byte alone',
            selected_local_results={'io_1': 'OOM / 1', 'io_other_nonzero': 'I/O error / 2',
                'io_0_trust_0': 'sets public-key-rejected / 5; local continuation flag may retain processing',
                'io_0_trust_nonzero': 'continues remaining verification, not final acceptance'},
            embedded_key='selected callback requests key material from monitor; equality to the embedded 0x31d740 object is not established',
            unlocked='output is initialized locally to state 1; optional getter return is ignored; reports (state != 1) with W0=0',
            wrapper_flags='read-unlocked byte passed as W3, W4=0; upstream bit0 names ALLOW_VERIFICATION_ERROR',
            wrapper_local_labels={'unlocked_1_result_0_3_4_5': 'orange',
                'unlocked_1_other_result': 'red', 'unlocked_0_result_0': 'green',
                'unlocked_0_result_5': 'yellow', 'unlocked_0_other_result': 'red'},
            classification_is_final_boot_acceptance=False),
        limits=[
            'only selected local blocks are analyzed; flags, chained keys and other callbacks have other paths',
            'normal continuation depends on opaque helpers/monitor returning and preserving required state',
            'secure request contents, active key, returned bytes and trust were not observed on the phone',
            'no claim that local error classification proves complete slot rejection or acceptance',
            'read-unlocked fallback and cached getter do not measure the live OEM/KG/FRP state',
            'signature verification, monitor key provider, runtime memory and physical diagnostic acquisition remain open'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_avb_trust: {error}\n')


if __name__ == '__main__':
    main()
