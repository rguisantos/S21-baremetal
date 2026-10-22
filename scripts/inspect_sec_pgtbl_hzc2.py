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
LDFW_MAGIC = 0x10adab1e
LDFW_HEADER = 0x40
LDFW_ALIGNMENT = 0x1000
HEADER_SOURCE = ('https://github.com/u-boot/u-boot/blob/'
                 '3d9115a045d2d48c28019b3d6673ab30271819f5/'
                 'board/samsung/e850-96/fw.c')
CRYPTO_SOURCE = ('https://github.com/halal-beef/Exynos9830-Firmware-Decryptor/'
                 'blob/5142272e65b8525647643131c42a0f495f60898c/decrypt-ldfws.py')


def parse_ldfw_records(data):
    """Bounded metadata parsing, not decryption or executable validation.

    Common header names follow the cited U-Boot implementation. The encryption
    flag and interval follow a related Exynos9830 parser, not recovered HZC2
    loader internals. Never interpret ciphertext as instructions or filenames
    as extraction paths. Only the received SignerVer03 trailer is supported.
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) > LDFW_SIZE:
        raise ValueError('LDFW input must be bounded bytes')
    records, names, offset = [], set(), 0
    fields = ('magic', 'size', 'init_entry', 'entry_point', 'suspend_entry',
              'resume_entry', 'start_smc_id', 'version', 'set_runtime_entry')
    while data[offset:offset + 11] != b'SignerVer03':
        if len(records) >= 32 or offset + LDFW_HEADER > len(data):
            raise ValueError('missing LDFW header/trailer or too many records')
        raw = struct.unpack_from('<12I', data, offset)
        if raw[0] != LDFW_MAGIC:
            raise ValueError(f'invalid LDFW magic at {offset:#x}')
        size = raw[1]
        if size < LDFW_ALIGNMENT or size % LDFW_ALIGNMENT:
            raise ValueError('invalid LDFW record size/alignment')
        end = offset + size
        if end > len(data):
            raise ValueError('LDFW record exceeds input')
        name_bytes = data[offset + 0x30:offset + 0x40].split(b'\0', 1)[0]
        if not name_bytes or any(not 32 <= value < 127 for value in name_bytes):
            raise ValueError('invalid LDFW name')
        name = name_bytes.decode('ascii')
        if name in names or (records and records[-1]['name'] == 'tail_fw'):
            raise ValueError('duplicate name or record after tail_fw')
        names.add(name)
        flag = raw[10]
        if flag not in (0, 1):
            raise ValueError('unsupported encryption flag in related format')
        region = None
        if flag:
            start, finish = struct.unpack_from('<II', data, offset + 0x44)
            if not LDFW_HEADER <= start < finish <= size or (start | finish) & 15:
                raise ValueError('invalid encrypted interval in related format')
            region = dict(start_relative=hex(start), end_exclusive_relative=hex(finish),
                          start_file=hex(offset + start), end_exclusive_file=hex(offset + finish),
                          size=finish - start,
                          sha256=hashlib.sha256(data[offset + start:offset + finish]).hexdigest())
        records.append(dict(
            name=name, file_offset=hex(offset), end_exclusive=hex(end), size=size,
            sha256=hashlib.sha256(data[offset:end]).hexdigest(),
            header={field: hex(value) for field, value in zip(fields, raw)},
            reserved_words_le=[hex(value) for value in raw[9:12]],
            encryption_flag_raw=flag, encrypted_interval_by_related_format=region,
            plaintext_validated=False, runtime_mapping_verified=False))
        offset = end
    if not records or records[-1]['name'] != 'tail_fw':
        raise ValueError('expected tail_fw before SignerVer03')
    if offset + 0xa4 > len(data):
        raise ValueError('truncated SignerVer03 metadata')
    return dict(records=records, record_span_bytes=offset, signer_info_offset=hex(offset),
                signer_tag='SignerVer03', signature_verified=False)


def ldfw_evidence(data, sboot):
    container = parse_ldfw_records(data)
    # A64 MOV W0,#0; RET leaves in the clear tail, not SEC_PGTBL handlers.
    tail = int(container['records'][-1]['file_offset'], 0)
    leaves = []
    for relative in (0xb8, 0xc0, 0xc8, 0xd0, 0xd8):
        off = tail + relative
        if struct.unpack_from('<II', data, off) != (0x52800000, 0xd65f03c0):
            raise ValueError('unexpected HZC2 tail leaf instructions')
        leaves.append(dict(file_offset=hex(off), x0='0x0',
                           scope='local_leaf_only', sec_pgtbl_reachability_verified=False))
    container.update(
        common_header_source=HEADER_SOURCE, encryption_metadata_source=CRYPTO_SOURCE,
        related_crypto_source_soc='Exynos9830; not an Exynos2100 key validation',
        hzc2_decryption_validated=False, runtime_load_base_verified=False,
        candidate_drm=dict(name='drm_fw', file_offset='0x228000',
                           start_smc_id='0x82002000', queried_service='0x82002060',
                           service_offset='0x60',
                           relationship='identifier proximity, not a recovered dispatcher'),
        tail_aarch64_zero_leaves=leaves,
        loader=dict(
            function_file_offset='0xf65f8', normal_world_buffer='0xfa000000',
            record_size_field=4, version_field='0x1c', name_field='0x30',
            load_smc_signed=-0x500, wrapper_file_offset='0xf60e8', smc_file_offset='0xf60fc',
            calls=calls(sboot, (0xf667c, 0xf66b0)),
            instruction_words=words(sboot, (
                0xf6630, 0xf6634, 0xf6638, 0xf663c, 0xf6640,
                0xf6658, 0xf6668, 0xf6680, 0xf6684, 0xf6688,
                0xf668c, 0xf6690, 0xf6694, 0xf66a8, 0xf66ac,
                0xf60e8, 0xf60ec, 0xf60f0, 0xf60f4, 0xf60f8, 0xf60fc, 0xf6100)),
            execution_observed=False),
        header_fields_corroborated_by_hzc2_loader=['magic', 'size', 'version', 'fw_name'],
        header_field_semantics_verified=False,
        header_interpretation='common layout corroborated; encryption metadata from related format',
        sec_pgtbl_handler_recovered=False, provider_dispatch_verified=False)
    return container


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
        ldfw_container=ldfw_evidence(ldfw, sboot),
        runtime_observed=False, memory_map_verified=False,
        limits=['LDFW header metadata does not validate an Exynos2100 key, decryption or load address',
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
