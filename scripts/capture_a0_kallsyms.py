#!/usr/bin/env python3
"""Bounded reader for the observed 5.4 ARM64 relative kallsyms profile.

An Image is not an ELF section table. Named linker intervals recovered here
must not be described as stock ELF section sizes or a compiler attribution.
"""
import struct

from capture_a0_formats import align, digest, require
from capture_a0_layout import pe_layout

LINK_BASE = 0xffffffc010080000
MAX_SYMBOLS = 300000
DIGITS = b'0\x001\x002\x003\x004\x005\x006\x007\x008\x009\x00'


def token_tables(image):
    """Use retained digit tokens only as a locator; verify all 256 indexes."""
    found = []; cursor = 0; attempts = 0
    while (hit := image.find(DIGITS, cursor)) >= 0:
        cursor = hit+1; attempts += 1
        require(attempts <= 1024, 'too many token locator candidates')
        try:
            start = hit
            for _ in range(48):
                previous = image.rfind(b'\0', max(0, start-128), start-1)
                require(previous >= 0, 'token prefix absent'); start = previous+1
            require(start % 8 == 0, 'token table alignment')
            tokens = []; indexes = []; end = start
            for _ in range(256):
                stop = image.find(b'\0', end, end+128)
                require(stop >= 0, 'unterminated token')
                token = image[end:stop]
                require(all(32 <= c < 127 for c in token), 'nonprintable token')
                indexes.append(end-start); tokens.append(token); end = stop+1
            index = align(end, 8)
            require(index+512 <= len(image) and image[end:index] == bytes(index-end)
                and image[index:index+512] == struct.pack('<256H', *indexes), 'token index differs')
            require(tokens[48:58] == [str(i).encode() for i in range(10)], 'digit token slots differ')
            found.append((start, index, tokens))
        except ValueError:
            continue
    require(len(found) == 1, 'requires one verified token table')
    return found[0]


def decode(image):
    """Decode and validate offsets, all names, markers and Image boundaries.

    Only the observed unsigned base-relative, non-absolute-percpu format is
    supported. There is no fallback that silently interprets another format.
    """
    pe = pe_layout(image); table, index, tokens = token_tables(image)
    bases = []; pos = 0; needle = struct.pack('<Q', LINK_BASE)
    while (pos := image.find(needle, pos, table)) >= 0:
        if pos % 8 == 0 and pos+16 < table:
            count = struct.unpack_from('<Q', image, pos+8)[0]
            if 0 < count <= MAX_SYMBOLS: bases.append((pos, count))
        pos += 1
        require(len(bases) <= 32, 'too many relative base candidates')
    accepted = []
    for base_at, count in bases:
        try:
            offset_at = base_at-align(count*4, 8); names_at = base_at+16
            require(4096 <= offset_at < base_at and table-names_at <= 8*1024*1024,
                'offset/name table bounds')
            offsets = struct.unpack_from('<'+str(count)+'I', image, offset_at)
            require(all(a <= b for a,b in zip(offsets, offsets[1:]))
                and offsets[-1] <= pe['pe_runtime_bytes'], 'relative symbol order/range')
            rows = []; markers = []; cursor = names_at
            for i, address in enumerate(offsets):
                require(cursor < table, 'name table truncated')
                if i % 256 == 0: markers.append(cursor-names_at)
                size = image[cursor]; cursor += 1
                require(size > 0 and cursor+size <= table, 'compressed name extent')
                expanded = b''.join(tokens[c] for c in image[cursor:cursor+size]); cursor += size
                require(2 <= len(expanded) <= 512 and chr(expanded[0]) in 'AaBbDdGgIiNnRrSsTtUuVvWw'
                    and all(33 <= c < 127 for c in expanded[1:]), 'unsupported symbol name/type')
                rows.append((LINK_BASE+address, chr(expanded[0]), expanded[1:].decode('ascii')))
            marker_at = align(cursor, 8); marker_end = marker_at+4*len(markers)
            require(marker_end <= table and image[cursor:marker_at] == bytes(marker_at-cursor)
                and image[marker_at:marker_end] == struct.pack('<'+str(len(markers))+'I', *markers)
                and align(marker_end, 8) == table
                and image[marker_end:table] == bytes(table-marker_end), 'marker offsets/geometry differ')
            unique = boundaries(rows, ('_text','_stext','_etext','stext','__initdata_begin','_edata','_end'))
            require(unique['_text'] == 0 and unique['_stext'] == 4096
                and unique['stext'] == pe['primary_branch_target']
                and unique['__initdata_begin'] == pe['sections']['.data']['rva']
                and unique['_edata'] == len(image) and unique['_end'] == pe['pe_runtime_bytes'],
                'decoded boundaries disagree with Image')
            accepted.append((rows, dict(symbol_count=count, relative_base=hex(LINK_BASE),
                offsets_at=offset_at, relative_base_at=base_at, names_at=names_at,
                names_bytes=cursor-names_at, markers_at=marker_at, token_table_at=table,
                token_index_at=index, tables_sha256=digest(image[offset_at:index+512]),
                all_markers_verified=True, image_boundaries_verified=True)))
        except ValueError:
            continue
    require(len(accepted) == 1, 'requires one complete validated kallsyms set')
    return accepted[0]


