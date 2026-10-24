#!/usr/bin/env python3
"""HZC2 EPBL buffer/MMIO provenance. Static decoding, never hardware execution.

Only the received, hash-bound sboot is accepted. MMIO addresses are decoded
from nearby literal builders; the inventory is lexical, not an execution trace.
Repeated transfer templates are checked instruction by instruction. No device
output, plaintext, physical mapping or cryptographic algorithm is fabricated.
"""
import argparse
import hashlib
import json
import struct

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_epbl_preparation import adrp_ldr_pointer, file_offset
from inspect_lk_final_edges import flow
from inspect_monitor_preparation import word

MMIO = 0x18330000
RANGES = ((0x312c, 0x3a8c), (0x3ad4, 0x4228), (0x422c, 0x4294))


def unsigned_access(w):
    """Only integer B/W/X unsigned-immediate transfers, no writeback/sign-ext."""
    forms = {0x39000000: ('write', 1), 0x39400000: ('read', 1),
             0xb9000000: ('write', 4), 0xb9400000: ('read', 4),
             0xf9000000: ('write', 8), 0xf9400000: ('read', 8)}
    form = forms.get(w & 0xffc00000)
    if form is None:
        return None
    operation, width = form
    return operation, width, w & 31, (w >> 5) & 31, ((w >> 10) & 4095) * width


def logical_immediate(w):
    """Decode A64 AND/ORR/EOR/ANDS immediate, rejecting reserved bitmasks."""
    if w & 0x1f800000 != 0x12000000:
        return None
    bits = 64 if w >> 31 else 32
    n, s, r = (w >> 22) & 1, (w >> 10) & 63, (w >> 16) & 63
    if bits == 32 and n:
        raise ValueError('reserved W logical immediate')
    length = ((n << 6) | (~s & 63)).bit_length() - 1
    if length < 1:
        raise ValueError('reserved logical immediate size')
    size = 1 << length
    levels = size - 1
    if (s & levels) == levels or size > bits:
        raise ValueError('reserved logical immediate mask')
    ones, rotate = (1 << ((s & levels) + 1)) - 1, r & levels
    mask = ((ones >> rotate) | (ones << (size - rotate))) & ((1 << size) - 1)
    mask = sum(mask << shift for shift in range(0, bits, size))
    return (w >> 29) & 3, bits, w & 31, (w >> 5) & 31, mask


def constant_before(data, pc, register, *, lower, budget=12):
    """Bounded backward slice; stop at control, unknown writer or ambiguity.

    Register 31 here is the data ZR, never an address SP. Only nearby MOVZ,
    MOVN, MOVK and ORR-immediate-from-ZR literal builders are evaluated.
    This does not propagate stack contents, MMIO values or across branches.
    """
    if type(budget) is not int or budget <= 0 or type(register) is not int or not 0 <= register <= 31:
        raise ValueError('invalid slice budget/register')
    if pc % 4 or lower % 4 or not 0 <= lower <= pc <= len(data):
        raise ValueError('invalid slice bounds')
    if register == 31:
        return 0
    overlays = []
    for at in range(pc - 4, max(lower - 1, pc - 4 * budget - 1), -4):
        w = word(data, at)
        kind, _ = flow(w, at)
        if kind not in ('linear',):
            return None
        opcode, bits = w & 0x7f800000, 64 if w >> 31 else 32
        if opcode in (0x12800000, 0x52800000, 0x72800000):
            if w & 31 != register:
                continue
            shift = ((w >> 21) & 3) * 16
            if shift >= bits:
                raise ValueError('reserved wide immediate')
            immediate = ((w >> 5) & 0xffff) << shift
            if opcode == 0x72800000:
                overlays.append((bits, shift, immediate))
                continue
            value = immediate if opcode == 0x52800000 else (~immediate & ((1 << bits) - 1))
            for width, shift, immediate in reversed(overlays):
                value = ((value & ~(0xffff << shift)) | immediate) & ((1 << width) - 1)
            return value
        logical = logical_immediate(w)
        if logical is not None:
            op, bits, rd, rn, mask = logical
            if rd != register:
                continue
            if op != 1 or rn != 31 or overlays:
                return None
            return mask
        access = unsigned_access(w)
        if access:
            if access[0] == 'read' and access[2] == register:
                return None
            continue
        # Skip a small declared set of unrelated integer writers. Values of
        # these operations are never evaluated, even when they are shifts.
        integer_writer = (w & 0x1f000000 in (0x10000000, 0x11000000)
                          or w & 0x7f800000 == 0x53000000
                          or w & 0x1f000000 in (0x0a000000, 0x0b000000))
        if integer_writer and w & 31 != register:
            continue
        return None
    return None


