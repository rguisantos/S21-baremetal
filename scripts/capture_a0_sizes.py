#!/usr/bin/env python3
"""Bounded Image mapping and streamed newc/gzip sizing, not boot validation."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct

from capture_a0_formats import MAX_IMAGE, align, digest, require
from capture_a0_module_policy import Elf, MAX_MODULE, module
from capture_a0_modules import cpio, cstring
from capture_a0_inputs import HashingWriter, read_checked, read_sealed

MAX_CPIO = 512*1024*1024  # Explicit measurement path; existing readers stay unchanged.
REMOVED_IMAGE_SECTIONS = {'.note', '.note.gnu.build-id', '.comment'}


def comparison(stock, candidate):
    require(type(stock) is int and type(candidate) is int and stock > 0 and candidate > 0, 'size values')
    return dict(stock_bytes=stock, candidate_bytes=candidate, delta_bytes=candidate-stock,
        not_larger_than_stock=candidate <= stock, exact_size_match=candidate == stock,
        current_fixed_size_packer_accepts=candidate == stock)


def arm64_header(image):
    require(len(image) >= 64 and image[56:60] == b'ARM\x64', 'ARM64 Image header missing')
    offset, size, flags = struct.unpack_from('<3Q', image, 8)
    require(len(image) <= size <= MAX_IMAGE, 'Image file exceeds declared runtime extent/bound')
    return dict(file_bytes=len(image), text_offset=offset, runtime_image_size=size, flags=flags)


def flat_image(data):
    """Independently reproduce objcopy's file-backed allocated-section mapping."""
    require(64 <= len(data) <= 512*1024*1024 and data[:7] == b'\x7fELF\x02\x01\x01', 'vmlinux ELF64 LE size/type')
    require(struct.unpack_from('<HHI', data, 16) in ((2, 183, 1), (3, 183, 1)), 'vmlinux kind/machine')
    phoff, shoff = struct.unpack_from('<QQ', data, 32)
    eh, phsize, phnum, shsize, count, names = struct.unpack_from('<6H', data, 52)
    require(eh == 64 and phsize == 56 and 0 < phnum <= 128 and phoff >= 64
        and phoff+phnum*phsize <= len(data) and shsize == 64 and 0 < names < count <= 16384
        and shoff >= 64 and shoff+count*shsize <= len(data), 'vmlinux table bounds')
    loads = []
    for i in range(phnum):
        kind, flags, off, va, pa, files, memory, alignment = struct.unpack_from('<II6Q', data, phoff+i*56)
        if kind != 1: continue
        require(files <= memory and off+files <= len(data), 'load segment extent')
        loads.append((off, va, pa, files))
    rows = [struct.unpack_from('<IIQQQQIIQQ', data, shoff+i*64) for i in range(count)]
    names_row = rows[names]
    require(names_row[1] == 3 and names_row[4]+names_row[5] <= len(data), 'section names extent')
    strings = data[names_row[4]:names_row[4]+names_row[5]]; sections = []; seen = set()
    for row in rows[1:]:
        name = cstring(strings, row[0]); require(name and name not in seen, 'empty/duplicate section name'); seen.add(name)
        kind, flags, va, off, size = row[1:6]
        if kind == 8 or not flags & 2 or not size or name in REMOVED_IMAGE_SECTIONS: continue
        require(not flags & 0x800 and off+size <= len(data), 'allocated section extent/compression')
        addresses = {pa+va-base for po, base, pa, files in loads
            if base <= va and va+size <= base+files and off-po == va-base}
        require(len(addresses) == 1, 'allocated section lacks an unambiguous file-backed LMA')
        sections.append((addresses.pop(), name, off, size))
    require(sections, 'no Image sections'); sections.sort()
    base = sections[0][0]; end = max(address+size for address, _, _, size in sections)
    require(0 < end-base <= MAX_IMAGE, 'flat Image size bound')
    out = bytearray(end-base); previous = base
    for address, name, off, size in sections:
        require(previous <= address, 'overlapping Image sections')
        out[address-base:address-base+size] = data[off:off+size]; previous = address+size
    image = bytes(out)
    return image, dict(base_lma=hex(base), file_backed_sections=len(sections),
        sections=[dict(name=n, offset=a-base, bytes=s) for a,n,o,s in sections], header=arm64_header(image))


def strip_equivalence(before, after):
    """Check necessary module metadata and allocated bytes across --strip-debug."""
    def measured(data):
        meta = module(data); meta = {k:v for k,v in meta.items() if k not in ('sha256','bytes')}
        elf = Elf(data); allocated = {}
        for name, index in elf.sections.items():
            row = elf.rows[index]
            if row[2] & 2:
                allocated[name] = dict(type=row[1], flags=row[2], bytes=row[5], alignment=row[8],
                    sha256=None if row[1] == 8 else digest(data[row[4]:row[4]+row[5]]))
        return meta, allocated
    old, old_alloc = measured(before); new, new_alloc = measured(after)
    require(old == new and old_alloc == new_alloc, 'strip changed module metadata or allocated section bytes')
    encoded = lambda x: digest(json.dumps(x, sort_keys=True, separators=(',',':')).encode())
    return dict(metadata_preserved=True, allocated_section_bytes_preserved=True,
        metadata_sha256=encoded(old), allocated_sections_sha256=encoded(old_alloc))


