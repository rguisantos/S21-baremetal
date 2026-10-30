#!/usr/bin/env python3
"""Inspect hash-bound HZC2 rollback/RPMB packets and secure MAC/nonce requests."""
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
from inspect_lk_build_id import load_unsigned_w, page_plus_add
from inspect_lk_embedded_key import adrp
from inspect_lk_payload_return import summarize_local
from inspect_lk_precopy_measurement import verify_disassembly
from inspect_lk_samsung_checks import store_unsigned_x


BLOCKS = {
    'counter_setter': (0x150800, 0x1509b0),
    'counter_getter': (0x1509b0, 0x150aa4),
    'read_gate': (0x10ada0, 0x10addc),
    'write_gate': (0x10ade0, 0x10ae1c),
    'read_blocks': (0x10a648, 0x10a84c),
    'write_blocks': (0x10a850, 0x10aa1c),
    'packet_dispatcher': (0x109ed8, 0x10a648),
    'mac_request': (0x109db8, 0x109ed4),
    'nonce_request': (0xf6fb0, 0xf71a0),
    'cache_clean': (0x1899f0, 0x189a40),
    'cache_invalidate': (0x189a40, 0x189a90),
    'smc_wrapper': (0xf6088, 0xf6090),
}
SELECTED = {
    0x150830: ('cmp', 'w19, #0x40'),
    0x150838: ('cmp', 'w22, #0x3e7'),
    0x15084c: ('ldr', 'w20, [x0, #880]'),
    0x150850: ('cmp', 'w20, #0x1'),
    0x150858: ('add', 'x2, x29, #0x50'),
    0x150860: ('mov', 'w1, w20'),
    0x150864: ('mov', 'w0, w20'),
    0x150868: ('bl', '0x10ada0'),
    0x150878: ('add', 'x23, x0, w19, uxtw #2'),
    0x15089c: ('stur', 'w22, [x23, #-256]'),
    0x1508a8: ('mov', 'w1, w20'),
    0x1508ac: ('mov', 'w0, w20'),
    0x1508b0: ('bl', '0x10ade0'),
    0x1508b8: ('cbnz', 'w0, 0x150950'),
    0x1508ec: ('tbz', 'w0, #17, 0x150848'),
    0x1509e0: ('ldr', 'w1, [x0, #880]'),
    0x150a3c: ('ret', ''),
    0x150a4c: ('bl', '0x10ada0'),
    0x10ada4: ('ldr', 'w4, [x4, #872]'),
    0x10ada8: ('cbz', 'w4, 0x10adb0'),
    0x10adac: ('b', '0x10a648'),
    0x10ade4: ('ldr', 'w4, [x4, #872]'),
    0x10ade8: ('cbnz', 'w4, 0x10ae18'),
    0x10ae18: ('b', '0x10a850'),
    0x10a64c: ('cmp', 'w1, wzr'),
    0x10a66c: ('b.le', '0x10a780'),
    0x10a684: ('mov', 'w23, w2'),
    0x10a6ac: ('strh', 'w20, [x19, #6]'),
    0x10a6b0: ('str', 'w23, [x19, #28]'),
    0x10a6c0: ('bl', '0x109ed8'),
    0x10a6d8: ('strh', 'w25, [x0]'),
    0x10a6e0: ('bl', '0x1b2290'),
    0x10a6e4: ('cbnz', 'w0, 0x10a7a8'),
    0x10a6f0: ('cbnz', 'w22, 0x10a7e0'),
    0x10a6f4: ('cbnz', 'w25, 0x10a818'),
    0x10a710: ('strh', 'w28, [x19]'),
    0x10a720: ('strh', 'w27, [x19, #4]'),
    0x10a724: ('str', 'w26, [x19, #32]'),
    0x10a734: ('bl', '0xf6fb0'),
    0x10a748: ('cbz', 'w22, 0x10a6a8'),
    0x10a8b8: ('bl', '0xf6fb0'),
    0x10a8bc: ('cbnz', 'w0, 0x10a9d8'),
    0x10a8dc: ('strh', 'w1, [x19]'),
    0x10a8e0: ('bl', '0x109ed8'),
    0x10a8f0: ('strh', 'w0, [x24]'),
    0x10a8fc: ('bl', '0x1b2290'),
    0x10a904: ('cbnz', 'w0, 0x10a9a0'),
    0x10a908: ('cbnz', 'w25, 0x10aa08'),
    0x10a90c: ('cmp', 'w23, wzr'),
    0x10a910: ('ldr', 'w25, [x19, #8]'),
    0x10a914: ('b.le', '0x10a9b4'),
    0x10a930: ('cbnz', 'w1, 0x10a9f0'),
    0x10a94c: ('strh', 'w20, [x19, #6]'),
    0x10a950: ('str', 'w21, [x19, #28]'),
    0x10a958: ('strh', 'w27, [x19]'),
    0x10a960: ('strh', 'w26, [x19, #4]'),
    0x10a968: ('str', 'w28, [x19, #8]'),
    0x10a96c: ('bl', '0x109ed8'),
    0x10a97c: ('strh', 'w1, [x24]'),
    0x10a980: ('cbz', 'w0, 0x10a930'),
    0x109df4: ('str', 'x2, [x21, #16]'),
    0x109df8: ('stp', 'x19, x23, [x21]'),
    0x109dfc: ('bl', '0x1899f0'),
    0x109e08: ('bl', '0x1899f0'),
    0x109e14: ('bl', '0x189a40'),
    0x109e20: ('subs', 'w20, w20, #0x1'),
    0x109e24: ('b.eq', '0x109ea8'),
    0x109e28: ('mov', 'x0, #0x1018'),
    0x109e2c: ('mov', 'x3, #0x0'),
    0x109e30: ('mov', 'x2, x21'),
    0x109e34: ('mov', 'x1, #0x3'),
    0x109e38: ('movk', 'x0, #0xc200, lsl #16'),
    0x109e3c: ('bl', '0xf6088'),
    0x109e40: ('cmp', 'w0, #0x20, lsl #12'),
    0x109e48: ('b.eq', '0x109e20'),
    0x109e4c: ('cbnz', 'w0, 0x109e78'),
    0x109e58: ('bl', '0x189a40'),
    0x109eb8: ('mov', 'w0, #0x100'),
    0x109ebc: ('movk', 'w0, #0x8, lsl #16'),
    0x109ee0: ('ldrh', 'w1, [x0]'),
    0x109ee8: ('sub', 'w1, w1, #0x1'),
    0x109ef0: ('stp', 'x19, x20, [sp, #16]'),
    0x109f00: ('cmp', 'w1, #0x3'),
    0x109f08: ('b.hi', '0x10a064'),
    0x109f20: ('ldrh', 'w0, [x0, w1, uxtw #1]'),
    0x109f28: ('add', 'x0, x1, w0, sxth #2'),
    0x109f2c: ('br', 'x0'),
    0x109f88: ('blr', 'x4'),
    0x109fb0: ('blr', 'x4'),
    0x109fd0: ('ldrh', 'w0, [x19, #2]'),
    0x109fd4: ('cmp', 'w0, #0x7'),
    0x109fd8: ('b.eq', '0x10a5c0'),
    0x10a008: ('bl', '0x109db8'),
    0x10a030: ('bl', '0x1b2290'),
    0x10a034: ('cbz', 'w0, 0x10a578'),
    0x10a068: ('mov', 'w0, w25'),
    0x10a0f8: ('bl', '0x1af3c0'),
    0x10a14c: ('bl', '0x109db8'),
    0x10a16c: ('bl', '0x1af3c0'),
    0x10a170: ('cbnz', 'w21, 0x10a528'),
    0x10a174: ('adrp', 'x0, 0x226000'),
    0x10a198: ('blr', 'x4'),
    0x10a1b4: ('strh', 'w1, [x19]'),
    0x10a20c: ('blr', 'x4'),
    0x10a254: ('bl', '0x109db8'),
    0x10a26c: ('bl', '0x1b2290'),
    0x10a270: ('cbz', 'w0, 0x10a564'),
    0x10a314: ('strh', 'w0, [x19]'),
    0x10a390: ('ldp', 'w0, w21, [x19, #28]'),
    0x10a3a4: ('stp', 'wzr, wzr, [x19, #28]'),
    0x10a430: ('blr', 'x4'),
    0x10a48c: ('bl', '0x109db8'),
    0x10a4ac: ('bl', '0x1b2290'),
    0x10a4f0: ('bl', '0x1af3c0'),
    0x10a4fc: ('cbnz', 'w25, 0x10a53c'),
    0x10a500: ('cbz', 'w23, 0x10a550'),
    0x10a534: ('bl', '0x1b1658'),
    0x10a538: ('b', '0x10a174'),
    0x10a54c: ('cbnz', 'w23, 0x10a504'),
    0x10a5c4: ('mov', 'w25, #0x0'),
    0xf6fcc: ('lsr', 'w23, w25, #4'),
    0xf6fe4: ('mov', 'x0, #0x101c'),
    0xf6fec: ('movk', 'x0, #0xc200, lsl #16'),
    0xf6ffc: ('smc', '#0x0'),
    0xf7008: ('cmp', 'x0, x22'),
    0xf7010: ('stp', 'x1, x2, [x29, #96]'),
    0xf7030: ('cbnz', 'x20, 0xf7094'),
    0xf7034: ('bl', '0x1af3c0'),
    0xf7044: ('bl', '0x1af3c0'),
    0xf7068: ('smc', '#0x0'),
    0xf70e8: ('smc', '#0x0'),
    0x189a18: ('dc', 'cvac, x0'),
    0x189a68: ('dc', 'ivac, x0'),
}
STRINGS = {
    0x210ec8: b'[CM] get random number: start\n',
    0x210ee8: b'[CM] get random number: fail: r0:0x%llx, r1:0x%llx, r2:0x%llx, r3:0x%llx\n',
    0x226020: b'rpmb_read_block',
    0x226038: b'[CM] RPMB: exceed maximum SMC retry count\n',
    0x226068: b'[CM] RPMB: error in CryptoManager F/W: 0x%X\n',
    0x2260c0: b'scsirpmb',
    0x2260d0: b'bio open fail\n',
    0x2260e0: b'RPMB: get hmac value: fail: 0x%X\n',
    0x226108: b'HMAC compare fail !!\n',
    0x226120: b'[CM] RPMB: get hmac value: fail: 0x%X\n',
    0x226148: b'RPMB: fail to get NONCE\n',
    0x226168: b'Authentication read NONCE compare fail\n',
    0x226190: b'RPMB: rpmb_read_block(%d) fail !!!\n',
    0x2261b8: b'RPMB: rpmb_read_block fail (result: 0x%x)\n',
    0x2261e8: b'Authentication write NONCE compare fail\n',
    0x226218: b'RPMB : fail to read write coutner !!!\n',
    0x226240: b'RPMB: write block (%d) fail !!!\n',
    0x226268: b'RPMB: rpmb_write_block fail (result: 0x%x)\n',
    0x2263f0: b'RPMB: %s fail, due to parameter SMC Fail!!!\n',
    0x2267d0: b'rpmb_write_block',
}


