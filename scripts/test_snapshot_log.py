#!/usr/bin/env python3
"""Synthetic ring captures, including incomplete/corrupt metadata. No hardware."""
import struct
from inspect_snapshot_log import decode, HEADER_SIZE, LOG_BASE, LOG_SIZE, DUMP_SIZE


def fixture(offset, wrapped):
    b = bytearray(DUMP_SIZE)
    struct.pack_into('<I', b, 0x200, LOG_BASE+offset)
    struct.pack_into('<I', b, 0x208, wrapped)
    return b


def main():
    b = fixture(5, 0)
    b[HEADER_SIZE:HEADER_SIZE+10] = b'boot\nstale'
    report, log = decode(b)
    assert log == b'boot\n' and report['decoded_size'] == 5
    # Full ring: oldest data after the cursor, newest data before it.
    b = fixture(3, 1)
    b[HEADER_SIZE:] = b'NEW' + b'.'*(LOG_SIZE-6) + b'OLD'
    _, log = decode(b)
    assert log == b'.'*(LOG_SIZE-6) + b'OLDNEW'
    for offset, flag, size in [(0,0,0),(LOG_SIZE,0,LOG_SIZE),
                               (0,1,LOG_SIZE),(LOG_SIZE,1,LOG_SIZE)]:
        report, log = decode(fixture(offset,flag))
        assert len(log) == size
    for bad in (b'', b'bad', bytes(DUMP_SIZE-1), bytes(DUMP_SIZE+1),
                fixture(-1,0), fixture(LOG_SIZE+1,0), fixture(0,2)):
        try: decode(bad)
        except ValueError: pass
        else: raise AssertionError('accepted incomplete or corrupt input')
    print('SNAPSHOT LOG: 6 reconstruction/boundary cases + 7 refusals PASS (synthetic only)')


if __name__ == '__main__': main()
