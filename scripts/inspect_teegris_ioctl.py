#!/usr/bin/env python3
"""Static HZC2 libteesl -> ELF linkage -> libtzsl ioctl -> SVC boundary.

Versioned dependencies describe the link contract, not a runtime symbol
resolution observation. No firmware, syscall, device, MMIO or SMC is executed.
"""
import argparse
import hashlib
import json
import struct

from inspect_el2_hzc2 import read_exact
from inspect_lk_final_edges import flow
from inspect_epbl_protocol import unsigned_access
from inspect_tzar_hzc2 import (SIZE, SHA256, INNER_SHA256, inner_archive,
    archive_entries, elf64, span, at_address, witnesses)

VERSYM, VERDEF, VERNEED = 0x6fffffff, 0x6ffffffd, 0x6ffffffe


def section(elf, kind):
    found = [s for s in elf['sections'] if s[1] == kind]
    if len(found) != 1:
        raise ValueError('expected one ELF section of selected type')
    s = found[0]
    return s, span(elf['data'], s[4], s[5])


def strings_for(elf, s):
    if not 0 <= s[6] < len(elf['sections']):
        raise ValueError('ELF section link out of bounds')
    strings = elf['sections'][s[6]]
    if strings[1] != 3:
        raise ValueError('ELF section must link a string table')
    return span(elf['data'], strings[4], strings[5])


def string(table, index):
    if not 0 <= index < len(table):
        raise ValueError('string offset out of bounds')
    end = table.find(b'\0', index, min(len(table), index + 1024))
    if end < 0:
        raise ValueError('unterminated ELF metadata string')
    return table[index:end].decode('ascii')


def dynamic_names(elf):
    s, raw = section(elf, 6)
    if s[9] != 16 or len(raw) % 16 or len(raw) // 16 > 4096:
        raise ValueError('invalid dynamic table size')
    strings = strings_for(elf, s)
    needed, soname, ended = [], None, False
    for offset in range(0, len(raw), 16):
        tag, value = struct.unpack_from('<qQ', raw, offset)
        if ended:
            if tag or value:
                raise ValueError('nonzero dynamic entry after NULL')
            continue
        if tag == 0:
            if value:
                raise ValueError('nonzero dynamic NULL payload')
            ended = True
        elif tag == 1:
            name = string(strings, value)
            if name in needed:
                raise ValueError('duplicate needed library')
            needed.append(name)
        elif tag == 14:
            if soname is not None:
                raise ValueError('duplicate SONAME')
            soname = string(strings, value)
    if not ended:
        raise ValueError('unterminated dynamic table')
    return dict(needed=needed, soname=soname)


def symbol_version_index(elf, name):
    s, raw = section(elf, VERSYM)
    if s[6] != elf['dynsym_section_index'] or s[9] != 2 or len(raw) != elf['dynsym_count'] * 2:
        raise ValueError('invalid symbol version table/link')
    value = struct.unpack('<H', span(raw, elf['symbols'][name]['index'] * 2, 2))[0]
    if (value & 0x7fff) <= 1:
        raise ValueError('selected symbol is not versioned')
    return value & 0x7fff, bool(value & 0x8000)