def halfword_targets(data, table, count, base, low, high):
    """Decode signed little-endian halfword offsets scaled by four."""
    if (any(type(x) is not int for x in (table, count, base, low, high))
            or table < 0 or table % 2 or not 1 <= count <= 256
            or table > len(data) or count*2 > len(data)-table
            or low < 0 or low % 4 or high % 4 or base % 4
            or not low <= base < high <= len(data)):
        raise ValueError('invalid halfword table or code bounds')
    result = []
    for index in range(count):
        displacement, = struct.unpack_from('<h', data, table+2*index)
        target = base+4*displacement
        if not low <= target < high:
            raise ValueError('halfword target outside code bounds')
        result.append(dict(index=index, signed_halfword=displacement, target=hex(target)))
    return result


def mac_fields(words):
    """Bind only the three u64 fields actually stored before the MAC SMC."""
    pair = pair_store_x(words[0x109df8])
    single = store_unsigned_x(words[0x109df4])
    if pair != (19, 23, 21, 0) or single != (2, 21, 16):
        raise ValueError('MAC descriptor binding differs')
    return {'0': 'original X0: input pointer u64',
            '8': 'original X1: input length u64',
            '16': 'original X2: output MAC pointer u64'}


def gate_locations(words):
    result = {}
    for name, page_pc, load_pc in (
            ('read', 0x10ada0, 0x10ada4), ('write', 0x10ade0, 0x10ade4)):
        register, page = adrp(words[page_pc], page_pc)
        dest, base, offset = load_unsigned_w(words[load_pc])
        if (register, dest, base) != (4, 4, 4):
            raise ValueError('RPMB gate register binding differs')
        result[name] = hex(page+offset)
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
    register, table = page_plus_add(words, 0x109f10, 0x109f14)
    if (register, table) != (0, 0x226018):
        raise ValueError('RPMB dispatch table binding differs')
    routes = halfword_targets(data, table, 4, 0x109f30, *BLOCKS['packet_dispatcher'])
    gates = gate_locations(words)
    fields = mac_fields(words)
    mac_id = wide_constant([words[0x109e28], words[0x109e38]])
    nonce_id = wide_constant([words[0xf6fe4], words[0xf6fec]])
    if mac_id[:2] != (0, 64) or nonce_id[:2] != (0, 64):
        raise ValueError('unexpected secure request identifier register')
    for offset, value in STRINGS.items():
        if data[offset:offset+len(value)+1] != value+b'\0':
            raise ValueError(f'literal differs at {offset:#x}')
    packed = b''.join(struct.pack('<II', pc, row[0]) for pc, row in sorted(lines.items()))
    return dict(mode='static_lk_rpmb_backend_and_secure_requests',
        sboot_sha256=IMAGES['sboot'][1], firmware_executed=False,
        hardware_observed=False, counter_persistence_established=False,
        gnu_words=len(lines), gnu_relative_targets=len(branches),
        selected_operand_checks=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        blocks={name: dict(start=hex(low), end_exclusive=hex(high))
                for name, (low, high) in BLOCKS.items()},
        selected_instructions={hex(pc): dict(word=f'{lines[pc][0]:08x}', op=op, args=args)
                               for pc, (op, args) in sorted(SELECTED.items())},
        branches=branches,
        dispatch=dict(table=hex(table), base='0x109f30', entry_bytes=2,
            signed=True, scale=4, command_bias=1,
            routes=[dict(command=r['index']+1, **r) for r in routes],
            command_outside_1_to_4='returns local 0 without I/O'),
        gate_relative_addresses=gates,
        transport=dict(device_name='scsirpmb', lookup='0x18eb08',
            device_read_method_offset=144, device_write_method_offset=152,
            packet_bytes=512, packet_to_wire='reverse all 512 bytes',
            wire_mac_offset=196, mac_bytes=32, wire_authenticated_offset=228,
            authenticated_bytes_per_frame=284, callbacks_and_io_success_observed=False),
        mac_request=dict(x0=hex(mac_id[2]), x1=3,
            x2='128-byte-aligned stack descriptor', x3=0, fields=fields,
            retry_low32='0x20000', max_smc_attempts=20480,
            exhausted_return_low32='0x80100', output_mac_bytes=32,
            implementation_key_and_result_observed=False),
        nonce_request=dict(x0=hex(nonce_id[2]), x1=0, x2=0, x3=0,
            selected_request_bytes=16, data_return_registers=['X1', 'X2'],
            full_x0_test=True, frontend_tests_low32=True,
            generator_quality_and_result_observed=False),
        strings={hex(pc): value.decode('ascii') for pc, value in STRINGS.items()},
        local_graphs={name: summarize_local(data, low, low, high)
                      for name, (low, high) in BLOCKS.items()},
        interpretation=dict(
            counter='getter/setter select one 256-byte block at index1; revision index is a u32 cell inside it; not the same as the device write counter at packet+8',
            setter='index>64 or revision>999 rejected; indices0..5 can skip on queried bit17; relative8a6370 must equal1 before read/modify/write',
            frontend_gate='relative8a6368 nonzero tail-dispatches; zero returns0x40304; distinct from provisioning word8a6370',
            read='signed count<=0 returns0 without I/O; otherwise command4, low16 index, 32-bit output pointer stepping256, one-frame requests',
            read_validation='writes result u16 before nonce comparison; nonce mismatch0x50a02 precedes dispatcher/result tests',
            write='requests command2 first even for signed count<=0; stores initial result but does not test it before command3 loop',
            write_counter='initial packet+8 u32 plus iteration wraps32; low16 index and low32 input pointer stepping256',
            io_status='selected indirect read/write return registers are overwritten without a local status test',
            result7='command2 response result7 returns dispatcher0 without MAC comparison; frontend result/nonce handling remains separate',
            mac_failure='command3 copies output MAC before testing helper status; nonzero logs then rejoins I/O; not an established valid MAC',
            data_order='command4 copies decoded 256-byte payloads to caller before testing helper status and MAC comparison',
            mac_status='ordinary command2/3/4 verification retains helper status on a match; mismatch selects2',
            nonce='selected length16 consumes X1/X2 only after full X0==0; frontends test only low32 of helper return'),
        limits=[
            'static analysis only; no packet, MAC request, nonce request, key programming or storage write was executed',
            'host packet fields and byte reversal are observed; no complete protocol or memory-safety certification',
            'no runtime callback targets, successful I/O, provisioning, revision values, persistence or readback were acquired',
            'MAC service identification follows call shape and firmware literals; algorithm, key source and secure implementation remain opaque',
            'candidate EL3 monitor bytes are not validated plaintext; TEEGRIS TZSW is a distinct boundary',
            'graphs stop at indirect dispatch/SMC; other calls keep conditional normal-return edges without register or path evaluation'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_rpmb: {error}\n')


if __name__ == '__main__':
    main()
