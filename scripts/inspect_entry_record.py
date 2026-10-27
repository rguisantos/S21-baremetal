#!/usr/bin/env python3
"""Validate an exact S21ENTRY v1 record offline against a supplied probe Image."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

RECORD_SIZE = 128
MAX_IMAGE_SIZE = 0x100000
LIMIT = 1 << 64


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect_record(record, image, load_address, snapshot=None):
    """Check the current probe layout; provenance and freshness remain external."""
    if len(record) != RECORD_SIZE:
        raise ValueError('record must contain exactly 128 bytes')
    if not 192 <= len(image) < MAX_IMAGE_SIZE:
        raise ValueError('invalid probe Image extent')
    if image[56:64] != b'ARM\x64\0\0\0\0' or any(image[32:56]):
        raise ValueError('not the raw ARM64 probe header (no EFI stub)')
    if struct.unpack_from('<3Q', image, 8) != (0x80000, len(image), 8):
        raise ValueError('probe header offset/size/flags mismatch')
    # start.S places diag_end immediately after the aligned v1 record.
    offset = len(image)-RECORD_SIZE
    if offset % 64 or image[offset:] != bytes(RECORD_SIZE):
        raise ValueError('reference Image must end with the aligned, zeroed v1 record')
    if not isinstance(load_address, int) or not 0 <= load_address <= LIMIT-len(image):
        raise ValueError('Image address interval overflows u64')
    if load_address % 64:
        raise ValueError('expected Image address must preserve 64-byte record alignment')
    if record[:8] != b'S21ENTRY':
        raise ValueError('record has no complete v1 commit marker; outcome is unknown')
    if struct.unpack_from('<2I', record, 8) != (1, RECORD_SIZE):
        raise ValueError('unsupported record version or size')
    values = struct.unpack_from('<14Q', record, 16)
    x0, x1, x2, x3, current_el, daif, sctlr, mpidr, spsel, sp, base, address, r0, r1 = values
    if current_el not in (4, 8):
        raise ValueError('recorded CurrentEL is incompatible with this probe')
    if daif & ~0x3c0 or spsel not in (0, 1):
        raise ValueError('invalid DAIF or SPSel encoding')
    if sctlr & 5:
        raise ValueError('committed record claims M/C enabled, inconsistent with the probe')
    if r0 or r1:
        raise ValueError('reserved record fields must be zero')
    if (base, address) != (load_address, load_address+offset):
        raise ValueError('recorded Image/record addresses differ from the supplied layout')
    if snapshot is not None:
        if len(snapshot) != len(image):
            raise ValueError('snapshot must contain the complete, exact Image extent')
        if snapshot[:offset] != image[:offset] or snapshot[offset:] != record:
            raise ValueError('snapshot code/header or record differs from the supplied bytes')
    return {
        'schema_version': 1, 'validation': 'consistent_with_supplied_probe_layout',
        'binding': 'full_image_bytes' if snapshot is not None else 'record_fields_only',
        'origin': 'not_verified', 'freshness': 'not_verified', 'authentication': 'not_verified',
        'x0_is_valid_fdt': 'not_established',
        'image_sha256': digest(image), 'record_sha256': digest(record),
        'snapshot_sha256': digest(snapshot) if snapshot is not None else None,
        'image_size': len(image), 'record_offset': offset,
        'image_address': f'0x{base:016x}', 'record_address': f'0x{address:016x}',
        'recorded_el': current_el >> 2, 'current_el_raw': current_el,
        'arguments': [f'0x{x:016x}' for x in (x0, x1, x2, x3)],
        'daif': f'0x{daif:016x}', 'sctlr': f'0x{sctlr:016x}',
        'mpidr': f'0x{mpidr:016x}', 'spsel': spsel, 'sp': f'0x{sp:016x}',
    }


def read_bounded(path, limit):
    with path.open('rb') as source:
        data = source.read(limit+1)
    if len(data) > limit:
        raise ValueError(f'{path.name} exceeds the input size limit')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path, help='exact 128-byte capture, without a dump prefix')
    parser.add_argument('--image', type=Path, required=True, help='unmodified reference entry_diag.Image')
    parser.add_argument('--load-address', type=lambda s: int(s, 0), required=True,
                        help='expected Image address from the capture context, not inferred RAM')
    parser.add_argument('--snapshot', type=Path, help='optional full Image capture for byte comparison')
    args = parser.parse_args()
    try:
        result = inspect_record(read_bounded(args.record, RECORD_SIZE),
                                read_bounded(args.image, MAX_IMAGE_SIZE), args.load_address,
                                read_bounded(args.snapshot, MAX_IMAGE_SIZE) if args.snapshot else None)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
