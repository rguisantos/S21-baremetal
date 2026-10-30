#!/usr/bin/env python3
"""Inspect the exact HZC2 pre-copy marker and SHA request; execute no firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_lk_payload_return import summarize_local


BLOCKS = {
    'v2_caller_fragment': (0x12e2b8, 0x12e2d8),
    'v3_caller_fragment': (0x12e6f8, 0x12e724),
    'marker_and_measurement': (0x151a10, 0x151b10),
    'policy_byte_getter': (0x14da90, 0x14daa4),
    'bounded_string_copy': (0x1b2688, 0x1b26ac),
    'bounded_string_compare': (0x1b26b0, 0x1b2714),
    'sha_request': (0x17dae8, 0x17dbbc),
    'cache_clean': (0x1899f0, 0x189a40),
    'cache_invalidate': (0x189a40, 0x189a90),
    'smc_wrapper': (0xf6088, 0xf6090),
    'erase_public_key_request': (0xf6ac0, 0xf6b70),
}

# GNU operands are selected witnesses in addition to the raw-word/branch check.
SELECTED = {
    0x12e2c0: ('stp', 'w0, w20, [x29, #80]'),
    0x12e2c8: ('ldr', 'x0, [x29, #80]'),
    0x12e2cc: ('bl', '0x151a10'),
    0x12e2d0: ('ldrb', 'w20, [x19, #16]'),
    0x12e2d4: ('ldrb', 'w0, [x19, #9]'),
    0x12e700: ('stp', 'w0, w21, [x29, #80]'),
    0x12e708: ('ldr', 'x0, [x29, #80]'),
    0x12e70c: ('bl', '0x151a10'),
    0x12e710: ('ldrb', 'w21, [x20, #2096]'),
    0x12e720: ('ldrb', 'w0, [x20, #2098]'),
    0x151a1c: ('str', 'x0, [x29, #16]'),
    0x151a28: ('tbz', 'w0, #19, 0x151aa0'),
    0x151a40: ('ldr', 'w3, [x29, #20]'),
    0x151a54: ('add', 'x0, x3, x0'),
    0x151a58: ('bl', '0x1b26b0'),
    0x151a5c: ('cbnz', 'w0, 0x151ad4'),
    0x151a70: ('cbnz', 'w0, 0x151af0'),
    0x151a8c: ('ldr', 'w1, [x1, #1848]'),
    0x151a94: ('bl', '0x17dae8'),
    0x151a9c: ('ret', ''),
    0x151ab4: ('ldr', 'w3, [x29, #20]'),
    0x151ac8: ('add', 'x0, x3, x0'),
    0x151acc: ('bl', '0x1b26b0'),
    0x151ad0: ('cbz', 'w0, 0x151a60'),
    0x151ad8: ('tbz', 'w0, #19, 0x151b00'),
    0x151af0: ('bl', '0xf6ac0'),
    0x151af4: ('mov', 'w0, #0x0'),
    0x14da94: ('ldrb', 'w0, [x0, #1596]'),
    0x17db04: ('cmp', 'x20, x1'),
    0x17db0c: ('b.ls', '0x17db38'),
    0x17db20: ('mov', 'w0, #0xffffffff'),
    0x17db40: ('and', 'x19, x19, #0xffffffffffffff80'),
    0x17db54: ('stp', 'x22, x3, [x19]'),
    0x17db58: ('str', 'w2, [x19, #28]'),
    0x17db5c: ('str', 'w20, [x19, #16]'),
    0x17db88: ('mov', 'x0, #0xffffffffffffff0f'),
    0x17db8c: ('bl', '0xf6088'),
    0x17dba4: ('mov', 'w0, w19'),
    0x189a18: ('dc', 'cvac, x0'),
    0x189a68: ('dc', 'ivac, x0'),
    0xf6af0: ('smc', '#0x0'),
}

STRINGS = {
    0x216638: b'RECOVERY', 0x2166a8: b'BOOT',
    0x242ad8: b'SEANDROIDENFORCE',
    0x23ff18: b'[TIMA trusted boot]: SEANDROID ENFORCING\n',
    0x23ff48: b'[TIMA trusted boot]: SEAndroid MAGIC failure (recovery.img)\n',
    0x23ff88: b'[TIMA trusted boot]: SEAndroid MAGIC failure (boot.img)\n',
    0x257930: b'[ERROR] SHA input size is limited 60MB\n',
    0x210a58: b'[CM] erase public_key: start\n',
    0x210ac8: b'[CM] erase public_key: success\n',
}


def verify_disassembly(data, lines, blocks, selected=None):
    """Reject missing/extra words, overlapping ranges and divergent GNU targets."""
    expected = set()
    for low, high in blocks.values():
        if (type(low) is not int or type(high) is not int or low < 0
                or low % 4 or high % 4 or not low < high <= len(data)):
            raise ValueError('invalid aligned file-backed block')
        pcs = set(range(low, high, 4))
        if expected & pcs:
            raise ValueError('overlapping disassembly blocks')
        expected.update(pcs)
    if not expected or set(lines) != expected:
        raise ValueError('GNU coverage differs')
    branches = {}
    for pc, (raw, op, args) in sorted(lines.items()):
        if raw != struct.unpack_from('<I', data, pc)[0] or op in ('.inst', 'udf'):
            raise ValueError(f'GNU word/instruction differs at {pc:#x}')
        kind, target = flow(raw, pc)
        gnu_target = direct_target(op, args)
        if kind in ('b', 'bl', 'conditional'):
            if target != gnu_target:
                raise ValueError(f'GNU relative target differs at {pc:#x}')
            branches[hex(pc)] = dict(kind=kind, target=hex(target))
        elif gnu_target is not None:
            raise ValueError(f'unclassified GNU branch at {pc:#x}')
    for pc, operands in (selected or {}).items():
        if pc not in lines or lines[pc][1:] != operands:
            raise ValueError(f'GNU selected operands differ at {pc:#x}')
    return branches


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for low, high in BLOCKS.values():
        text = subprocess.check_output(command + ['-D', '-z', '-b', 'binary', '-m',
            'aarch64', f'--start-address={low}', f'--stop-address={high}',
            str(Path(path).resolve())], text=True)
        parsed = parse_lines(text)
        if lines.keys() & parsed.keys():
            raise ValueError('duplicate GNU PC across blocks')
        lines.update(parsed)
    branches = verify_disassembly(data, lines, BLOCKS, SELECTED)
    for pc, value in STRINGS.items():
        if data[pc:pc+len(value)+1] != value+b'\0':
            raise ValueError(f'literal differs at {pc:#x}')
    packed = b''.join(struct.pack('<II', pc, lines[pc][0]) for pc in sorted(lines))
    return dict(mode='static_precopy_marker_and_sha_request',
        sboot_sha256=IMAGES['sboot'][1], firmware_executed=False,
        hardware_observed=False, image_authentication_established=False,
        gnu_version=subprocess.check_output(command+['--version'], text=True).splitlines()[0],
        gnu_words=len(lines), gnu_relative_targets=len(branches),
        selected_operand_checks=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc): dict(word=f'{raw:08x}', op=op, args=args)
                      for pc, (raw, op, args) in sorted(lines.items())},
        branches=branches,
        strings={hex(pc): value.decode('ascii') for pc, value in STRINGS.items()},
        local_graphs={name: summarize_local(data, low, low, high)
                      for name, (low, high) in BLOCKS.items()},
        interpretation=dict(
            packed_input='X0 is saved at frame+16; the u32 at frame+20 is its high half',
            marker_address='0x94000000 + high_u32(saved_X0)', marker_compare_bytes=16,
            partition_labels='RECOVERY if flags bit19 set; BOOT otherwise; labels do not select the fixed staging address',
            policy_byte='0x14da90 returns bool(u8 at LK-relative 0xcd563c)',
            matching_marker='prints enforcing; zero policy byte requests SHA, nonzero requests public-key erase',
            mismatching_marker='re-reads flags; prints boot/recovery failure; then uses the same policy-byte gate',
            sha_arguments={'x0': 'LK-relative 0x31d740', 'w1': 'u32 at LK-relative 0x31d738',
                           'w2': 1, 'x3': 'LK-relative 0xcd6250'},
            sha_input_limit='unsigned X1 <= 0x3c00000; larger returns W0=0xffffffff',
            request_fields={'0': 'input pointer (u64)', '8': 'output pointer (u64)',
                            '16': 'input length (u32)', '28': 'mode (u32)'},
            request_alignment=128,
            sha_smc={'x0': '0xffffffffffffff0f', 'x1': 'request pointer', 'x2': 0, 'x3': 4},
            sha_return='low u32 of monitor X0 after output invalidation; handler returns it without testing',
            erase_request='SMC 0xc200101d, X1=5, X2=X3=0; actual monitor effect unknown',
            erase_path_return='handler discards helper return and returns W0=0',
            caller_return='neither selected v2/v3 continuation tests W0 before a later byte load overwrites it'),
        limits=[
            'local graphs do not evaluate registers, path feasibility or active policies',
            'normal call continuation requires the callee to return; SMC may trap or fail',
            'request bytes not listed as fields are not proven initialized by this wrapper',
            'source/length producers for 0x31d740/0x31d738 and other writers remain open',
            'SHA naming comes from a bound literal, not an observed algorithm or output',
            'no proof that the SHA input equals the raw kernel Image or the whole boot container',
            'marker match and a local zero are not signature acceptance or an unlock procedure',
            'no physical loading, memory ownership, record acquisition or recovery established'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_precopy_measurement: {error}\n')


if __name__ == '__main__':
    main()
