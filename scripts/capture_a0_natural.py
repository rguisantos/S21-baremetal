#!/usr/bin/env python3
"""Laboratory B geometry: natural payload lengths, unchanged total file size.

Only Android v3 and the canonical RSA4096 profile accepted by the existing
reader are supported. Opaque bytes are moved unchanged, not authenticated as
Samsung metadata. This module neither updates a parent vbmeta nor authorizes
physical use of any output.
"""
import hashlib
import struct

from capture_a0_container import PAYLOADS, describe, signature_valid, template
from capture_a0_formats import align, digest, layout, require
from inspect_lk_embedded_key import inspect_avb_rsa_key


def stage(original, replacements):
    """Rebuild all intervals, retaining opaque bytes and the EOF coordinate.

    Footer coordinates and descriptor image_size are updated. Digest/RSA are
    intentionally stale until separately rehashed/authenticated. An empty or
    byte-identical replacement set must reproduce the stock bytes exactly.
    """
    p = template(original); inv = p['inventory']; page = inv['page_size']
    require(isinstance(replacements, dict) and set(replacements) <= PAYLOADS[inv['kind']],
        'unsupported natural replacement')
    rows = {r['name']: r for r in inv['parts']}
    for row in inv['parts']:
        if row['kind'] == 'padding':
            require(not any(original[row['start']:row['end']]), 'noncanonical nonzero padding')
    for name, data in replacements.items():
        require(name in rows and type(data) is bytes and 0 < len(data) <= len(original),
            'natural payload must be nonempty bounded bytes')
    header = bytearray(original[:rows['header']['end']])
    names = ('kernel', 'ramdisk') if inv['kind'] == 'boot_v3' else ('ramdisk', 'dtb')
    offsets = (8, 12) if inv['kind'] == 'boot_v3' else (24, 2100)
    payloads = {}
    for name, offset in zip(names, offsets):
        row = rows.get(name)
        previous = original[row['start']:row['end']] if row else b''
        payloads[name] = replacements.get(name, previous)
        struct.pack_into('<I', header, offset, len(payloads[name]))
    body = bytearray(header); body.extend(b'\0'*(align(len(body), page)-len(body)))
    for name in names:
        body.extend(payloads[name]); body.extend(b'\0'*(align(len(body), page)-len(body)))
        require(len(body) <= len(original)-64, 'natural body exceeds laboratory file bound')
    opaque = original[inv['body_end']:inv['avb']['offset']]
    signed_bytes = p['extent']-inv['body_end']
    require(0 <= signed_bytes <= len(opaque), 'signed opaque extent differs')
    extent = len(body)+signed_bytes; offset = len(body)+len(opaque)
    require(offset % page == 0, 'natural vbmeta offset is not page aligned')
    meta = bytearray(p['meta'])
    struct.pack_into('>Q', meta, p['descriptor']+16, extent)
    require(offset+len(meta) <= len(original)-64, 'natural metadata exceeds laboratory file bound')
    output = body+opaque+meta
    output.extend(b'\0'*(len(original)-64-len(output)))
    footer = bytearray(original[-64:])
    struct.pack_into('>QQQ', footer, 12, extent, offset, len(meta))
    output.extend(footer)
    output = bytes(output); q = describe(output)
    require(len(output) == len(original) and q['extent'] == extent, 'natural reconstructed extent differs')
    return output


def rehash(staged):
    """Hash-only negative control; the previous RSA is not repaired."""
    p = describe(staged); output = bytearray(staged)
    h = hashlib.sha256(p['salt']); h.update(memoryview(staged)[:p['extent']])
    at = p['inventory']['avb']['offset']+p['digest_offset']
    output[at:at+32] = h.digest()
    return bytes(output)


def seal_lab(original, replacements, public_key, signer):
    """Build and authenticate B with an explicit key different from stock."""
    stock = template(original)
    require(type(public_key) is bytes and len(public_key) == 1032
        and inspect_avb_rsa_key(public_key)['key_num_bits'] == 4096, 'invalid natural lab key')
    require(public_key != stock['key'], 'laboratory key must differ from stock')
    output = bytearray(rehash(stage(original, replacements))); p = describe(bytes(output))
    offset = p['inventory']['avb']['offset']; at = offset+p['key_offset']
    output[at:at+1032] = public_key
    meta = bytes(output[offset:offset+len(p['meta'])])
    signing_input = meta[:256]+meta[256+p['auth']:]
    signature = signer(signing_input)
    require(type(signature) is bytes and len(signature) == 512, 'natural signer output differs')
    output[offset+256:offset+288] = hashlib.sha256(signing_input).digest()
    output[offset+288:offset+800] = signature
    output = bytes(output); q = describe(output)
    require(q['inventory']['avb']['all_hashes_match'] and signature_valid(q),
        'natural laboratory authentication failed')
    return output


def evidence(original, output):
    """Report the complete observed layout, without promoting it to trust."""
    p = template(original); q = describe(output)
    before = p['inventory']; after = q['inventory']
    require(len(output) == len(original), 'natural result file length differs')
    old_opaque = original[before['body_end']:before['avb']['offset']]
    new_opaque = output[after['body_end']:after['avb']['offset']]
    return dict(bytes=len(output), sha256=digest(output), byte_identical=output == original,
        original_layout=before, output_layout=after,
        signed_extension_bytes=q['extent']-after['body_end'],
        opaque_extension_bytes=len(new_opaque), opaque_bytes_preserved=old_opaque == new_opaque,
        vbmeta_header_preserved=p['meta'][:256] == q['meta'][:256],
        embedded_public_key_sha256=digest(q['key']),
        hash_descriptors_match=after['avb']['all_hashes_match'],
        rsa_signature_matches_embedded_key=signature_valid(q),
        footer_at_same_eof=True, physical_partition_capacity_established=False,
        samsung_signerver03_validated=False, samsung_acceptance_established=False,
        parent_vbmeta_status='not_supplied_not_assumed_unaffected', parent_vbmeta_updated=False,
        module_abi_established=False, a0_complete=False, a1_started=False, physical_action=False)
