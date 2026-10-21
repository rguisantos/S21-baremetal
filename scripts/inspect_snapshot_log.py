#!/usr/bin/env python3
"""Inspect an offline Samsung snapshot header+kernel-log dump.
Input must cover [0xf0000000, 0xf0210000), with no prefix or sparse holes.
This does not acquire memory, authenticate a dump, or access a device.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

HEADER_SIZE = 0x10000
LOG_BASE = 0xf0010000
LOG_SIZE = 0x200000
DUMP_SIZE = HEADER_SIZE + LOG_SIZE


def decode(data):
    if len(data) != DUMP_SIZE:
        raise ValueError(f'expected exactly {DUMP_SIZE} contiguous bytes')
    cursor = struct.unpack_from('<I', data, 0x200)[0]
    wrapped = struct.unpack_from('<I', data, 0x208)[0]
    if not LOG_BASE <= cursor <= LOG_BASE + LOG_SIZE:
        raise ValueError('cursor outside the source-defined log region')
    if wrapped not in (0, 1):
        raise ValueError('unsupported wrap flag (requires 0 or 1)')
    offset = cursor - LOG_BASE
    log = data[HEADER_SIZE:]
    result = log[offset:] + log[:offset] if wrapped else log[:offset]
    report = dict(format='Samsung source reference snapshot log',
                  physical_start=hex(0xf0000000), cursor=hex(cursor),
                  cursor_offset=offset, wrapped=bool(wrapped),
                  decoded_size=len(result), dump_sha256=hashlib.sha256(data).hexdigest(),
                  log_sha256=hashlib.sha256(result).hexdigest(),
                  limits=['No authentication or physical acquisition',
                          'Requires the same layout as the received Samsung source',
                          'May contain LK and kernel data; not a payload boot proof'])
    return report, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dump', type=Path)
    parser.add_argument('--output', type=Path, help='new output file for chronological bytes')
    args = parser.parse_args()
    try:
        with args.dump.open('rb') as source:
            report, log = decode(source.read(DUMP_SIZE+1))
        if args.output:
            with args.output.open('xb') as dest:
                dest.write(log)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'inspect_snapshot_log: {exc}\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