def mmio_inventory(data, ranges):
    accesses = []
    for start, end in ranges:
        if start % 4 or end % 4 or not 0 <= start < end <= len(data):
            raise ValueError('invalid inventory range')
        # An edge into the middle of a literal builder invalidates its slice.
        targets = {flow(word(data, pc), pc)[1] for pc in range(start, end, 4)
                   if flow(word(data, pc), pc)[0] in ('b', 'bl', 'conditional')}
        for pc in range(start, end, 4):
            transfer = unsigned_access(word(data, pc))
            if transfer is None or transfer[3] == 31:
                continue
            operation, width, register, base, offset = transfer
            # A target at the access itself may bypass its nearby builder.
            floor = max([start] + [target for target in targets if start <= target <= pc])
            address = constant_before(data, pc, base, lower=floor)
            if address is None or not MMIO <= address + offset < MMIO + 0x2000:
                continue
            absolute = address + offset
            value = constant_before(data, pc, register, lower=floor, budget=256) if operation == 'write' else None
            accesses.append(dict(pc=hex(pc), word=f'{word(data, pc):08x}', operation=operation,
                                 width_bytes=width, address=hex(absolute), offset=hex(absolute - MMIO),
                                 data_register=register, literal_write_value=None if value is None else hex(value)))
    return accesses


def expect(data, pc, *values):
    if any(word(data, pc + i * 4) != value for i, value in enumerate(values)):
        raise ValueError(f'protocol instruction template changed at {pc:#x}')


