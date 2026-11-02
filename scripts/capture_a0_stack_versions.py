#!/usr/bin/env python3
"""Read final SSP relocation sites and bounded modpost-generated version rows."""
import re
import struct

from capture_a0_formats import require
from capture_a0_module_policy import Elf

HELPERS = {'__stack_chk_fail', '__stack_chk_guard'}


def version_rows(text):
    require(len(text) <= 128*1024, 'generated source bound')
    blocks = re.findall(r'__used __section\(__versions\) = \{(.*?)\n\};', text, re.S)
    require(len(blocks) == 1, 'generated versions section missing/ambiguous')
    rows = {}
    for line in blocks[0].splitlines():
        if not line.strip():
            continue
        m = re.fullmatch(r'\s*\{\s*(0x[0-9a-fA-F]{1,8}|0), "([A-Za-z_][A-Za-z0-9_.$]*)" \},', line)
        require(m and m[2] not in rows, 'generated version row invalid/duplicate')
        rows[m[2]] = f'0x{int(m[1], 16):08x}'
    require('module_layout' in rows, 'generated module_layout missing')
    return rows


def offsets(text):
    require(len(text) <= 256*1024, 'offset assembly bound')
    rows = re.findall(r'->(\w+) ([#$]?\d+) ', text)
    require(rows and len(rows) <= 1024 and len(dict(rows)) == len(rows), 'offset marker ambiguity')
    return '\n'.join('#define '+n+' '+v.lstrip('#$') for n, v in rows)+'\n'


def coverage_delta(original, generated):
    require(all(generated.get(n) == crc for n, crc in original['versions'].items()),
            'existing version changed/removed')
    expected = set(original['imports']) | {'module_layout'}
    require(set(generated) == expected, 'generated records do not cover precisely final imports/layout')
    return {n: generated[n] for n in sorted(generated.keys()-original['versions'].keys())}


def stack_sites(data):
    elf = Elf(data)
    require('.text' in elf.sections, 'text missing')
    target = elf.sections['.text']; code = elf.read(target); sites = []
    kinds = {275: ('__stack_chk_guard', 0x9f000000, 0x90000000),
             286: ('__stack_chk_guard', 0xffc00000, 0xf9400000),
             283: ('__stack_chk_fail', 0xfc000000, 0x94000000)}
    for i, row in enumerate(elf.rows[1:], 1):
        if row[1] != 4 or row[7] != target:
            continue
        require(row[6] == elf.symindex and row[9] == 24 and row[5] % 24 == 0, 'text relocation ABI')
        raw = elf.read(i)
        for pos in range(0, len(raw), 24):
            off, info, addend = struct.unpack_from('<QQq', raw, pos)
            require(info >> 32 < len(elf.symbols), 'text relocation symbol bound')
            sym = elf.symbols[info >> 32]
            if sym['name'] not in HELPERS:
                continue
            kind = info & 0xffffffff
            require(kind in kinds and kinds[kind][0] == sym['name'] and sym['section'] == 0
                    and sym['binding'] == 1 and addend == 0 and off % 4 == 0
                    and off+4 <= len(code), 'SSP relocation ABI/bounds')
            owners = [s for s in elf.symbols if s['type'] == 2 and s['section'] == target
                      and s['value'] <= off < s['value']+s['size']]
            require(len(owners) == 1, 'SSP function ownership ambiguous/missing')
            word = struct.unpack_from('<I', code, off)[0]
            require(word & kinds[kind][1] == kinds[kind][2], 'SSP relocation instruction differs')
            owner = owners[0]
            sites.append(dict(symbol=sym['name'],relocation=kind,text_offset=off,
                function=owner['name'].split('$')[0],function_offset=off-owner['value'],
                instruction=f'0x{word:08x}'))
    require({s['symbol'] for s in sites} == HELPERS, 'SSP sites incomplete')
    return sorted(sites, key=lambda s:s['text_offset'])
