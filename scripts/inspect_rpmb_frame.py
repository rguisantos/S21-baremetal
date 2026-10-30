#!/usr/bin/env python3
"""Decode one offline RPMB frame; do not authenticate it or access a device."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct


FRAME_BYTES = 512
# Fixed-width local layout cross-checked against the pinned Flop C declaration.
LOCAL_FIELDS = (
    ('request', 0, 2), ('result', 2, 2), ('count', 4, 2),
    ('address', 6, 2), ('write_counter', 8, 4), ('nonce', 12, 16),
    ('data', 28, 256), ('Key_MAC', 284, 32), ('stuff', 316, 196),
)


def wire_interval(offset, size):
    """Translate a nonempty local field through whole-frame byte reversal."""
    if (type(offset) is not int or type(size) is not int
            or offset < 0 or size < 1 or offset > FRAME_BYTES-size):
        raise ValueError('field outside RPMB frame')
    return FRAME_BYTES-offset-size, size


def decode_frame(frame, *, input_order='wire'):
    if not isinstance(frame, bytes) or len(frame) != FRAME_BYTES:
        raise ValueError('exactly 512 frame bytes required')
    if input_order not in ('wire', 'local-materialized'):
        raise ValueError('unknown RPMB input order')
    # The local form is only meaningful after payload materialization, not while
    # pointer/count placeholders still occupy frontend fields +28/+32.
    wire = frame if input_order == 'wire' else frame[::-1]
    local = wire[::-1]
    scalars = dict(zip(('request', 'result', 'count', 'address', 'write_counter'),
                       struct.unpack_from('<HHHHI', local)))
    arrays = {}
    for name, offset, size in LOCAL_FIELDS[5:]:
        start, _ = wire_interval(offset, size)
        arrays[name] = dict(wire_offset=start, bytes=size,
            wire_sha256=hashlib.sha256(wire[start:start+size]).hexdigest())
    return dict(mode='offline_single_rpmb_frame', input_order=input_order,
        input_sha256=hashlib.sha256(frame).hexdigest(),
        wire_sha256=hashlib.sha256(wire).hexdigest(),
        scalars=scalars, arrays=arrays,
        authenticated_region=dict(wire_offset=228, bytes=284,
            sha256=hashlib.sha256(wire[228:]).hexdigest()),
        authentication_verified=False, capture_provenance_verified=False,
        device_io_established=False, counter_persistence_established=False,
        limits=[
            'scalar values are decoded bytes, not authenticated device state',
            'wire array hashes preserve transmitted byte order; local arrays reverse that order',
            'local-materialized input is a caller assertion; frontend pointer/count placeholders cannot be distinguished by these bytes alone',
            'no HMAC key, verification, transport, multi-frame aggregation or freshness proof is provided'])


def inspect_file(path, *, input_order='wire'):
    # Bound the read, including the extra byte needed to refuse trailing data.
    path = Path(path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('offline input must be a regular file')
    with path.open('rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError('offline input must be a regular file')
        data = source.read(FRAME_BYTES+1)
    return decode_frame(data, input_order=input_order)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frame', type=Path)
    parser.add_argument('--input-order', choices=('wire', 'local-materialized'), default='wire')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_file(args.frame, input_order=args.input_order), indent=2))
    except (OSError, ValueError, struct.error) as error:
        parser.exit(2, f'inspect_rpmb_frame: {error}\n')


if __name__ == '__main__':
    main()