def boundaries(rows, names):
    wanted = set(names); result = {}
    for address, kind, name in rows:
        if name not in wanted: continue
        require(name not in result, 'ambiguous boundary symbol: '+name)
        result[name] = address-LINK_BASE
    require(result.keys() == wanted, 'missing boundary symbols')
    return result


def compare_map(rows, raw):
    require(len(raw) <= 32*1024*1024, 'System.map bound')
    reference = set()
    for line in raw.decode('ascii').splitlines():
        fields = line.split(); require(len(fields) == 3, 'System.map record')
        reference.add((int(fields[0], 16), fields[1], fields[2]))
    require(all(row in reference for row in rows), 'decoded symbol absent/different in System.map')
    return dict(decoded_symbols_matched=len(rows), system_map_sha256=digest(raw))


def alignment_delta(stock, candidate):
    """Account for the observed shift at the pre-init 64 KiB alignment."""
    names = ('_etext','__start_rodata','__end_rodata','__start_notes','__stop_notes',
        'idmap_pg_dir','idmap_pg_end','reserved_pg_dir','swapper_pg_dir',
        '__init_begin','stext','__initdata_begin','_edata','_end')
    decoded = [decode(image) for image in (stock, candidate)]
    limits = [boundaries(rows, names) for rows,meta in decoded]
    profiles = []
    for image, b in zip((stock,candidate), limits):
        require(b['_etext'] == b['__start_rodata']
            and b['idmap_pg_dir'] == align(b['__stop_notes'], 4096)
            and b['idmap_pg_end']-b['idmap_pg_dir'] == 3*4096
            and b['reserved_pg_dir'] == b['idmap_pg_end']
            and b['swapper_pg_dir'] == b['reserved_pg_dir']+4096,
            'unsupported pre-init page-table geometry')
        before_align = b['swapper_pg_dir']+4096; init = b['__init_begin']
        require(init == b['stext'] == align(before_align, 65536)
            and not any(image[before_align:init]), 'pre-init alignment/padding differs')
        profiles.append(dict(symbols=b, before_segment_align=before_align,
            segment_align=65536, zero_alignment_bytes=init-before_align,
            rodata_to_page_tables_bytes=before_align-b['__start_rodata'],
            init_to_initdata_bytes=b['__initdata_begin']-init))
    a,b = profiles
    earlier = b['before_segment_align']-a['before_segment_align']
    padding = b['zero_alignment_bytes']-a['zero_alignment_bytes']
    shift = b['symbols']['__init_begin']-a['symbols']['__init_begin']
    require(earlier+padding == shift
        and b['symbols']['__start_rodata'] == a['symbols']['__start_rodata']
        and b['init_to_initdata_bytes'] == a['init_to_initdata_bytes'], 'alignment delta accounting differs')
    return dict(stock=profiles[0], candidate=profiles[1],
        kallsyms=dict(stock=decoded[0][1],candidate=decoded[1][1]),
        pre_alignment_delta_bytes=earlier, alignment_padding_delta_bytes=padding,
        init_boundary_delta_bytes=shift, source_producer_cause_identified=False,
        stock_elf_section_table_available=False)