def version_records(elf, kind):
    """Bounded GNU verneed/verdef chains; offsets stay inside their section."""
    if kind not in (VERNEED, VERDEF):
        raise ValueError('unsupported version record dialect')
    s, raw = section(elf, kind)
    strings = strings_for(elf, s)
    if not 1 <= s[7] <= 64:
        raise ValueError('invalid version record count')
    cursor, result = 0, {}
    for i in range(s[7]):
        if kind == VERNEED:
            version, count, filename, auxiliary, following = struct.unpack('<HHIII', span(raw, cursor, 16))
            minimum, aux_size = 16, 16
            filename = string(strings, filename)
        else:
            version, _, index, count, _, auxiliary, following = struct.unpack('<HHHHIII', span(raw, cursor, 20))
            minimum, aux_size, filename = 20, 8, None
        if version != 1 or not 1 <= count <= 64 or auxiliary < minimum:
            raise ValueError('invalid version record header')
        stop = cursor + following if following else len(raw)
        if (i + 1 < s[7]) != bool(following) or not cursor + minimum <= stop <= len(raw):
            raise ValueError('invalid version record chain')
        aux = cursor + auxiliary
        for j in range(count):
            if not cursor + minimum <= aux or aux + aux_size > stop:
                raise ValueError('version auxiliary outside its record')
            if kind == VERNEED:
                _, _, index, name, next_aux = struct.unpack('<IHHII', span(raw, aux, aux_size))
            else:
                name, next_aux = struct.unpack('<II', span(raw, aux, aux_size))
            label = string(strings, name)
            # Verdef additional auxiliaries name parents, not additional IDs.
            if kind == VERNEED or j == 0:
                key = index & 0x7fff
                if key == 0 or (kind == VERNEED and key == 1) or key in result:
                    raise ValueError('invalid/duplicate version index')
                result[key] = dict(version=label, library=filename)
            if (j + 1 < count) != bool(next_aux) or (next_aux and next_aux < aux_size):
                raise ValueError('invalid version auxiliary chain')
            aux += next_aux
        cursor = stop
    if cursor != len(raw):
        raise ValueError('unconsumed version records')
    return result


def jump_slot(elf, name):
    index = elf['symbols'][name]['index']
    found = []
    for s in elf['sections']:
        if s[1] != 4 or s[6] != elf['dynsym_section_index']:
            continue
        if s[9] != 24 or s[5] % 24 or s[5] // 24 > 65536:
            raise ValueError('invalid RELA table')
        raw = span(elf['data'], s[4], s[5])
        for offset in range(0, len(raw), 24):
            address, info, addend = struct.unpack_from('<QQq', raw, offset)
            if info >> 32 >= elf['dynsym_count']:
                raise ValueError('relocation symbol outside dynamic table')
            if info >> 32 == index and info & 0xffffffff == 1026:
                if addend:
                    raise ValueError('unexpected JUMP_SLOT addend')
                at_address(elf, address, 8)
                found.append(address)
    if len(found) != 1:
        raise ValueError('expected unique AArch64 JUMP_SLOT')
    return found[0]


def plt_slot(raw, pc):
    """ADRP X16; LDR X17,[X16,#n]; ADD X16,X16,#n; BR X17."""
    if type(pc) is not int or not 0 <= pc < 1 << 64 or pc % 4 or len(raw) != 16:
        raise ValueError('invalid PLT bounds')
    adrp, load, add, branch = struct.unpack('<4I', raw)
    if adrp & 0x9f00001f != 0x90000010 or branch != 0xd61f0220:
        raise ValueError('unsupported PLT registers/control')
    value = ((adrp >> 5) & 0x7ffff) << 2 | ((adrp >> 29) & 3)
    signed = value - (1 << 21) if value & (1 << 20) else value
    base = (pc & ~4095) + (signed << 12)
    access = unsigned_access(load)
    if access is None or access[:4] != ('read', 8, 17, 16) or add & 0xffc003ff != 0x91000210:
        raise ValueError('unsupported PLT load/add')
    offset = (add >> 10) & 4095
    if offset != access[4] or not 0 <= base + offset < 1 << 64:
        raise ValueError('PLT load/add address mismatch')
    return base + offset


def normalize_return(raw):
    """Arithmetic after SVC for an explicitly supplied X0; no response injected."""
    if type(raw) is not int or not 0 <= raw < 1 << 64:
        raise ValueError('explicit unsigned 64-bit syscall return required')
    error = raw > (1 << 64) - 4096
    return dict(return_w0=0xffffffff if error else raw & 0xffffffff,
                errno_word=(-raw) & 0xffffffff if error else None)


