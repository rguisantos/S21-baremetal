#!/usr/bin/env python3
"""Build an inspectable S21R10 v1 container; this does not authorize chainload.
Only identity-linked AArch64 ET_EXEC ELF files are supported. No relocation,
RAM discovery, partition writes or legacy XNU boot_args are performed.
"""
import argparse
from pathlib import Path
import struct

MAGIC = b'S21R10  '
HEADER = struct.Struct('<8sII7Q608s')
SEGMENT = struct.Struct('<4Q')
MAX_SEGMENTS = 32
MAX_SIZE = 64 * 1024 * 1024
U64 = (1 << 64) - 1


def require(condition, message):
    if not condition:
        raise ValueError(message)


def span(start, size):
    return size > 0 and start <= U64 - size


def align(value, boundary=4096):
    return (value + boundary - 1) & -boundary


def overlap(a, n, b, m):
    return n and m and a < b + m and b < a + n


def validate_dtb(data):
    require(40 <= len(data) <= 2 * 1024 * 1024, 'DTB size outside bounds')
    magic, total, so, ss, ro, version, last, _, sn, stn = struct.unpack_from('>10I', data)
    require(magic == 0xd00dfeed and total == len(data), 'expected a raw, exact-length FDT')
    require(version >= 17 and last <= 17 and last <= version, 'unsupported FDT version')
    require(so >= 40 and not so % 4 and stn and not stn % 4 and so + stn <= total,
            'bad FDT structure bounds')
    require(ss >= 40 and ss + sn <= total and not overlap(so, stn, ss, sn), 'bad FDT strings bounds')
    require(ro >= 40 and not ro % 8 and ro + 16 <= total, 'bad FDT reservation bounds')
    pos = ro
    while True:
        require(pos + 16 <= total and not overlap(ro, pos + 16 - ro, so, stn)
                and not overlap(ro, pos + 16 - ro, ss, sn), 'unterminated/overlapping FDT reservations')
        addr, size = struct.unpack_from('>QQ', data, pos)
        pos += 16
        if not addr and not size:
            break
        require(span(addr, size), 'invalid FDT reservation')
    pos, end, depth, seen, closed = so, so + stn, 0, False, False
    children = []
    while pos < end:
        token, = struct.unpack_from('>I', data, pos)
        pos += 4
        if token == 1:
            require(not closed and depth < 32, 'bad FDT root/depth')
            stop = data.find(b'\0', pos, end)
            require(stop >= pos and b'/' not in data[pos:stop], 'bad FDT node name')
            require((depth > 0 and stop > pos) or (depth == 0 and stop == pos and not seen), 'bad FDT root/node')
            if depth:
                children[-1] = True
            seen = True
            depth += 1
            children.append(False)
            pos = align(stop + 1, 4)
        elif token == 2:
            require(depth > 0, 'unbalanced FDT node')
            depth -= 1
            children.pop()
            closed = depth == 0
        elif token == 3:
            require(depth > 0 and not children[-1] and pos + 8 <= end, 'bad FDT property')
            size, name = struct.unpack_from('>II', data, pos)
            pos += 8
            require(name < sn and size <= end - pos, 'bad FDT property bounds')
            stop = data.find(b'\0', ss + name, ss + sn)
            require(stop > ss + name, 'bad FDT property name')
            pos = align(pos + size, 4)
        elif token == 9:
            require(seen and closed and depth == 0 and pos == end, 'bad FDT end')
            return
        else:
            require(token == 4, 'unknown FDT token')
        require(pos <= end, 'truncated FDT structure')
    raise ValueError('missing FDT end')


