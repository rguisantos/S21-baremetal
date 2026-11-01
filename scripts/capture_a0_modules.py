#!/usr/bin/env python3
"""Bounded newc/ELF64 readers for offline stock module requirements.

Never extracts filesystem entries, loads modules, or verifies signatures.
Only the observed little-endian AArch64, 64-byte __versions ABI is supported.
"""
from pathlib import PurePosixPath
import re
import stat
import struct
import zlib

from capture_a0_formats import align, digest, require

MAX_RAMDISK = 128*1024*1024
SYMBOL = re.compile(r'[A-Za-z_][A-Za-z0-9_.$]*')


def gunzip(data):
    require(len(data) <= MAX_RAMDISK, 'compressed ramdisk exceeds bound')
    dec = zlib.decompressobj(31)
    raw = dec.decompress(data, MAX_RAMDISK+1)
    require(len(raw) <= MAX_RAMDISK and dec.eof and not dec.unused_data
            and not dec.unconsumed_tail, 'gzip incomplete, concatenated or oversized')
    return raw


def cpio(data):
    """One newc archive, canonical relative names, no link following."""
    require(len(data) <= MAX_RAMDISK, 'cpio size exceeds bound')
    pos = 0; entries = {}
    for _ in range(10000):
        require(pos+110 <= len(data) and data[pos:pos+6] == b'070701', 'newc header missing')
        header = data[pos+6:pos+110]
        require(re.fullmatch(rb'[0-9a-fA-F]{104}', header), 'invalid newc hex')
        fields = [int(header[i:i+8], 16) for i in range(0, 104, 8)]
        mode, links, size, ns, check = fields[1], fields[4], fields[6], fields[11], fields[12]
        require(1 < ns <= 4096 and pos+110+ns <= len(data) and check == 0, 'newc name/check bounds')
        encoded = data[pos+110:pos+110+ns]
        require(encoded[-1:] == b'\0' and b'\0' not in encoded[:-1], 'newc name termination')
        name = encoded[:-1].decode('utf-8')
        start = align(pos+110+ns, 4); end = start+size; pos = align(end, 4)
        require(pos <= len(data), 'truncated newc content/padding')
        if name == 'TRAILER!!!':
            require(size == 0 and not any(data[pos:]), 'trailing archive/data unsupported')
            return entries
        path = PurePosixPath(name)
        require(path.parts and not path.is_absolute() and '..' not in path.parts
                and str(path) == name and name not in entries, 'unsafe/duplicate newc path')
        kind = stat.S_IFMT(mode)
        require(kind in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK), 'unsupported newc kind')
        require(kind != stat.S_IFREG or links == 1, 'regular hardlinks unsupported')
        entries[name] = dict(kind=kind, data=data[start:end])
    raise ValueError('newc entry budget exceeded')


def cstring(data, offset):
    require(0 <= offset < len(data), 'string offset outside table')
    end = data.find(b'\0', offset)
    require(end >= 0, 'unterminated ELF string')
    return data[offset:end].decode('utf-8')


def elf_sections(data):
    require(64 <= len(data) <= 32*1024*1024, 'ELF size outside bound')
    require(data[:7] == b'\x7fELF\x02\x01\x01', 'requires ELF64 little endian')
    kind, machine, version = struct.unpack_from('<HHI', data, 16)
    require((kind, machine, version) == (1, 183, 1), 'requires AArch64 ET_REL')
    shoff = struct.unpack_from('<Q', data, 40)[0]
    ehsize, _, phnum, shsize, count, names_index = struct.unpack_from('<6H', data, 52)
    require(ehsize == 64 and phnum == 0 and shsize == 64 and 0 < names_index < count <= 4096
            and shoff >= 64 and shoff+64*count <= len(data), 'ELF section table bounds')
    rows = [struct.unpack_from('<IIQQQQIIQQ', data, shoff+64*i) for i in range(count)]
    for r in rows[1:]:
        require(not r[2] & 0x800, 'compressed ELF section unsupported')
        require(r[1] == 8 or r[4]+r[5] <= len(data), 'ELF section exceeds file')
    name_row = rows[names_index]
    require(name_row[1] == 3, 'section names must be STRTAB')
    names = data[name_row[4]:name_row[4]+name_row[5]]; result = {}
    for r in rows[1:]:
        name = cstring(names, r[0])
        require(name and name not in result, 'duplicate/empty section name')
        result[name] = dict(type=r[1], data=b'' if r[1] == 8 else data[r[4]:r[4]+r[5]])
    return result


