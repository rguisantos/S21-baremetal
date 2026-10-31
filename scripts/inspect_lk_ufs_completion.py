#!/usr/bin/env python3
"""Inspect selected HZC2 UFS descriptor, polling and response paths statically."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_avb_boot import wide_constant
from inspect_lk_avb_trust import load_x, pair_store_x
from inspect_lk_build_id import page_plus_add
from inspect_lk_embedded_key import adrp
from inspect_lk_payload_return import summarize_local
from inspect_lk_precopy_measurement import verify_disassembly
from inspect_lk_rpmb_transport import store_unsigned_b
from inspect_lk_samsung_checks import store_unsigned_x


BLOCKS = {
    'bind_request_and_lun': (0x10c7f8, 0x10c878),
    'response_parser': (0x10c888, 0x10cab8),
    'descriptor_builder': (0x10cab8, 0x10ccf0),
    'poll_status': (0x10cda0, 0x10cfb0),
    'wait_dispatch': (0x10cfb0, 0x10d07c),
    'request_executor': (0x10e568, 0x10e758),
    'security_workspace_fragment': (0x10c034, 0x10c060),
    'scsi_status_consumer': (0x10bea8, 0x10beb4),
}
SELECTED = {
    0x10bea8: ('adrp', 'x0, 0x8a7000'),
    0x10beac: ('ldrb', 'w0, [x0, #992]'),
    0x10beb0: ('b', '0x10b9c0'),
    0x10c7f8: ('add', 'x4, x1, #0x20'),
    0x10c800: ('str', 'x4, [x0, #128]'),
    0x10c808: ('str', 'x1, [x0, #96]'),
    0x10c80c: ('str', 'w2, [x0, #136]'),
    0x10c840: ('ldr', 'w3, [x1, #280]'),
    0x10c844: ('cmp', 'w3, #0x44'),
    0x10c848: ('b.eq', '0x10c870'),
    0x10c870: ('mov', 'w3, #0xc4'),
    0x10c8b4: ('ldr', 'x20, [x19, #96]'),
    0x10c8b8: ('ldp', 'x21, x0, [x19, #144]'),
    0x10c8bc: ('cbz', 'x20, 0x10c8c8'),
    0x10c8c0: ('ldrb', 'w1, [x21, #1031]'),
    0x10c8c4: ('strb', 'w1, [x20, #96]'),
    0x10c8c8: ('ldrb', 'w2, [x0, #9]'),
    0x10c8cc: ('ldrb', 'w4, [x0, #8]'),
    0x10c8d0: ('ldrb', 'w3, [x0, #10]'),
    0x10c8d4: ('ldrb', 'w1, [x0, #11]'),
    0x10c8d8: ('orr', 'x2, x4, x2, lsl #8'),
    0x10c8dc: ('mov', 'w0, #0x0'),
    0x10c8e0: ('orr', 'x2, x2, x3, lsl #16'),
    0x10c8e4: ('orr', 'x2, x2, x1, lsl #24'),
    0x10c8e8: ('cbnz', 'x2, 0x10c900'),
    0x10c900: ('ldrb', 'w1, [x21, #1024]'),
    0x10c920: ('bl', '0x10f310'),
    0x10c924: ('ldrb', 'w0, [x21, #1024]'),
    0x10c92c: ('b.eq', '0x10c9a0'),
    0x10c940: ('mov', 'w0, #0xffffffff'),
    0x10c9a0: ('ldr', 'x0, [x19, #96]'),
    0x10c9a4: ('mov', 'x2, #0x12'),
    0x10c9a8: ('add', 'x1, x21, #0x422'),
    0x10c9ac: ('add', 'x0, x0, #0x20'),
    0x10c9b0: ('bl', '0x1af3c0'),
    0x10c9b4: ('cbz', 'x20, 0x10caa8'),
    0x10cad4: ('ldr', 'w3, [x1, #16]'),
    0x10cae0: ('cbz', 'w3, 0x10caf8'),
    0x10caf8: ('strb', 'w2, [x20, #1]'),
    0x10cb00: ('strb', 'w1, [x20]'),
    0x10cb10: ('strb', 'w3, [x20, #2]'),
    0x10cb1c: ('ldr', 'w3, [x3, #16]'),
    0x10cb20: ('rev', 'w3, w3'),
    0x10cb28: ('bl', '0x1af3c0'),
    0x10cb2c: ('mov', 'x2, #0x10'),
    0x10cb30: ('ldr', 'x1, [x19, #96]'),
    0x10cb34: ('add', 'x0, x20, x2'),
    0x10cb38: ('bl', '0x1af3c0'),
    0x10cb40: ('ldr', 'w0, [x14, #16]'),
    0x10cb44: ('cbz', 'w0, 0x10cc54'),
    0x10cb48: ('add', 'w0, w0, #0xfff'),
    0x10cb4c: ('lsr', 'w10, w0, #12'),
    0x10cb50: ('cbz', 'w10, 0x10cbcc'),
    0x10cb54: ('ldr', 'x1, [x14, #24]'),
    0x10cb60: ('mov', 'w12, #0xffffffff'),
    0x10cb64: ('mov', 'w11, #0xf'),
    0x10cb68: ('ubfiz', 'x0, x3, #4, #32'),
    0x10cb88: ('strb', 'w1, [x0, #2048]'),
    0x10cb98: ('strb', 'w12, [x0, #2060]'),
    0x10cb9c: ('add', 'x1, x1, #0x1, lsl #12'),
    0x10cba0: ('strb', 'w11, [x0, #2061]'),
    0x10cbc8: ('b.ne', '0x10cb68'),
    0x10cbd4: ('uxth', 'w0, w10'),
    0x10cbd8: ('strb', 'w2, [x1, #8]'),
    0x10cbec: ('cmp', 'w2, #0x2a'),
    0x10cbf0: ('b.eq', '0x10ccb0'),
    0x10cc00: ('cmp', 'w2, #0xb5'),
    0x10cc04: ('b.eq', '0x10ccb0'),
    0x10cc10: ('mov', 'w2, #0x5000000'),
    0x10cc14: ('ubfiz', 'w0, w0, #4, #12'),
    0x10cc1c: ('strb', 'w0, [x1, #28]'),
    0x10cc34: ('strb', 'w2, [x1, #3]'),
    0x10cc3c: ('strb', 'w4, [x1, #29]'),
    0x10cc44: ('strb', 'w3, [x1, #31]'),
    0x10ccb0: ('mov', 'w2, #0x3000000'),
    0x10ccd0: ('mov', 'w2, #0x40'),
    0x10cce8: ('mov', 'w2, #0x20'),
    0x10cdb0: ('ldr', 'x0, [x0, #24]'),
    0x10cdb4: ('ldr', 'w19, [x0, #32]'),
    0x10cdb8: ('cbnz', 'w1, 0x10ce30'),
    0x10cdbc: ('tbz', 'w19, #0, 0x10ce00'),
    0x10cdc0: ('ldr', 'w0, [x0, #88]'),
    0x10cdc4: ('tbnz', 'w0, #0, 0x10ce00'),
    0x10cdc8: ('mov', 'w0, #0x0'),
    0x10cdcc: ('mov', 'w1, #0x880'),
    0x10cdd0: ('movk', 'w1, #0x3, lsl #16'),
    0x10cdd4: ('tst', 'w19, w1'),
    0x10cdd8: ('b.eq', '0x10cdf0'),
    0x10cdec: ('mov', 'w0, #0x2'),
    0x10ce08: ('tst', 'w19, w0'),
    0x10ce0c: ('b.ne', '0x10cddc'),
    0x10ce10: ('ldr', 'w0, [x20, #204]'),
    0x10ce14: ('sub', 'w1, w0, #0x1'),
    0x10ce18: ('str', 'w1, [x20, #204]'),
    0x10ce1c: ('cbz', 'w0, 0x10cef0'),
    0x10ce24: ('bl', '0xef3a8'),
    0x10ce28: ('mov', 'w0, #0x3'),
    0x10cfac: ('b', '0x10cdf0'),
    0x10cfc8: ('b.eq', '0x10d058'),
    0x10cfcc: ('cbz', 'w1, 0x10d050'),
    0x10cfd0: ('cmp', 'w1, #0x16'),
    0x10cfd4: ('b.eq', '0x10d000'),
    0x10cff0: ('mov', 'w0, #0x3'),
    0x10d000: ('mov', 'w0, #0xe360'),
    0x10d004: ('movk', 'w0, #0x16, lsl #16'),
    0x10d008: ('str', 'w0, [x19, #204]'),
    0x10d00c: ('mov', 'w1, #0x0'),
    0x10d014: ('bl', '0x10cda0'),
    0x10d018: ('cmp', 'w0, #0x3'),
    0x10d01c: ('b.eq', '0x10d00c'),
    0x10d030: ('str', 'w2, [x1, #32]'),
    0x10d044: ('str', 'w2, [x1, #320]'),
    0x10d050: ('mov', 'w0, #0x7530'),
    0x10d058: ('ldr', 'x2, [x19, #96]'),
    0x10d05c: ('mov', 'w0, #0x4600'),
    0x10d060: ('mov', 'w1, #0x9680'),
    0x10d064: ('movk', 'w0, #0x23c3, lsl #16'),
    0x10d068: ('movk', 'w1, #0x98, lsl #16'),
    0x10d06c: ('ldrb', 'w2, [x2]'),
    0x10d070: ('cmp', 'w2, #0x4'),
    0x10d074: ('csel', 'w0, w0, w1, eq'),
    0x10e5c8: ('bl', '0x10c7f8'),
    0x10e5d0: ('bl', '0x10cab8'),
    0x10e5d8: ('cbz', 'w0, 0x10e630'),
    0x10e630: ('dsb', 'st'),
    0x10e648: ('str', 'w4, [x3, #64]'),
    0x10e64c: ('str', 'w23, [x2, #88]'),
    0x10e650: ('bl', '0x10cfb0'),
    0x10e654: ('mov', 'w20, w0'),
    0x10e658: ('cbz', 'w0, 0x10e678'),
    0x10e67c: ('bl', '0x10c888'),
    0x10e680: ('mov', 'w25, w0'),
    0x10e684: ('cbnz', 'w0, 0x10e6b8'),
    0x10e694: ('cbnz', 'w25, 0x10e708'),
    0x10e708: ('mov', 'w0, w25'),
}
STRINGS = {
    0x226c38: b'Type (0x%x), OCS (0x%0x)\n',
    0x226c58: b'SCSI pscm is null\n',
    0x226d90: b'UFS QUERY Response(%02x) : ',
    0x226de8: b'UFS: UIC ERROR 0x%08x\n',
    0x226e00: b'UFS: FATAL ERROR 0x%08x\n',
    0x226e20: b'UFS UIC TIMEOUT\n',
    0x226e38: b'UFS UTP TIMEOUT\n',
    0x226eb0: b'UFS: %s: invalid type = %u\n',
}
ERROR_MASK = 0x30880


def load_unsigned_b(word):
    if (type(word) is not int or not 0 <= word <= 0xffffffff
            or word & 0xffc00000 != 0x39400000):
        raise ValueError('expected LDRB unsigned immediate')
    return word & 31, (word >> 5) & 31, (word >> 10) & 0xfff


def load_pair_x(word):
    if (type(word) is not int or not 0 <= word <= 0xffffffff
            or word & 0xffc00000 != 0xa9400000):
        raise ValueError('expected LDP X offset addressing')
    return pair_store_x(word ^ (1 << 22))


def status_binding(words):
    if (store_unsigned_x(words[0x10c808]) != (1, 0, 96)
            or load_x(words[0x10c8b4]) != (20, 19, 96)
            or load_pair_x(words[0x10c8b8]) != (21, 0, 19, 144)
            or load_unsigned_b(words[0x10c8c0]) != (1, 21, 1031)
            or store_unsigned_b(words[0x10c8c4]) != (1, 20, 96)):
        raise ValueError('response status producer binding differs')
    register, workspace = page_plus_add(words, 0x10c034, 0x10c03c)
    page_register, page = adrp(words[0x10bea8], 0x10bea8)
    destination, base, offset = load_unsigned_b(words[0x10beac])
    if (register, page_register, destination, base) != (19, 0, 0, 0) or page+offset != workspace+96:
        raise ValueError('response status consumer binding differs')
    loads = [load_unsigned_b(words[pc]) for pc in (0x10c8c8, 0x10c8cc, 0x10c8d0, 0x10c8d4)]
    if loads != [(2, 0, 9), (4, 0, 8), (3, 0, 10), (1, 0, 11)]:
        raise ValueError('OCS byte-load binding differs')
    return dict(request_pointer_host_offset=96, command_descriptor_host_offset=144,
        transfer_descriptor_host_offset=152, status_source_command_descriptor_offset=1031,
        status_destination_request_offset=96, consumer_relative_address=hex(page+offset),
        ocs_transfer_descriptor_offset=8, ocs_checked_bytes=4,
        status_store_precedes_ocs_test=True, live_freshness_established=False)


def u32(value):
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ValueError('u32 input required')
    return value


def poll_data_snapshot(interrupt_status, doorbell, budget):
    """One synthetic mode0 sample of 0x10cda0; not a device polling loop."""
    interrupt_status, doorbell, budget = map(u32, (interrupt_status, doorbell, budget))
    if interrupt_status & ERROR_MASK:
        return dict(result=2, budget_after=budget, delay_helper_called=False)
    if interrupt_status & 1 and not doorbell & 1:
        return dict(result=0, budget_after=budget, delay_helper_called=False)
    return dict(result=3 if budget else 1, budget_after=(budget-1) & 0xffffffff,
                delay_helper_called=bool(budget))


def descriptor_shape(length):
    """Selected raw length arithmetic only; allocate no payload or DMA descriptors."""
    length = u32(length)
    count = ((length+4095) & 0xffffffff) >> 12
    return dict(payload_bytes=length, prd_entries_written=count,
        prd_length_field_u16=(count & 0xfff) << 4,
        prd_stride_bytes=16, prd_segment_bytes=4096 if count else None,
        last_segment_reduced_to_payload_remainder=False)


def response_publication(ocs_word, scsi_status):
    """Selected non-null request, normal diagnostic calls; no authenticity claim."""
    ocs_word = u32(ocs_word)
    if type(scsi_status) is not int or not 0 <= scsi_status <= 255:
        raise ValueError('u8 SCSI status required')
    return dict(published_scsi_status=scsi_status, response_return=0 if ocs_word == 0 else 0xffffffff,
        diagnostic_calls_assumed_normal=True, authenticated=False, hardware_observed=False)


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
    binding = status_binding(words)
    constants = {}
    for name, pcs in {
            'mode1_other_opcode_budget': (0x10d060, 0x10d068),
            'mode1_opcode4_budget': (0x10d05c, 0x10d064),
            'mode0_budget': (0x10d050,),
            'mode22_budget': (0x10d000, 0x10d004),
            'fatal_mask': (0x10cdcc, 0x10cdd0)}.items():
        register, width, value = wide_constant([words[pc] for pc in pcs])
        if width != 32:
            raise ValueError('unexpected counter/mask width')
        constants[name] = value
    if constants['fatal_mask'] != ERROR_MASK:
        raise ValueError('poll model mask differs from instructions')
    for offset, value in STRINGS.items():
        if data[offset:offset+len(value)+1] != value+b'\0':
            raise ValueError(f'literal differs at {offset:#x}')
    packed = b''.join(struct.pack('<II', pc, row[0]) for pc, row in sorted(lines.items()))
    return dict(mode='static_lk_ufs_descriptor_completion_response',
        sboot_sha256=IMAGES['sboot'][1], firmware_executed=False,
        hardware_observed=False, counter_persistence_established=False,
        gnu_words=len(lines), gnu_relative_targets=len(branches), selected_operand_checks=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        blocks={name: dict(start=hex(low), end_exclusive=hex(high)) for name, (low, high) in BLOCKS.items()},
        selected_instructions={hex(pc): dict(word=f'{lines[pc][0]:08x}', op=op, args=args)
                               for pc, (op, args) in sorted(SELECTED.items())},
        branches=branches, response_status_binding=binding, constants=constants,
        synthetic_poll_samples=[dict(interrupt_status=hex(i), doorbell=d, budget=b,
            **poll_data_snapshot(i,d,b)) for i,d,b in ((1,0,7),(1,1,7),(0,0,0),
                (1|ERROR_MASK,0,7),(4,0,7))],
        synthetic_descriptor_shapes=[descriptor_shape(n) for n in (0,512,4096,4097,0xfffff000,0xfffff001)],
        synthetic_response_samples=[dict(ocs=hex(o), **response_publication(o,s))
                                    for o,s in ((0,0),(0,2),(15,0),(0x100,2))],
        strings={hex(pc): value.decode('ascii') for pc,value in STRINGS.items()},
        local_graphs={name: summarize_local(data, low, low, high) for name, (low, high) in BLOCKS.items()},
        interpretation=dict(
            lun='selected A2/B5 command with parent LU68 is mapped to UPIU byte2=0xc4 by0x10c7f8',
            command='CDB16 copied to command descriptor+16; expected length big-endian at+12; IN/OUT flags0x40/0x20',
            prdt='data at command descriptor+2048; stride16, address increments4096 and segment-size-minus-one4095 even for512-byte request',
            length='u32(length+4095)>>12 may wrap; encoded length field keeps low12 entry count times16; no full bounds proof',
            direction='selected nonzero A2/B5 transfer header bytes0..3 are00000005/00000003; OCS word initialized15',
            polling='RPMB mode1 calls poll mode0; completion bit0 plus doorbell bit0 clear, fatal mask clear ->0; pending ->3, expired old budget0 ->1, fatal ->2',
            budget='counter is decremented before old-zero expiration check, wrapping0 to0xffffffff; delay helper units and wall-clock bound not established',
            response_initialization='executor requests zeroing4096 bytes at host+144 on each attempt, including response status source; an initialized zero is not evidence of a fresh device write',
            response='copies command descriptor+0x407 to request+96 before testing full little-endian word at transfer descriptor+8',
            ocs='full32 zero returns0 without testing transaction type/SCSI status here; nonzero enters diagnostics and local-1 under normal calls',
            sense='nonzero OCS with type0x21 copies18 bytes from response+34 to request+32 before later pointer check; no general memory-safety proof',
            layering='executor response return, outer SCSI status classifier, RPMB result, nonce and MAC are separate checks; no counter persistence observed'),
        limits=[
            'models are synthetic host arithmetic and branch summaries, not firmware execution or hardware traces',
            'nominal LU and status bindings depend on the selected registered object and preserved pointers',
            'descriptor addresses, DMA coherence, ownership, capacity, device behavior and active host state were not acquired',
            'the PRD segment size and raw length field do not establish actual transferred byte count or overrun on hardware',
            'diagnostic callees and delay helper remain opaque; graphs retain conditional normal-return edges',
            'no HMAC authentication, fresh physical response, image acceptance or counter persistence is proved'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot',type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as error:
        parser.exit(2,f'inspect_lk_ufs_completion: {error}\n')


if __name__=='__main__':
    main()
