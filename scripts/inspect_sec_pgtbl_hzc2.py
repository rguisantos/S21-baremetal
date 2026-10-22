#!/usr/bin/env python3
"""Hash-bound HZC2 SEC_PGTBL caller evidence and explicit return scenarios.

Does not execute SMC, decrypt LDFW, emulate firmware or verify a memory map.
Optional register results are supplied scenarios, never observations.
"""
import argparse
import hashlib
import json
import struct

from inspect_el2_hzc2 import IMAGES, calls, read_exact, words

LDFW_SIZE = 8388608
LDFW_SHA = '9d52a013bffde6f3d734e02a359ce9323a7db75878fce60569f5989b63e057fd'
U64 = (1 << 64) - 1
U32 = (1 << 32) - 1
ALIGN = 1 << 20


def response_model(base_result, size_result):
    """Model X0 replies while preserving the callee-saved state LK expects."""
    for value in (base_result, size_result):
        if type(value) is not int or not 0 <= value <= U64:
            raise ValueError('reply must be an unsigned 64-bit register value')
    base, split = base_result, False
    if base_result == 0:
        base_status = 'invalid_type'
    elif base_result == 3:
        base, base_status = 0, 'unsupported'
    elif base_result == U64:
        base, base_status = 0, 'ldfw_not_initialized'
    elif base_result & (ALIGN - 1):
        base, base_status = 0, 'base_unaligned'
    else:
        split, base_status = True, 'base_accepted'
    size = size_result & U32
    if size == 0:
        split, size_status = False, 'invalid_type'
    elif size == 3:
        size, split, size_status = 0, False, 'unsupported'
    elif size == U32:
        size, split, size_status = 0, False, 'ldfw_not_initialized'
    else:
        # 0xfaeac uses X21 (normalized base), not the size reply in X0/W20.
        if base & (ALIGN - 1):
            raise ValueError('normalized base unexpectedly unaligned')
        size_status = 'size_low32_kept_without_alignment_check'
    end = base + size
    aligned = size % ALIGN == 0
    host_guard = split and size != 0 and aligned and end <= U64
    return dict(
        mode='supplied_register_scenario', runtime_observed=False,
        inputs=dict(base_x0=hex(base_result), size_x0=hex(size_result)),
        lk=dict(base_status=base_status, size_status=size_status,
                normalized_base=hex(base), size_low32=hex(size),
                size_reply_upper32_ignored=hex(size_result >> 32),
                w22_split_flag=int(split), x27_end_wrapped64=hex(end & U64),
                x27_addition_overflows=end > U64,
                size_alignment_was_checked=False),
        host_arithmetic_guard=dict(
            scope='split_flag_nonzero_size_1MiB_alignment_and_no_u64_wrap',
            size_is_nonzero=size != 0, size_is_1MiB_aligned=aligned, passes=host_guard,
            is_lk_validation=False),
        memory_map_verified=False, range_is_free=False,
        service_response_authenticity_verified=False,
        assumptions=['SMC/printing preserve X21 and W22 as expected by this LK',
                     'Only the two supplied X0 replies are modeled; no hardware state'])


def inspect(sboot_path, ldfw_path):
    sboot = read_exact(sboot_path, *IMAGES['sboot'])
    ldfw = read_exact(ldfw_path, LDFW_SIZE, LDFW_SHA)
    labels = (0x216298, 0x2162b8, 0x2162f8, 0x216328,
              0x216350, 0x216370, 0x2163b0, 0x2163e0, 0x216408, 0x216420)
    # Fixed instruction checks bind the interpretation to the register operands.
    if struct.unpack_from('<I', sboot, 0xfaeac)[0] != 0x92404ea1:
        raise ValueError('expected AND X1,X21,#0xfffff')
    return dict(
        mode='static_sec_pgtbl_evidence',
        inputs=dict(sboot_sha256=IMAGES['sboot'][1],
                    ldfw_size=len(ldfw), ldfw_sha256=hashlib.sha256(ldfw).hexdigest()),
        service=dict(id='0x82002060', base_selector=1, size_selector=2,
                     calls=calls(sboot, (0xfae40, 0xfae90, 0xfb678, 0xfb690)),
                     base_reply_width=64, size_reply_width_used=32),
        instruction_words=words(sboot, (
            0xfae2c, 0xfae38, 0xfae3c, 0xfae44, 0xfae48, 0xfae4c,
            0xfae54, 0xfae5c, 0xfae60, 0xfae64, 0xfae6c, 0xfae74,
            0xfae7c, 0xfae88, 0xfae8c, 0xfae94, 0xfae98, 0xfae9c,
            0xfaea4, 0xfaeac, 0xfaeb0, 0xfaeb4, 0xfaec4,
            0xfb5c0, 0xfb5c8, 0xfb5d0, 0xfb5dc, 0xfb5e4,
            0xfb5ec, 0xfb5f8, 0xfb604, 0xfb610, 0xfb618,
            0xfb628, 0xfb630, 0xfb640, 0xfb670, 0xfb674,
            0xfb67c, 0xfb680, 0xfb684, 0xfb688, 0xfb68c)),
        strings={hex(off): sboot[off:sboot.index(0, off)].decode('ascii')
                 for off in labels},
        size_alignment_test=dict(instruction='0xfaeac: AND X1,X21,#0xfffff',
                                 source_register_index=(struct.unpack_from('<I', sboot, 0xfaeac)[0] >> 5) & 31,
                                 operand='normalized_base',
                                 tests_size=False),
        ldfw_container=dict(
            header_words_le={hex(off): hex(struct.unpack_from('<I', ldfw, off)[0])
                             for off in range(0, 0x30, 4)},
            marker_offset='0x30', marker=ldfw[0x30:0x40].rstrip(b'\0').decode('ascii'),
            name_offset='0x3fc09c', name=ldfw[0x3fc09c:0x3fc0a4].decode('ascii'),
            header_field_semantics_verified=False,
            sec_pgtbl_handler_recovered=False, provider_dispatch_verified=False),
        runtime_observed=False, memory_map_verified=False,
        limits=['LDFW marker/header bytes do not establish a decryption algorithm or load address',
                'LDFW dependency is indicated by LK error strings; service provider dispatch unresolved',
                'No service invocation, signature check, firmware patch or free-memory claim'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    parser.add_argument('ldfw')
    parser.add_argument('--base-result', type=lambda value: int(value, 0))
    parser.add_argument('--size-result', type=lambda value: int(value, 0))
    args = parser.parse_args()
    if (args.base_result is None) != (args.size_result is None):
        parser.error('supply both explicit register results or neither')
    try:
        report = inspect(args.sboot, args.ldfw)
        if args.base_result is not None:
            report['scenario'] = response_model(args.base_result, args.size_result)
    except (OSError, ValueError) as error:
        parser.exit(1, f'inspect_sec_pgtbl_hzc2: {error}\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