def module(data):
    sections = elf_sections(data)
    require(all(n in sections and sections[n]['type'] == 1 for n in ('.modinfo', '__versions')),
            'module metadata/version section missing or wrong type')
    raw = sections['.modinfo']['data']
    require(raw.endswith(b'\0'), 'unterminated modinfo')
    info = {}
    for item in raw.split(b'\0'):
        if not item: continue
        key, sep, value = item.decode('utf-8').partition('=')
        require(sep and key, 'invalid modinfo entry')
        info.setdefault(key, []).append(value)
    require(all(len(info.get(k, [])) == 1 for k in ('name', 'vermagic', 'depends')),
            'missing/ambiguous module identity')
    versions = {}; raw = sections['__versions']['data']
    require(raw and len(raw) % 64 == 0, 'unsupported modversion record size')
    for pos in range(0, len(raw), 64):
        crc = struct.unpack_from('<Q', raw, pos)[0]; name = cstring(raw[pos+8:pos+64], 0)
        require(crc <= 0xffffffff and SYMBOL.fullmatch(name) and name not in versions,
                'invalid/duplicate version requirement')
        versions[name] = f'0x{crc:08x}'
    require('module_layout' in versions, 'module_layout version missing')
    return dict(bytes=len(data), sha256=digest(data), name=info['name'][0],
        vermagic=info['vermagic'][0], depends=info['depends'][0].split(',') if info['depends'][0] else [],
        version_count=len(versions), versions_sha256=digest(raw)), versions


def requirements(modules):
    """Keep conflicts explicit; never silently pick a CRC from one module."""
    union = {}
    for filename, versions in sorted(modules.items()):
        for name, crc in versions.items():
            union.setdefault(name, {}).setdefault(crc, []).append(filename)
    return {name: dict(crcs=sorted(values), consumers=sum(map(len, values.values())))
            for name, values in sorted(union.items())}


def compare_symvers(required, text):
    """Necessary CRC coverage only; not a module loader or ABI approval."""
    require(len(text) <= 16*1024*1024, 'symvers size exceeds bound')
    actual = {}
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) in (4, 5), 'unsupported Module.symvers row')
        crc, name, provider, export = fields[:4]
        require(re.fullmatch(r'0x[0-9a-fA-F]{8}', crc) and SYMBOL.fullmatch(name)
                and name not in actual and export in ('EXPORT_SYMBOL', 'EXPORT_SYMBOL_GPL',
                'EXPORT_SYMBOL_GPL_FUTURE', 'EXPORT_UNUSED_SYMBOL', 'EXPORT_UNUSED_SYMBOL_GPL'),
                'invalid/duplicate Module.symvers symbol')
        actual[name] = crc.lower()
    missing = []; mismatched = []; conflicts = []; matched = 0
    for name, row in required.items():
        if len(row['crcs']) != 1: conflicts.append(name)
        elif name not in actual: missing.append(name)
        elif actual[name] != row['crcs'][0]: mismatched.append(name)
        else: matched += 1
    return dict(supplied=True, sha256=digest(text.encode()), matched=matched,
        missing=missing, mismatched=mismatched, stock_crc_conflicts=conflicts,
        crc_coverage_passed=bool(required) and not (missing or mismatched or conflicts),
        module_abi_established=False)