def upload_words(data, start, count, mmio_offset, source_offset):
    """MOVZ/MOVK X0; LDR W1,[X29,#n]; STR W1,[X0]."""
    result = []
    for i in range(count):
        pc, address, source = start + i * 16, mmio_offset + i * 4, source_offset + i * 4
        expect(data, pc, 0xd2800000 | address << 5, 0xf2a30660,
               0xb94003a1 | (source // 4) << 10, 0xb9000001)
        result.append(dict(load_pc=hex(pc + 8), store_pc=hex(pc + 12),
                           frame_offset=hex(source), mmio_offset=hex(address)))
    return result


def download_words(data, start, count, frame_offset):
    """MOVZ/MOVK X0; LDR W0,[X0]; STR W0,[X29,#n]."""
    result = []
    for i in range(count):
        pc, offset, target = start + i * 16, 0x11c0 + i * 4, frame_offset + i * 4
        expect(data, pc, 0xd2800000 | offset << 5, 0xf2a30660,
               0xb9400000, 0xb90003a0 | (target // 4) << 10)
        result.append(dict(read_pc=hex(pc + 8), store_pc=hex(pc + 12),
                           mmio_offset=hex(offset), frame_offset=hex(target)))
    return result


def request_control(key_bytes, mode, direction):
    """Pure arithmetic of the consumer selectors, not a hardware algorithm."""
    if type(key_bytes) is not int or key_bytes not in (16, 24, 32):
        raise ValueError('unsupported explicit material width')
    if type(mode) is not int or not 0 <= mode <= 3 or type(direction) is not int or direction not in (0, 1):
        raise ValueError('invalid explicit selector')
    return (0xf88 | direction | (0, 2, 2, 4)[mode] | {16: 0, 24: 16, 32: 32}[key_bytes])


def join_dma_pair(high, low, size):
    """Arithmetic of explicit 32-bit words; no claim about their HW binding."""
    if any(type(value) is not int or not 0 <= value < 1 << 32 for value in (high, low, size)):
        raise ValueError('explicit unsigned DMA words required')
    address = high << 32 | low
    if address + size > 1 << 64:
        raise ValueError('DMA extent exceeds 64 bits')
    return address, address + size


def bounded_poll(data, compare_pc, branch_pc, counter_offset, status):
    """Decode CMP Wn,#imm / B.LS, without supplying a status or elapsed time."""
    w = word(data, compare_pc)
    if w & 0xff80001f != 0x7100001f:
        raise ValueError('expected CMP W immediate')
    branch = word(data, branch_pc)
    kind, target = flow(branch, branch_pc)
    if branch_pc != compare_pc + 4 or kind != 'conditional' or branch & 15 != 9 or not 0 <= target < compare_pc:
        raise ValueError('expected backward B.LS after poll comparison')
    limit = ((w >> 10) & 4095) << (12 if w & (1 << 22) else 0)
    return dict(compare_pc=hex(compare_pc), loop_target=hex(target), limit=hex(limit),
                unsuccessful_reads_before_limit_exit=limit + 1, counter_offset=counter_offset,
                status_on_exhaustion=status, counter_start_and_increment_verified_separately=True,
                elapsed_time_known=False, actual_status_observed=False)


def evidence(path):
    data = read_exact(path, *IMAGES['sboot'])
    # Full-file identity plus instruction-level checks bind every transfer to
    # this firmware. No MMIO return is supplied to this program.
    seed_slot, seed = adrp_ldr_pointer(data, 0x31d0, 0x31d4)
    seed_offset = file_offset(seed, 0x02024000, 34) + 2
    expect(data, 0x31bc, 0xb833681f, 0x91001000, 0xf102001f, 0x54ffffa1,
           0xd2800000, 0x90000062, 0xf946f841, 0x8b010001, 0x39400821,
           0x38206a61, 0x91000400, 0xf100801f, 0x54ffff41)
    upload = upload_words(data, 0x3284, 32, 0x1100, 0x88)
    first_output = download_words(data, 0x3574, 12, 0x58)
    for i in range(32):
        expect(data, 0x3634 + i * 12, 0xd2800000 | (0x1100 + i * 4) << 5,
               0xf2a30660, 0xb900001f)
    # First material -> 32 bytes at frame+0x88; next 16 -> frame+0xcc.
    expect(data, 0x3834, 0xd2800000, 0x38616802, 0x38206a62, 0x91000400,
           0xf100801f, 0x54ffff81, 0xd2800000, 0x8b000023, 0x8b000262,
           0x91000400, 0xf100401f, 0x39408063, 0x39011043, 0x54ffff41)
    expect(data, 0x37f8, 0xb900ffbf, 0x910163a1, 0xb9010bbf)
    expect(data, 0x381c, 0x52800020, 0xb90103a0, 0xb90107a0, 0x52800400,
           0xf9007bb4, 0xb900cba0)
    expect(data, 0x3870, 0xaa1303e0, 0xaa1403e1, 0x94000274)
    expect(data, 0x4234, 0xb900401f, 0x52800001, 0xb900441f)
    expect(data, 0x4274, 0xf94017a1, 0xf94013a2, 0x35000060, 0xaa1303e0, 0x97fffe14)
    # Material/IV upload on this caller's key_bytes=32, mode=1 path.
    key_upload = []
    for i in range(8):
        pc = 0x3d38 + i * 16
        if i < 7:
            address = 0xd2800004 | (0x480 + i * 4) << 5
            load = 0xb9400009 | i << 10
            middle = (load, 0xf2a30664) if i == 0 else (0xf2a30664, load)
            expect(data, pc, address, *middle, 0xb9000089)
        else:
            expect(data, 0x3da8, 0xb9401c09, 0xd2809384, 0xf2a30664, 0xb9000089)
        key_upload.append(dict(request_offset=hex(i * 4), mmio_offset=hex(0x480 + i * 4)))
    for i in range(3):
        pc = 0x3e08 + i * 16
        a = 0xd2800004 | (0x430 + i * 4) << 5
        load = 0xb9400008 | (17 + i) << 10
        middle = (load, 0xf2a30664) if i == 0 else (0xf2a30664, load)
        expect(data, pc, a, *middle, 0xb9000088)
    expect(data, 0x3e38, 0xd2808784, 0xb9405008, 0xf2a30664, 0xb9000088)
    final_output = []
    for i in range(8):
        pc = 0x4168 + i * 16
        expect(data, pc, 0xd2800000 | (0x11c0 + i * 4) << 5, 0xf2a30660,
               0xb9400000, 0xb9000040 | i << 10)
        final_output.append(dict(read_pc=hex(pc + 8), destination_offset=hex(i * 4)))
    expected_slot, expected_pointer = adrp_ldr_pointer(data, 0x3880, 0x3888)
    expected_offset = file_offset(expected_pointer, 0x02024000, 36) + 4
    # The scalar byte assembly compares eight LE u32 words, not 48 bytes.
    expect(data, 0x3884, 0xb9403ba3)
    for i in range(7):
        pc = 0x388c if i == 0 else 0x38b4 + (i - 1) * 44
        block = [0x39400020 | (5 + i * 4) << 10, 0x39400022 | (4 + i * 4) << 10]
        if i:
            block.append(0xb9400283 | i << 10)
        block += [0xaa002042, 0x39400020 | (6 + i * 4) << 10, 0xaa004042,
                  0x39400020 | (7 + i * 4) << 10, 0xaa006042, 0x52822120, 0x6b02007f]
        branch_pc = pc + len(block) * 4
        block.append(0x54000001 | (((0x39e8 - branch_pc) // 4) & 0x7ffff) << 5)
        expect(data, pc, *block)
    expect(data, 0x39bc, 0x39408420, 0x39408023, 0x39408822, 0x39408c21,
           0xaa002060, 0xaa024000, 0xaa016000, 0xb9401e81, 0x6b00003f, 0x52822120, 0x1a8003e0)
    expect(data, 0x39e8, 0xd2800001, 0x38216a7f, 0x91000421, 0xf100803f,
           0x54ffffa1, 0x91011261, 0x91015273, 0x3800143f, 0xeb13003f, 0x54ffffc1)
    if data[0x4228:0x422c] != bytes((3, 0, 0, 2)):
        raise ValueError('mode table changed')
    expect(data, 0x3bb8, 0x6b1f011f, 0x5281f104, 0x5281f128, 0x1a880084)
    expect(data, 0x3c34, 0x321f0084, 0x14000002, 0x321e0084)
    expect(data, 0x3c60, 0x321c0084, 0x14000002, 0x321b0084)
    polls = []
    for reset_pc, counter, increment_pc, compare_pc, status in (
            (0x350c, 'frame+0x34', 0x3538, 0x3544, '0x1106'),
            (0x3530, 'frame+0x34', 0x37bc, 0x37c8, '0x1107'),
            (0x4060, 'consumer_sp+0xc', 0x4090, 0x409c, '0x110d'),
            (0x4088, 'consumer_sp+0xc', 0x40fc, 0x4108, '0x110e'),
            (0x4060, 'consumer_sp+0xc', 0x414c, 0x4158, '0x110c')):
        base = 29 if counter.startswith('frame') else 31
        offset = 0x34 if base == 29 else 0xc
        reset = 0xb9000000 | (offset // 4) << 10 | base << 5 | 31
        expect(data, reset_pc, reset)
        register = word(data, increment_pc) & 31
        expect(data, increment_pc, 0xb9400000 | (offset // 4) << 10 | base << 5 | register,
               0x11000400 | register << 5 | register,
               0xb9000000 | (offset // 4) << 10 | base << 5 | register)
        polls.append(bounded_poll(data, compare_pc, compare_pc + 4, counter, status))
    expect(data, 0x3fb8, 0xb9000087)
    expect(data, 0x3fc4, 0xd360fce7, 0xb9000087)
    expect(data, 0x3fd4, 0xb9000086)
    expect(data, 0x3fe0, 0xd360fcc6, 0xb9000086)
    expect(data, 0x4008, 0x52a20006, 0xb9000fff)
    expect(data, 0x4034, 0xb9400fe4, 0x11000484, 0xb9000fe4, 0x6b06009f, 0x54fffe69, 0x17fffff6)
    expect(data, 0x4020, 0xd2803184, 0xf2a30664, 0xb9400084, 0x36000f64)
    status_witnesses = []
    for pc, register, status in ((0x3adc, 3, 0x1001), (0x3ae8, 3, 0x1002),
            (0x3b0c, 3, 0x1003), (0x41f0, 3, 0x1004), (0x420c, 3, 0x1005),
            (0x4214, 3, 0x1006), (0x421c, 3, 0x1007), (0x3b1c, 3, 0x1008),
            (0x3b28, 3, 0x1009), (0x4204, 3, 0x100a), (0x3c18, 3, 0x100b),
            (0x41fc, 3, 0xfdaa0500), (0x3550, 0, 0x1106), (0x37d4, 0, 0x1107),
            (0x38ac, 0, 0x1109), (0x4164, 3, 0x110c), (0x40a8, 3, 0x110d),
            (0x4114, 3, 0x110e), (0x425c, 0, 0x1110), (0x4230, 1, 0x1111),
            (0x3bb4, 3, 0x1112)):
        if constant_before(data, pc, register, lower=max(0, pc - 16)) != status:
            raise ValueError(f'status producer changed before {pc:#x}')
        status_witnesses.append(dict(before_pc=hex(pc), register=register, value=hex(status)))
    inventory = mmio_inventory(data, RANGES)
    by_pc = {int(event['pc'], 16): event for event in inventory}
    dma_words = {offset: int(by_pc[pc]['literal_write_value'], 16)
                 for offset, pc in ((0x40, 0x34fc), (0x44, 0x34f0), (0x48, 0x3508))}
    dma_address, dma_end = join_dma_pair(dma_words[0x40], dma_words[0x44], dma_words[0x48])
    packed = b''.join(struct.pack('<II', pc, word(data, pc)) for a, b in RANGES for pc in range(a, b, 4))
    return dict(mode='static_HZC2_EPBL_protocol', sboot_sha256=IMAGES['sboot'][1],
        code_ranges=[[hex(a), hex(b)] for a, b in RANGES], instruction_count=len(packed) // 8,
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        mmio_inventory=inventory, mmio_access_count=len(inventory),
        inventory_semantics='Lexical occurrences with locally proven literal addresses; paths/returns/progress are not proven',
        first_stage=dict(seed_pointer_slot=hex(seed_slot), seed_candidate_offset=hex(seed_offset),
            seed_bytes=32, seed_sha256=hashlib.sha256(data[seed_offset:seed_offset + 32]).hexdigest(),
            scratch_frame_offset='0x88', scratch_zero_bytes=128, seed_copy_bytes=32,
            upload=upload, output=first_output, output_bytes=48,
            seed_mmio_clear_after_output_bytes=128,
            literal_dma_registers={hex(offset): hex(value) for offset, value in dma_words.items()},
            candidate_dma_layout=dict(address_high_register='0x40', address_low_register='0x44',
                size_register='0x48', candidate_address=hex(dma_address), candidate_size=hex(dma_words[0x48]),
                candidate_end_exclusive=hex(dma_end),
                basis='Same high32/low32/size spacing as the instruction-proven consumer source and destination groups',
                HZC2_register_specification_verified=False, mapping_or_contents_verified=False),
            literal_hash_configuration=dict(control='0x19', message_size_low='0x3fc', message_size_high=0,
                prior_size_registers_zero=True, algorithm_verified=False)),
        second_stage=dict(request_frame_offset='0x88', source_nominal='0x02028700',
            destination_nominal='0x02028700', source_and_destination_bytes='0xb6e0',
            candidate_file_range=['0x4700', '0xfde0'], material_bytes=32, material_source_frame_range=['0x58', '0x78'],
            iv_bytes=16, iv_source_frame_range=['0x78', '0x88'], material_upload=key_upload,
            iv_mmio_range=['0x430', '0x440'], mode=1, direction=1, extra_field_0x80=0,
            control_word=hex(request_control(32, 1, 1)),
            dma_address_fields=[dict(request_offset='0x58', low_register='0x24', high_register='0x20'),
                                dict(request_offset='0x68', low_register='0x154', high_register='0x150')],
            dma_length_fields=[dict(request_offset='0x60', register='0x28'),
                               dict(request_offset='0x70', register='0x158')],
            wrapper_context_counter_offsets=['0x40', '0x44'], wrapper_initializes_only_counters=True,
            local_material_and_iv_clear_bytes=[32, 16], hardware_material_registers_cleared_after_second_stage=False,
            final_output_pointer_is_wrapper_argument=True, final_output=final_output, final_output_bytes=32,
            final_hash_configuration='0x14 when context counters are zero',
            algorithm_inference='AES-256-CBC decryption is consistent with the pinned public SSS AES bit definitions; HZC2 hardware binding unverified'),
        comparison=dict(pointer_slot=hex(expected_slot), record_candidate_offset=hex(expected_offset - 4),
            expected_candidate_offset=hex(expected_offset), compared_bytes=32, word_order='eight little-endian u32',
            expected_sha256=hashlib.sha256(data[expected_offset:expected_offset + 32]).hexdigest(),
            mismatch_status='0x1109', actual_output_unknown=True, hash_algorithm_verified=False),
        bounded_polling=polls,
        status_witnesses=status_witnesses,
        dma_polling=dict(limit='0x10000000', final_recheck_pc='0x4028',
            all_unsuccessful_read_bound=(1 << 28) + 2, final_recheck_can_still_succeed=True,
            failure_status='0x1007', elapsed_time_known=False),
        status_paths={'0x1001': 'null request', '0x1002': 'null source/destination or zero size',
            '0x1003': 'request+0x80 nonzero', '0x1004': 'MMIO+0x404 bit2 set',
            '0x1005': 'mode above 3', '0x1006': 'material width outside 16/24/32',
            '0x1007': 'DMA completion bit0 absent at final recheck',
            '0x1008': 'direction above 1', '0x1009': 'destination capacity smaller than source size',
            '0x100a': 'MMIO+0x18c bit6 remains set', '0x100b': 'MMIO+0x18c bit0 remains set',
            '0xfdaa0500': 'MMIO+0x18c bit10 remains set',
            '0x1106': 'first stage interrupt poll exhausted', '0x1107': 'first stage output poll exhausted',
            '0x1109': '32-byte comparison mismatch', '0x110c': 'final output bit6 poll exhausted',
            '0x110d': 'partial path MMIO+0x10 bit0 poll exhausted',
            '0x110e': 'partial path MMIO+0x1010 bit4 poll exhausted',
            '0x1110': 'wrapper output argument null', '0x1111': 'context initializer argument null',
            '0x1112': 'MMIO+0x1010 mask0x50 nonzero in guarded path'},
        firmware_executed=False, mmio_executed=False, transformed_plaintext_recovered=False,
        vector_or_SMC_handler_linked=False, hardware_ready=False,
        unresolved=['Register binding and contents of candidate first-stage DMA input [0x1fc00,0x1fffc)',
            'Exact HZC2 hash configuration and hardware outputs', 'Conditional preparation gates and actual runtime mapping',
            'Prepared vector bytes, classification initialization and SMC handler bindings'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        print(json.dumps(evidence(args.sboot), indent=2))
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(2, 'EPBL protocol audit failed: ' + str(exc) + '\n')