def evidence(path):
    raw = read_exact(path, SIZE, SHA256)
    archive, _ = inner_archive(raw)
    if hashlib.sha256(archive).hexdigest() != INNER_SHA256:
        raise ValueError('decoded archive identity differs')
    entries = archive_entries(archive)
    caller_name, provider_name = '/lib64/libteesl.so', '/lib64/libtzsl.so'
    caller, provider = [elf64(entries[name]['data']) for name in (caller_name, provider_name)]
    caller_dynamic, provider_dynamic = dynamic_names(caller), dynamic_names(provider)
    required_index, hidden_requirement = symbol_version_index(caller, 'ioctl')
    provided_index, hidden_definition = symbol_version_index(provider, 'ioctl')
    requirement = version_records(caller, VERNEED)[required_index]
    definition = version_records(provider, VERDEF)[provided_index]
    if (requirement['library'] != provider_dynamic['soname'] or requirement['version'] != definition['version']
        or requirement['library'] not in caller_dynamic['needed'] or caller['symbols']['ioctl']['section'] != 0
        or provider['symbols']['ioctl']['section'] == 0):
        raise ValueError('declared ioctl dependency does not match provider')
    slot = jump_slot(caller, 'ioctl')
    calls = []
    for pc in (0x2a894, 0x2c860):
        offset, word = at_address(caller, pc, 4, executable=True)
        kind, target = flow(struct.unpack('<I', word)[0], pc)
        if kind != 'bl' or plt_slot(at_address(caller, target, 16, executable=True)[1], target) != slot:
            raise ValueError('caller/PLT/relocation mismatch')
        calls.append(dict(call_address=hex(pc), file_offset=hex(offset), plt_address=hex(target), slot=hex(slot)))
    function = provider['symbols']['ioctl']
    if (function['address'], function['size']) != (0x8654, 72):
        raise ValueError('provider ioctl extent changed')
    expected = (0xa9be7bfd, 0x93407c00, 0x93407c21, 0xd28001e7, 0x910003fd, 0xf9000bf3,
        0xd4000001, 0xaa0003f3, 0xb140041f, 0x540000a9, 0x4b1303f3, 0x97fff39c,
        0xb9000013, 0x92800013, 0x2a1303e0, 0xf9400bf3, 0xa8c27bfd, 0xd65f03c0)
    if struct.unpack('<18I', at_address(provider, 0x8654, 72, executable=True)[1]) != expected:
        raise ValueError('ioctl syscall/errno instruction template differs')
    return dict(mode='static_declared_ELF_link_and_SVC_boundary', tzar_sha256=SHA256,
        libraries={name: dict(size=len(entries[name]['data']), sha256=hashlib.sha256(entries[name]['data']).hexdigest())
                   for name in (caller_name, provider_name)},
        declared_link=dict(caller=caller_name, provider=provider_name, caller_needed=caller_dynamic['needed'],
            provider_soname=provider_dynamic['soname'], symbol='ioctl', version=requirement['version'],
            required_version_index=required_index, provided_version_index=provided_index,
            requirement_hidden=hidden_requirement, definition_hidden=hidden_definition,
            relocation_type='R_AARCH64_JUMP_SLOT', relocation_symbol_index=caller['symbols']['ioctl']['index'],
            provider_symbol_index=provider['symbols']['ioctl']['index'],
            relocation_slot=hex(slot), calls=calls, runtime_symbol_resolution_observed=False),
        caller_witnesses=witnesses(caller, ((0x2a894, 0x2a898), (0x2c860, 0x2c864), (0x9760, 0x9770))),
        provider_witnesses=witnesses(provider, ((0x8654, 0x869c),)),
        boundary=dict(svc_address='0x866c', instruction='svc #0', selector_register='X7', selector_value=15,
            x0='sign-extended W0 file descriptor', x1='sign-extended W1 ioctl request',
            x2='caller argument pointer passed through; pointed bytes not read by this wrapper',
            svc_handler_identified=False, device_consumer_identified=False),
        return_normalization=dict(error_signed_X0_range=[-4095, -1], excluded_boundary=-4096,
            return_width_bits=32, error_return_W0='0xffffffff', errno_store_width_bits=32,
            errno_address_observed=False,
            examples={str(value): normalize_return(value & ((1 << 64) - 1)) for value in (0, 1, -1, -4095, -4096, 0x100000001)}),
        limits=['Version requirements identify a declared provider; runtime interposition/loading was not observed',
            'SVC handler, driver dispatch, device state and EPBL MMIO 0x19 remain unresolved'],
        firmware_executed=False, syscall_executed=False, physical_device_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tzar')
    args = parser.parse_args()
    try:
        print(json.dumps(evidence(args.tzar), indent=2))
    except (ValueError, OSError, KeyError, UnicodeError, struct.error) as error:
        parser.exit(2, f'{error}\n')