def elf_segments(data):
    require(64 <= len(data) <= MAX_SIZE, 'ELF size outside bounds')
    fields = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    ident, kind, machine, version, entry, phoff, _, _, ehsize, phsize, count, *_ = fields
    require(ident[:7] == b'\x7fELF\x02\x01\x01' and kind == 2 and machine == 183
            and version == 1 and ehsize == 64, 'expected little-endian AArch64 ET_EXEC')
    require(phsize == 56 and 0 < count <= 128 and phoff >= 64
            and phoff + count * phsize <= len(data), 'bad ELF program headers')
    segments = []
    for i in range(count):
        kind, flags, off, va, pa, filesz, memsz, alignment = struct.unpack_from('<II6Q', data, phoff + i * phsize)
        if kind in (2, 3):
            raise ValueError('dynamic/interpreted ELF is unsupported')
        if kind != 1:
            continue
        if memsz == 0:
            require(filesz == 0, "file-backed ELF segment has zero memory size")
            continue
        require(flags & ~7 == 0 and not (flags & 1 and flags & 2), 'unsupported/WX ELF segment')
        require(pa == va, 'physical relocation is unsupported')
        require(span(va, memsz) and filesz <= memsz and off + filesz <= len(data), 'bad ELF segment bounds')
        require(alignment in (0, 1) or (alignment & (alignment - 1) == 0
                and va % alignment == off % alignment), 'bad ELF segment alignment')
        require(not any(overlap(va, memsz, s[0], s[1]) for s in segments), 'overlapping ELF load segments')
        segments.append((va, memsz, data[off:off + filesz], flags))
    require(0 < len(segments) <= MAX_SEGMENTS, 'unsupported ELF load segment count')
    segments.sort()
    require(any(flags & 1 and va <= entry < va + len(content)
                for va, _, content, flags in segments), 'ELF entry is not in executable file-backed bytes')
    return entry, segments


def build(elf, dtb, cmdline='', phys_base=None, mem_size=None):
    validate_dtb(dtb)
    entry, segments = elf_segments(elf)
    virt_base = segments[0][0]
    require(not virt_base % 4096, 'ELF base must be page aligned')
    require(phys_base is None or phys_base == virt_base, 'physical relocation is unsupported')
    kernel_end = align(max(va + size for va, size, _, _ in segments))
    dtb_dest_end = kernel_end + len(dtb)
    required = align(dtb_dest_end) - virt_base
    require(span(virt_base, required) and required <= MAX_SIZE, 'load extent exceeds 64 MiB')
    if mem_size is None:
        mem_size = required
    require(required <= mem_size <= MAX_SIZE and span(virt_base, mem_size), 'invalid destination extent')
    line = cmdline.encode('utf-8')
    require(len(line) < 608 and b'\0' not in line, 'cmdline must fit 607 bytes without NUL')
    payload = bytearray(align(HEADER.size + len(segments) * SEGMENT.size, 8))
    records = []
    for va, size, content, _ in segments:
        records.append((va, size, len(payload), len(content)))
        payload.extend(content)
        payload.extend(b'\0' * (-len(payload) % 8))
    dtb_off = len(payload)
    payload.extend(dtb)
    require(len(payload) <= MAX_SIZE, 'container exceeds 64 MiB')
    HEADER.pack_into(payload, 0, MAGIC, 1, len(segments), virt_base, entry,
                     dtb_off, len(dtb), kernel_end, virt_base, mem_size, line)
    for i, record in enumerate(records):
        SEGMENT.pack_into(payload, HEADER.size + i * SEGMENT.size, *record)
    return bytes(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--dtb', type=Path, required=True)
    parser.add_argument('-o', '--output', type=Path, required=True)
    parser.add_argument('--cmdline', default='')
    parser.add_argument('--phys-base', type=lambda s: int(s, 0))
    parser.add_argument('--mem-size', type=lambda s: int(s, 0))
    args = parser.parse_args()
    try:
        require(args.elf.stat().st_size <= MAX_SIZE and args.dtb.stat().st_size <= 2 * 1024 * 1024,
                'input file exceeds size limit')
        blob = build(args.elf.read_bytes(), args.dtb.read_bytes(), args.cmdline, args.phys_base, args.mem_size)
        # Exclusive creation preserves existing files, including symlink targets.
        with args.output.open('xb') as out:
            out.write(blob)
    except (ValueError, OSError, struct.error) as exc:
        parser.exit(2, f'mkpayload: {exc}\n')
    print(f'S21R10 v1: {len(blob)} bytes; inspection only, hardware handoff disabled')


if __name__ == '__main__':
    main()
