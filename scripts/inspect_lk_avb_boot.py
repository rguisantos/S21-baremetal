#!/usr/bin/env python3
"""Inspect HZC2 AVB wrapper returns and their selected caller, statically."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_avb_signature import adr, relative_targets
from inspect_lk_avb_trust import address_pair
from inspect_lk_embedded_key import adrp
from inspect_lk_final_edges import flow, signed
from inspect_lk_payload_return import summarize_local
from inspect_lk_precopy_measurement import verify_disassembly


BLOCKS = {
    'wrapper': (0x17f5d0, 0x17fcb8),
    'root_info_helper': (0x17f378, 0x17f540),
    'partition_list_builder': (0x17f540, 0x17f5d0),
    'caller_and_handoff': (0xfbc10, 0xfbf48),
    'key_smc_fragment': (0xf6a2c, 0xf6a48),
    'hash_smc_fragment': (0xf6b9c, 0xf6bb8),
    'os_smc_fragment': (0xf6c50, 0xf6c6c),
    'patch_smc_fragment': (0xf6d08, 0xf6d24),
    'lock_smc_fragment': (0xf6dbc, 0xf6dd8),
    'color_smc_fragment': (0xf6e6c, 0xf6e88),
    'finish_smc_fragment': (0xf6f18, 0xf6f34),
}
SELECTED = {
    0x17f6b0: ('bl', '0x1244b0'),
    0x17f6b4: ('mov', 'w24, w0'),
    0x17f7c4: ('bl', '0x17e920'),
    0x17f7f8: ('cbnz', 'w0, 0x17fbf0'),
    0x17f834: ('b.eq', '0x17fc80'),
    0x17f838: ('cmp', 'w24, wzr'),
    0x17f844: ('cbz', 'w0, 0x17f9bc'),
    0x17f8a4: ('cbz', 'w0, 0x17f9e0'),
    0x17f8c8: ('cbz', 'w0, 0x17f9e0'),
    0x17f8ec: ('cbz', 'w0, 0x17fc38'),
    0x17f924: ('str', 'wzr, [x0, #2176]'),
    0x17f92c: ('sub', 'w0, w0, #0x67'),
    0x17f938: ('mov', 'w0, #0x4002'),
    0x17f950: ('movk', 'w0, #0xfdaa, lsl #16'),
    0x17f958: ('ret', ''),
    0x17f9a8: ('cmp', 'w24, wzr'),
    0x17f9ec: ('bl', '0x156310'),
    0x17f9f4: ('bl', '0x12ecc8'),
    0x17fa08: ('str', 'w1, [x0, #2176]'),
    0x17fa10: ('sub', 'w0, w0, #0x67'),
    0x17fa14: ('cmp', 'w0, #0x12'),
    0x17fa18: ('b.hi', '0x17f938'),
    0x17fa24: ('ldrb', 'w0, [x1, w0, uxtw]'),
    0x17fa2c: ('add', 'x0, x1, w0, sxtb #2'),
    0x17fa30: ('br', 'x0'),
    0x17fa38: ('mov', 'w25, #0x1'),
    0x17fa3c: ('ldrb', 'w0, [x29, #143]'),
    0x17fa40: ('mov', 'w1, w25'),
    0x17fa48: ('eor', 'w0, w0, #0x1'),
    0x17fa4c: ('bl', '0x17f378'),
    0x17fa50: ('cbnz', 'w0, 0x17fbcc'),
    0x17facc: ('str', 'w25, [x19, #576]'),
    0x17fae4: ('str', 'w0, [x25, #4]'),
    0x17fb38: ('bl', '0x1b26b0'),
    0x17fb3c: ('cbnz', 'w0, 0x17fb44'),
    0x17fb40: ('b', '0x17fb40'),
    0x17fb44: ('ldr', 'x0, [x29, #152]'),
    0x17fb68: ('bl', '0x1af3c0'),
    0x17fb8c: ('mov', 'w0, w24'),
    0x17fba8: ('ret', ''),
    0x17fbb4: ('mov', 'w25, #0x3'),
    0x17fbc4: ('bl', '0x17f378'),
    0x17fbc8: ('cbz', 'w0, 0x17fa54'),
    0x17fbcc: ('adrp', 'x2, 0x257000'),
    0x17fbd8: ('bl', '0x1b1658'),
    0x17fbdc: ('b', '0x17fa54'),
    0x17fbe0: ('mov', 'w25, #0x2'),
    0x17fbe8: ('mov', 'w25, #0x0'),
    0x17fbfc: ('bl', '0x17e828'),
    0x17fc38: ('bl', '0x147ed8'),
    0x17fc3c: ('tbnz', 'w0, #18, 0x17f8f0'),
    0x17fc48: ('mov', 'w22, #0x2710'),
    0x17fc6c: ('b.gt', '0x17f8f0'),
    0x17fc80: ('bl', '0x17deb0'),
    0x17fc88: ('b.lt', '0x17fc94'),
    0x17fc90: ('b', '0x17f838'),
    0x17fca0: ('bl', '0x156310'),
    0x17fcb4: ('b', '0x17f848'),
    0x17f390: ('cbz', 'x2, 0x17f4d0'),
    0x17f3cc: ('bl', '0xf6f00'),
    0x17f3d0: ('mov', 'w0, w19'),
    0x17f420: ('bl', '0x1af3c0'),
    0x17f428: ('ldr', 'w0, [x0, #16]'),
    0x17f464: ('bl', '0xf6a00'),
    0x17f46c: ('cbnz', 'w0, 0x17f3cc'),
    0x17f478: ('bl', '0xf6c30'),
    0x17f48c: ('bl', '0xf6ce8'),
    0x17f49c: ('bl', '0xf6da0'),
    0x17f4ac: ('bl', '0xf6e50'),
    0x17f4c4: ('bl', '0xf6b70'),
    0x17f4e0: ('bl', '0xf6f00'),
    0x17f4e4: ('mov', 'w0, w19'),
    0x17f5a4: ('stp', 'x2, x1, [x19, #40]'),
    0x17f5c0: ('str', 'x0, [x19, #40]'),
    0xfbc68: ('bl', '0x17f5d0'),
    0xfbc6c: ('adrp', 'x0, 0x216000'),
    0xfbcc4: ('ldr', 'w0, [x0, #2176]'),
    0xfbcc8: ('bl', '0x1536e0'),
    0xfbe14: ('blr', 'x4'),
    0xf6a44: ('smc', '#0x0'),
    0xf6bb4: ('smc', '#0x0'),
    0xf6c68: ('smc', '#0x0'),
    0xf6d20: ('smc', '#0x0'),
    0xf6dd4: ('smc', '#0x0'),
    0xf6e84: ('smc', '#0x0'),
    0xf6f30: ('smc', '#0x0'),
}
LABELS = {'green': (0x23ff10, 0x17fbe8), 'yellow': (0x257dc0, 0x17fa38),
          'orange': (0x23ff08, 0x17fbe0), 'red': (0x257c50, 0x17fbb4)}
STRINGS = {
    0x257e10: b'[AVB 2.0 ERR] authentication fail [ret: 0x%X] (%s)\n',
    0x257e48: b'[AVB 2.0] authentication success (%s)\n',
    0x257e70: b'[AVB] Root of trust error ret: 0x%X\n',
    0x22d7e0: b'vbmeta', 0x257978: b'dtbo', 0x2169f0: b'boot',
    0x23baa0: b'recovery', 0x257db0: b'vendor_boot', 0x257de8: b'init_boot',
    0x2109b0: b'[CM] set publick_key: start\n',
    0x210ae8: b'[CM] set verified_boot_hash: start\n',
    0x210b88: b'[CM] set os_version & os_patch_level: start\n',
    0x210c40: b'[CM] set vendor & boot patch level: start\n',
    0x210cf8: b'[CM] set device_state: start\n',
    0x210d88: b'[CM] set boot_state: start\n',
    0x210e10: b'[CM] block verified boot commands: start\n',
}
SMC_FIELDS = {
    'key': (0xf6a2c, 0xf6a34, 0xf6a30),
    'hash': (0xf6b9c, 0xf6ba4, 0xf6ba0),
    'os_version': (0xf6c50, 0xf6c58, 0xf6c54),
    'patch_levels': (0xf6d08, 0xf6d10, 0xf6d0c),
    'lock': (0xf6dbc, 0xf6dc4, 0xf6dc0),
    'color': (0xf6e6c, 0xf6e74, 0xf6e70),
    'block_commands_request': (0xf6f18, 0xf6f20, 0xf6f1c),
}


def wide_constant(words):
    """Decode a MOVZ/MOVN followed only by MOVKs; no CPU or register model."""
    if not words:
        raise ValueError('empty wide-immediate sequence')
    result = None; destination = None; width = None
    for index, word in enumerate(words):
        if (type(word) is not int or not 0 <= word <= 0xffffffff
                or word & 0x1f800000 != 0x12800000):
            raise ValueError('expected move-wide instruction')
        bits = 64 if word >> 31 else 32
        register = word & 31
        opcode = (word >> 29) & 3
        shift = ((word >> 21) & 3)*16
        if shift >= bits or opcode == 1:
            raise ValueError('reserved move-wide encoding')
        if index == 0:
            if opcode not in (0, 2):
                raise ValueError('sequence must start with MOVZ or MOVN')
            destination, width = register, bits
            result = ((word >> 5) & 0xffff) << shift
            if opcode == 0:
                result = (~result) & ((1 << width)-1)
        else:
            if register != destination or bits != width or opcode != 3:
                raise ValueError('MOVK register/width/operation differs')
            mask = 0xffff << shift
            result = (result & ~mask) | (((word >> 5) & 0xffff) << shift)
    return destination, width, result


def direct_references(data, target, low=0xec000, high=0x20c630):
    """Scan aligned B/BL encodings only, not arbitrary controls or function pointers."""
    if (any(type(x) is not int for x in (target, low, high)) or low < 0
            or low % 4 or high % 4 or target % 4 or not 0 <= target < len(data)
            or not low < high <= len(data)):
        raise ValueError('invalid direct-reference scan bounds')
    result = []
    for pc in range(low, high, 4):
        word, = struct.unpack_from('<I', data, pc)
        if word >> 26 in (5, 37):
            kind, destination = flow(word, pc)
            if destination == target:
                result.append(dict(pc=hex(pc), kind=kind))
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
    words = {pc: row[0] for pc, row in lines.items()}
    table = address_pair(words, 0x17fa1c, 0x17fa20, 1)
    register, base = adr(words[0x17fa28], 0x17fa28)
    if register != 1:
        raise ValueError('unexpected color dispatch base register')
    targets = relative_targets(data, table, 19, base, *BLOCKS['wrapper'])
    color_codes = {}
    for name, (offset, pc) in LABELS.items():
        if data[offset:offset+len(name)+1] != name.encode()+b'\0':
            raise ValueError('color label differs')
        register, width, code = wide_constant([words[pc]])
        if (register, width) != (25, 32):
            raise ValueError('color code register differs')
        target = targets[ord(name[0])-ord('g')]
        if not target <= pc <= target+4:
            raise ValueError('color dispatch does not reach its code store')
        color_codes[name] = dict(code=code, label_file_offset=hex(offset),
                                dispatch_target=hex(target), code_pc=hex(pc))
    for offset, value in STRINGS.items():
        if data[offset:offset+len(value)+1] != value+b'\0':
            raise ValueError(f'literal differs at {offset:#x}')
    register, width, error = wide_constant([words[0x17f938], words[0x17f950]])
    if (register, width) != (0, 32) or flow(words[0x17fb40], 0x17fb40) != ('b', 0x17fb40):
        raise ValueError('wrapper error return or fixed loop differs')
    if adrp(words[0xfbc6c], 0xfbc6c)[0] != 0:
        raise ValueError('caller does not immediately overwrite X0')
    smc = {}
    for name, (start, keep, subcommand) in SMC_FIELDS.items():
        register, width, identifier = wide_constant([words[start], words[keep]])
        sub_register, sub_width, sub = wide_constant([words[subcommand]])
        if (register, width, sub_register, sub_width) != (0, 64, 1, 64):
            raise ValueError('unexpected SMC register/width')
        smc[name] = dict(x0=hex(identifier), x1=sub,
                        monitor_implementation_and_result_observed=False)
    references = direct_references(data, 0x17f5d0)
    if references != [dict(pc='0xfbc68', kind='bl')]:
        raise ValueError('aligned direct wrapper references differ')
    packed = b''.join(struct.pack('<II', pc, row[0]) for pc, row in sorted(lines.items()))
    graphs = {name: summarize_local(data, low, low, high)
              for name, (low, high) in BLOCKS.items()}
    graphs['red_fixed_loop'] = summarize_local(data, 0x17fb40, 0x17fb40, 0x17fb44)
    graphs['wrapper_after_color_dispatch'] = summarize_local(data, 0x17fa38, *BLOCKS['wrapper'])
    return dict(mode='static_avb_wrapper_returns_and_caller', sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False, hardware_observed=False, image_acceptance_established=False,
        gnu_words=len(lines), gnu_relative_targets=len(branches),
        selected_operand_checks=len(SELECTED), instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc): dict(word=f'{raw:08x}', op=op, args=args)
                      for pc, (raw, op, args) in sorted(lines.items())},
        branches=branches, color_codes=color_codes,
        color_dispatch=dict(table=hex(table), base=hex(base), first_character=ord('g'),
            targets={chr(index+ord('g')): hex(target) for index, target in enumerate(targets)}),
        wrapper_custom_error=dict(unsigned=hex(error), signed=signed(error, 32)),
        wrapper_direct_reference_scan=dict(low='0xec000', high_exclusive='0x20c630',
            references=references, indirect_calls_and_unaligned_encodings_excluded=True),
        secure_requests=smc, strings={hex(pc): value.decode('ascii') for pc, value in STRINGS.items()},
        local_graphs=graphs,
        interpretation=dict(
            labels='first character dispatches nominal green/yellow/orange/red to codes 0/1/2/3',
            slot_status='saved in W24; normal wrapper epilogue returns it, not root-info helper status',
            root_helper='errors logged, then join metadata publication; finish-request status overwritten by saved helper status',
            red='if label retains red and comparison/callees return normally, 0x17fb40 is a fixed self-loop before normal return',
            other_labels='nominal green/yellow/orange can reach normal return, subject to all intervening callees',
            custom_error='out-of-range or unrecognized first-character dispatch returns 0xfdaa4002',
            extra_check='selected initially-green/non-recovery/type1 path calls 0x17deb0; negative result overwrites label with red',
            caller='BL at 0xfbc68 returns to ADRP X0 at 0xfbc6c, discarding wrapper return immediately',
            caller_limit='persistent metadata, opaque helpers, monitor and later handoff checks still affect boot',
            phone='no unlock, flash, monitor call or diagnostic execution performed'),
        limits=[
            'full local wrapper body is covered; external callees and the monitor are not transitively certified',
            'graphs explore both conditional branches without register evaluation; BR stops, BLR keeps only an opaque normal-return edge',
            'numeric colors and labels are nominal file-backed values, not live physical state',
            'ignored return alone is not an authentication bypass: red loops and secure services remain dependencies',
            '0x17deb0, partition-processing helpers and live key provider remain frontiers',
            'aligned B/BL reference scan does not enumerate indirect callers or prove global reachability'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_avb_boot: {error}\n')


if __name__ == '__main__':
    main()
