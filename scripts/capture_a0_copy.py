#!/usr/bin/env python3
"""Copy a pinned stream and verify the actual destination before publication.

Readback detects a damaged copy; it does not identify a historical mutator or
prevent later changes. Consumers must still check inputs immediately before use.
"""
import hashlib
import os
from pathlib import Path
import re
import stat

from capture_a0_formats import require

MAX_COPY = 512*1024*1024


def identity(info):
    return dict(device=info.st_dev,inode=info.st_ino,bytes=info.st_size,
        mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns)


def copy_checked(source, destination, pin):
    require(type(pin['bytes']) is int and 0 <= pin['bytes'] <= MAX_COPY
        and isinstance(pin['sha256'],str) and re.fullmatch('[0-9a-f]{64}',pin['sha256']), 'copy pin invalid')
    count = 0; h = hashlib.sha256()
    with Path(destination).open('xb') as output:
        while chunk := source.read(1024*1024):
            count += len(chunk); require(count <= pin['bytes'], 'copy source exceeds pin')
            h.update(chunk); require(output.write(chunk) == len(chunk), 'copy destination short write')
        require(count == pin['bytes'] and h.hexdigest() == pin['sha256'], 'copy source identity differs')
        output.flush(); os.fsync(output.fileno()); written = os.fstat(output.fileno())
        require(stat.S_ISREG(written.st_mode) and written.st_size == count, 'copy destination size/type differs after flush')
    readback = hashlib.sha256(); read_count = 0
    with Path(destination).open('rb') as file:
        before = os.fstat(file.fileno())
        require(identity(before) == identity(written), 'copy destination identity changed before readback')
        while chunk := file.read(1024*1024):
            read_count += len(chunk); require(read_count <= pin['bytes'], 'copy destination grew during readback')
            readback.update(chunk)
        after = os.fstat(file.fileno())
    require(identity(after) == identity(written) == identity(Path(destination).lstat()), 'copy destination changed during readback')
    require(read_count == count and readback.hexdigest() == pin['sha256'], 'copy destination SHA differs')
    return dict(bytes_written=count,source_sha256=h.hexdigest(),destination_sha256=readback.hexdigest(),
        destination_readback_verified=True,writer_pid=os.getpid(),destination=identity(after),
        volatile_identity_fields_are_not_reproduction_criteria=True)