def records(raw):
    """Retain original newc headers, order and permissions; never extract paths."""
    entries = cpio(raw); rows = []; pos = 0
    while True:
        start = pos; fields = [int(raw[pos+6+i*8:pos+14+i*8], 16) for i in range(13)]
        ns = fields[11]; name = raw[pos+110:pos+110+ns-1].decode()
        body = align(pos+110+ns, 4); end = align(body+fields[6], 4)
        row = dict(name=name, fields=fields, prefix=raw[start:body], data=raw[body:body+fields[6]],
            padding=raw[body+fields[6]:end])
        rows.append(row); pos = end
        if name == 'TRAILER!!!': break
    return rows, entries


def ramdisk(raw, replacements, target):
    """Stream a measured newc512/gzip-9 profile, then verify every member again.

    replacements maps canonical original names to {path, bytes, sha256}.
    Input reader bounds remain 128 MiB; only the output measurement stream
    may reach 512 MiB. No path inside either archive is extracted.
    """
    rows, entries = records(raw)
    require(set(replacements) <= entries.keys(), 'replacement name absent from original cpio')
    expected = {}
    for row in rows:
        name = row['name']
        if name == 'TRAILER!!!': continue
        replacement = replacements.get(name)
        if replacement is not None:
            info = os.fstat(replacement['fd']) if 'fd' in replacement else Path(replacement['path']).lstat()
            require(stat.S_ISREG(info.st_mode) and stat.S_IFMT(row['fields'][1]) == stat.S_IFREG
                and 0 <= info.st_size == replacement['bytes'] <= MAX_MODULE, 'replacement type/size')
        expected[name] = dict(fields=list(row['fields']), sha256=replacement['sha256'] if replacement else digest(row['data']))
        if replacement: expected[name]['fields'][6] = replacement['bytes']
    written = 0; cpio_hash = hashlib.sha256()
    with target.open('xb') as file:
        encoded = HashingWriter(file)
        with gzip.GzipFile(filename='', fileobj=encoded, mode='wb', compresslevel=9, mtime=0) as zipped:
            def emit(data):
                nonlocal written
                written += len(data); require(written <= MAX_CPIO, 'measurement cpio exceeds explicit bound')
                cpio_hash.update(data); zipped.write(data)
            if not replacements:
                emit(raw)
            else:
                for row in rows:
                    replacement = replacements.get(row['name'])
                    if replacement is None:
                        emit(row['prefix']); emit(row['data']); emit(row['padding']); continue
                    prefix = bytearray(row['prefix']); prefix[54:62] = f"{replacement['bytes']:08x}".encode()
                    data = read_sealed(replacement['fd'],replacement) if 'fd' in replacement else read_checked(Path(replacement['path']),replacement)
                    emit(prefix); emit(data); emit(bytes((-len(data)) % 4))
                emit(bytes((-written) % 512))
    compressed = read_checked(target,encoded.pin())
    # Stream decoded cpio from the very compressed buffer verified against
    # the writer, without constructing a 400+ MiB decoded byte string.
    checked = 0; read = 0; seen = set(); verified_hash = hashlib.sha256()
    with gzip.GzipFile(fileobj=io.BytesIO(compressed),mode='rb') as stream:
        def take(size):
            nonlocal read
            require(0 <= size <= 1024*1024 and read+size <= MAX_CPIO, 'streamed cpio bound')
            data = stream.read(size); require(len(data) == size, 'truncated output cpio')
            read += size; verified_hash.update(data); return data
        for row in rows:
            header = take(110); require(header[:6] == b'070701', 'output cpio magic')
            fields = [int(header[6+i*8:14+i*8], 16) for i in range(13)]
            require(1 < fields[11] <= 4096, 'output name bound')
            name_bytes = take(fields[11]); require(name_bytes[-1:] == b'\0', 'output name termination')
            name = name_bytes[:-1].decode(); require(name == row['name'] and name not in seen, 'output order/name duplicate')
            seen.add(name); take((-read) % 4)
            wanted = expected[name] if name != 'TRAILER!!!' else dict(fields=row['fields'], sha256=digest(b''))
            require(fields == wanted['fields'], 'output cpio metadata changed')
            hashed = hashlib.sha256(); remaining = fields[6]
            while remaining:
                chunk = take(min(remaining, 1024*1024)); hashed.update(chunk); remaining -= len(chunk)
            require(hashed.hexdigest() == wanted['sha256'], 'output member digest changed'); take((-read) % 4)
            checked += name != 'TRAILER!!!'
        while chunk := stream.read(1024*1024):
            require(not any(chunk) and read+len(chunk) <= MAX_CPIO, 'output trailing bytes/bound')
            read += len(chunk); verified_hash.update(chunk)
    require(read == written and verified_hash.digest() == cpio_hash.digest(), 'stream replay differs')
    return dict(cpio_bytes=written, cpio_sha256=cpio_hash.hexdigest(), gzip_bytes=len(compressed),
        gzip_sha256=digest(compressed), entries_verified=checked, modules_replaced=len(replacements),
        original_order_and_headers_preserved_except_file_size=True,
        untouched_entry_data_preserved=True, stream_replay_verified=True,
        compression='Python gzip.GzipFile, level 9, mtime 0, empty filename',
        newc_padding='original for no replacements; zero padding to 512 for replacements')
