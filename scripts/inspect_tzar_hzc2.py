#!/usr/bin/env python3
"""Read-only HZC2 TZAR inventory and selected crypto-library boundaries.

Accepts only the received decompressed tzar.img. Decompresses its first
legacy LZ4 block in memory, never extracts archive paths or executes firmware.
ELF addresses below are link-time virtual addresses, not physical mappings.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import PurePosixPath
import struct

from inspect_el2_hzc2 import read_exact
from inspect_lk_final_edges import flow

SIZE = 7340816
SHA256 = '791c8818555e64d0e060c406e68748e869c7d53fbc9c9bbc893a1dd4f65a2077'
INNER_SHA256 = '5b98e0ad1d493cf5e9d792ca607e8c05a0f4dbc019b9263806fe68541edbd97d'
LIMIT = 8 * 1024 * 1024


def span(data, offset, size):
    if type(offset) is not int or type(size) is not int or offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError('range outside file')
    return data[offset:offset + size]


def inner_archive(data):
    """One observed size-prefixed legacy block; preserve, do not parse, tail."""
    expected, magic, compressed = struct.unpack('<III', span(data, 0, 12))
    if magic != 0x184c2102 or not 16 <= expected <= LIMIT or not 1 <= compressed <= LIMIT:
        raise ValueError('unsupported legacy LZ4 envelope')
    source = span(data, 12, compressed)
    library = ctypes.CDLL(ctypes.util.find_library('lz4') or 'liblz4.so.1')
    library.LZ4_decompress_safe.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    library.LZ4_decompress_safe.restype = ctypes.c_int
    encoded, decoded = ctypes.create_string_buffer(source), ctypes.create_string_buffer(expected)
    actual = library.LZ4_decompress_safe(encoded, decoded, compressed, expected)
    if actual != expected:
        raise ValueError('LZ4 block failed or decoded size differs')
    return decoded.raw, 12 + compressed


def archive_entries(data):
    """Observed TZAR dialect: 16-byte header, count name/size/data records."""
    if len(data) > LIMIT or span(data, 0, 8) != b'\x7f\xa5TA\0\0\0\1':
        raise ValueError('unsupported TZAR header')
    size, count = struct.unpack('<II', span(data, 8, 8))
    if size != len(data) or not 1 <= count <= 128:
        raise ValueError('invalid TZAR size/count')
    cursor, entries = 16, {}
    for _ in range(count):
        record = cursor
        name_size, file_size = struct.unpack('<II', span(data, cursor, 8))
        cursor += 8
        if not 2 <= name_size <= 256:
            raise ValueError('invalid TZAR name size')
        raw = span(data, cursor, name_size)
        cursor += name_size
        if raw[-1:] != b'\0' or any(byte < 32 or byte > 126 for byte in raw[:-1]):
            raise ValueError('invalid TZAR name encoding')
        name = raw[:-1].decode('ascii')
        path = PurePosixPath(name)
        if not name.startswith('/') or name.startswith('//') or '..' in path.parts or str(path) != name or name == '/' or name in entries:
            raise ValueError('noncanonical/duplicate TZAR name')
        content = span(data, cursor, file_size)
        entries[name] = dict(record_offset=record, data_offset=cursor, data=content)
        cursor += file_size
    if cursor != len(data):
        raise ValueError('unconsumed TZAR bytes')
    return entries


def elf64(data):
    """Restricted ELF64 LE AArch64 ET_DYN headers and dynamic symbol table."""
    header = span(data, 0, 64)
    if header[:7] != b'\x7fELF\2\1\1':
        raise ValueError('expected ELF64 little-endian version 1')
    kind, machine, version, entry, ph, sh, _, ehsize, phsize, phnum, shsize, shnum, _ = struct.unpack_from('<HHIQQQIHHHHHH', header, 16)
    if (kind, machine, version, ehsize, phsize, shsize) != (3, 183, 1, 64, 56, 64) or not 1 <= phnum <= 128 or not 1 <= shnum <= 4096:
        raise ValueError('unsupported ELF header/tables')
    span(data, ph, phsize * phnum)
    span(data, sh, shsize * shnum)
    loads = []
    for i in range(phnum):
        typ, flags, offset, address, _, filesz, memsz, align = struct.unpack('<IIQQQQQQ', span(data, ph + i * phsize, phsize))
        if typ == 1:
            span(data, offset, filesz)
            if filesz > memsz or address + memsz > 1 << 64:
                raise ValueError('invalid ELF load extent')
            loads.append(dict(offset=offset, address=address, size=filesz, flags=flags))
    if not loads:
        raise ValueError('ELF has no file-backed load segments')
    sections = [struct.unpack('<IIQQQQIIQQ', span(data, sh + i * shsize, shsize)) for i in range(shnum)]
    symbols = {}
    tables = [(i, s) for i, s in enumerate(sections) if s[1] == 11]
    if len(tables) != 1:
        raise ValueError('expected one dynamic symbol table')
    dynsym_index, s = tables[0]
    if s[9] != 24 or s[5] % 24 or s[5] // 24 > 65536 or not 0 <= s[6] < shnum:
        raise ValueError('invalid dynamic symbol table')
    strings_section = sections[s[6]]
    if strings_section[1] != 3:
        raise ValueError('dynamic symbols do not link a string table')
    strings = span(data, strings_section[4], strings_section[5])
    table = span(data, s[4], s[5])
    for at in range(0, len(table), 24):
        name, info, _, index, address, size = struct.unpack_from('<IBBHQQ', table, at)
        if name >= len(strings):
            raise ValueError('ELF symbol name outside string table')
        end = strings.find(b'\0', name, min(len(strings), name + 1024))
        if end < 0:
            raise ValueError('unterminated/oversized ELF symbol name')
        text = strings[name:end].decode('ascii')
        if text:
            if text in symbols:
                raise ValueError('ambiguous dynamic symbol name')
            symbols[text] = dict(address=address, size=size, section=index, type=info & 15, index=at // 24)
    return dict(entry=entry, loads=loads, symbols=symbols, data=data, sections=sections,
                dynsym_section_index=dynsym_index, dynsym_count=s[5] // 24)


def at_address(elf, address, size, *, executable=False):
    if type(address) is not int or type(size) is not int or address < 0 or size <= 0 or address + size > 1 << 64:
        raise ValueError('invalid ELF address/size')
    candidates = [p for p in elf['loads'] if p['address'] <= address and address + size <= p['address'] + p['size']]
    if len(candidates) != 1 or (executable and not candidates[0]['flags'] & 1):
        raise ValueError('ambiguous/non-file-backed ELF address')
    p = candidates[0]
    offset = p['offset'] + address - p['address']
    return offset, span(elf['data'], offset, size)


def witnesses(elf, ranges):
    rows = []
    for start, end in ranges:
        if start % 4 or end % 4 or start >= end:
            raise ValueError('invalid instruction witness range')
        offset, raw = at_address(elf, start, end - start, executable=True)
        for i in range(0, len(raw), 4):
            word = struct.unpack_from('<I', raw, i)[0]
            kind, target = flow(word, start + i)
            rows.append(dict(elf_address=hex(start + i), file_offset=hex(offset + i), word=f'{word:08x}',
                             relative_target=hex(target) if kind in ('b', 'bl', 'conditional') else None))
    return rows


def evidence(path):
    data = read_exact(path, SIZE, SHA256)
    archive, end = inner_archive(data)
    if hashlib.sha256(archive).hexdigest() != INNER_SHA256:
        raise ValueError('unexpected decoded TZAR identity')
    entries = archive_entries(archive)
    if len(entries) != 44:
        raise ValueError('unexpected HZC2 entry count')
    inventory = [dict(path=name, record_offset=hex(item['record_offset']), data_offset=hex(item['data_offset']),
        size=len(item['data']), sha256=hashlib.sha256(item['data']).hexdigest(),
        ELF_class=item['data'][4] if item['data'].startswith(b'\x7fELF') else None)
        for name, item in entries.items()]
    scrypto = elf64(entries['/lib64/libscrypto.so']['data'])
    teesl = elf64(entries['/lib64/libteesl.so']['data'])
    selected = {}
    for name, elf, symbols in (
        ('scrypto64', scrypto, ('SHA384_Init', 'SHA384_Update', 'SHA384_Final', 'SHA512_Update', 'SHA512_Final', 'HMAC', 'ioctl')),
        ('teesl64', teesl, ('TEE_AllocateOperation', 'TEE_DigestUpdate', 'TEE_DigestDoFinal', 'TEE_MACInit', 'TEE_MACUpdate', 'TEE_MACComputeFinal', 'ioctl', 'EVP_DigestUpdate'))):
        selected[name] = {}
        for symbol in symbols:
            item = elf['symbols'][symbol]
            if item['section']:
                at_address(elf, item['address'], item['size'], executable=True)
            selected[name][symbol] = dict(address=hex(item['address']), size=item['size'], defined=bool(item['section']))
    # Bind the named functions to the two branches, independently annotated by
    # GNU objdump/readelf in the accompanying evidence. No call is executed.
    for address, target, kind in ((0xa7a9c, scrypto['symbols']['SHA512_Update']['address'], 'bl'),
                                  (0xa7aac, scrypto['symbols']['SHA512_Final']['address'], 'b')):
        _, raw = at_address(scrypto, address, 4, executable=True)
        if flow(struct.unpack('<I', raw)[0], address) != (kind, target):
            raise ValueError('SHA384 delegation edge changed')
    _, crypto_path = at_address(teesl, 0x43670, 12)
    if crypto_path != b'/dev/crypto\0':
        raise ValueError('crypto device string changed')
    return dict(mode='static_read_only_TZAR_inventory', input=dict(size=SIZE, sha256=SHA256),
        envelope=dict(declared_decoded_size=len(archive), compressed_block_offset='0xc',
            compressed_block_size=end - 12, compressed_end=hex(end), inner_sha256=INNER_SHA256,
            tail_offset=hex(end), tail_size=len(data) - end, tail_sha256=hashlib.sha256(data[end:]).hexdigest(),
            tail_interpreted=False),
        archive=dict(entry_count=len(entries), all_bytes_consumed=True, entries=inventory),
        selected_dynamic_symbols=selected,
        scrypto_SHA384_delegation=witnesses(scrypto, ((0xa7a94, 0xa7ab0),)),
        teesl_crypto_boundary=witnesses(teesl, ((0x281f8, 0x282e4), (0x2a7fc, 0x2a818), (0x2a850, 0x2a89c),
            (0x2c7cc, 0x2c7f4), (0x2c81c, 0x2c868), (0x2c89c, 0x2c8b4))),
        interpretation=dict(crypto_device='/dev/crypto', allocation_ioctl_request=7,
            update_ioctl_request=1, device_digest_selectors=['0x500000d2', '0x500000d4', '0x500000d6'],
            static_helper_translation={'0x500000d2': '0x02010000', '0x500000d4': '0x02030000',
                '0x500000d6': '0x02040000'},
            helper_low_bit='OR 1 exactly when its W1 argument equals 1; actual argument not observed',
            separate_EVP_digest_selectors=['0x50000001..0x50000006'],
            device_driver_implementation_resolved=False, EPBL_mode_0x19_identified=False,
            EPBL_DMA_input_identified=False,
            limit='Library API selectors and ioctl requests are not EPBL MMIO selector values'),
        archive_paths_extracted=False, firmware_executed=False, physical_device_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tzar', help='exact decompressed HZC2 tzar.img')
    args = parser.parse_args()
    try:
        print(json.dumps(evidence(args.tzar), indent=2))
    except (ValueError, OSError, KeyError, UnicodeError, struct.error) as error:
        parser.exit(2, f'{error}\n')
