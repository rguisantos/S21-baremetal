#!/usr/bin/env python3
"""Bounded ARM64/PE layout and prefix evidence; no producer attribution."""
import struct

from capture_a0_formats import MAX_IMAGE, digest, require
from capture_a0_sizes import arm64_header


def pe_layout(image):
    header = arm64_header(image)
    require(len(image) <= MAX_IMAGE and image[:2] == b'MZ', 'requires EFI ARM64 Image')
    pe = struct.unpack_from('<I',image,60)[0]
    require(64 <= pe <= 4096 and pe+24 <= len(image) and image[pe:pe+4] == b'PE\0\0', 'PE header extent/magic')
    machine, count = struct.unpack_from('<HH',image,pe+4); optional_size = struct.unpack_from('<H',image,pe+20)[0]
    optional = pe+24; table = optional+optional_size
    require(machine == 0xaa64 and count == 2 and optional_size >= 112 and table+40*count <= 4096
        and table+40*count <= len(image) and struct.unpack_from('<H',image,optional)[0] == 0x20b,
        'unsupported PE machine/section profile')
    code, initialized, uninitialized, entry, base = struct.unpack_from('<5I',image,optional+4)
    section_align, file_align = struct.unpack_from('<II',image,optional+32)
    runtime, headers = struct.unpack_from('<II',image,optional+56)
    require((section_align,file_align) == (4096,512) and runtime == header['runtime_image_size'], 'PE/Linux size or alignment differs')
    sections = {}
    for i in range(count):
        name, vs, va, rs, rp = struct.unpack_from('<8s4I',image,table+40*i)
        name = name.rstrip(b'\0').decode('ascii')
        require(name in ('.text','.data') and name not in sections and rp+rs <= len(image)
            and va+vs <= runtime, 'PE section bounds/name')
        sections[name] = dict(virtual_bytes=vs,rva=va,file_bytes=rs,file_offset=rp)
    require(set(sections) == {'.text','.data'}, 'PE sections missing')
    text, data = sections['.text'], sections['.data']
    require(text['rva'] == text['file_offset'] == base == headers == 4096
        and text['file_bytes'] == text['virtual_bytes'] == code
        and data['rva'] == data['file_offset'] == headers+code
        and initialized == data['virtual_bytes'] and uninitialized == 0
        and data['rva']+data['virtual_bytes'] == runtime,
        'PE layout does not follow the pinned source expressions')
    branch = struct.unpack_from('<I',image,4)[0]
    require(branch & 0xfc000000 == 0x14000000, 'primary header B instruction differs')
    immediate = branch & 0x3ffffff
    if immediate & (1<<25): immediate -= 1<<26
    primary = 4+4*immediate
    require(4096 <= primary < data['rva'] and 4096 <= entry < data['rva'], 'entry coordinates outside PE code region')
    file_end = data['file_offset']+data['file_bytes']
    return dict(file_bytes=len(image),sha256=digest(image),linux_header=header,pe_offset=pe,
        pe_runtime_bytes=runtime,headers_bytes=headers,sections=sections,
        primary_branch_target=primary,efi_entry_rva=entry,
        mapped_file_end=file_end,unmapped_file_tail_bytes=len(image)-file_end,
        virtual_tail_without_file_bytes=runtime-file_end)


def explain_delta(stock, candidate):
    a,b = pe_layout(stock),pe_layout(candidate)
    require(a['unmapped_file_tail_bytes'] == b['unmapped_file_tail_bytes'] == 0, 'observed Image profile has unmapped file overlay')
    change = lambda x,y: y-x
    parts = {name:{k:change(a['sections'][name][k],b['sections'][name][k])
        for k in ('virtual_bytes','rva','file_bytes','file_offset')} for name in ('.text','.data')}
    file_delta = change(a['file_bytes'],b['file_bytes']); memory_delta = change(a['pe_runtime_bytes'],b['pe_runtime_bytes'])
    require(file_delta == parts['.text']['file_bytes']+parts['.data']['file_bytes']
        and memory_delta == parts['.text']['virtual_bytes']+parts['.data']['virtual_bytes'], 'size delta not accounted for')
    return dict(stock=a,candidate=b,file_delta_bytes=file_delta,runtime_delta_bytes=memory_delta,
        primary_branch_target_delta=b['primary_branch_target']-a['primary_branch_target'],
        efi_entry_rva_delta=b['efi_entry_rva']-a['efi_entry_rva'],
        section_deltas=parts,delta_fully_accounted_by_pe_layout=True,
        producer_build_cause_identified=False,padding_validated=False,physical_layout_measured=False)


def prefix_evidence(module, length, recorded_sha256):
    require(64 <= length < len(module) <= 128*1024*1024 and module[:7] == b'\x7fELF\x02\x01\x01'
        and struct.unpack_from('<HHI',module,16) == (1,183,1), 'requires intact ELF64 AArch64 module and shorter prefix')
    shoff = struct.unpack_from('<Q',module,40)[0]
    shsize,count = struct.unpack_from('<HH',module,58)
    require(shsize == 64 and 0 < count <= 4096 and 64 <= shoff and shoff+count*64 <= len(module), 'full module section table differs')
    prefix_sha = digest(module[:length])
    return dict(full_bytes=len(module),full_sha256=digest(module),prefix_bytes=length,prefix_sha256=prefix_sha,
        recorded_truncated_sha256=recorded_sha256,recorded_hash_matches_prefix=prefix_sha == recorded_sha256,
        absent_tail_bytes=len(module)-length,section_table_offset=shoff,section_table_bytes=count*64,
        section_table_fits_prefix=shoff+count*64 <= length,historical_mutator_identified=False)
