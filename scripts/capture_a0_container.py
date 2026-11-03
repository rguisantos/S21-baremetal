#!/usr/bin/env python3
"""Fixed-geometry offline AVB repack. A lab signature is never device trust.

Only the observed boot/vendor_boot v3 SHA256_RSA4096 profile is supported.
Payload lengths, Android headers, opaque extensions and footer remain fixed.
"""
import hashlib
import struct

from capture_a0_formats import align, digest, layout, require
from inspect_lk_embedded_key import inspect_avb_rsa_key

PAYLOADS = {'boot_v3': {'kernel', 'ramdisk'}, 'vendor_boot_v3': {'ramdisk', 'dtb'}}
PARTITIONS = {'boot_v3': 'boot', 'vendor_boot_v3': 'vendor_boot'}
SHA256_DER = bytes.fromhex('3031300d060960864801650304020105000420')


def describe(data):
    """Parse one bounded canonical signed profile; report crypto separately."""
    inv = layout(data)
    require(inv['kind'] in PAYLOADS and inv['avb'], 'requires boot/vendor_boot v3 with AVB')
    av = inv['avb']; offset = av['offset']; meta = data[offset:offset+av['bytes']]
    major, minor, auth, aux, algorithm = struct.unpack_from('>IIQQI', meta, 4)
    fields = struct.unpack_from('>10Q', meta, 32)
    ho, hs, so, ss, po, ps, pmo, pms, do, ds = fields
    require((major, minor, algorithm, auth) == (1, 0, 2, 576)
        and (ho, hs, so, ss, ps, pms, do) == (0, 32, 32, 512, 1032, 0, 0)
        and po == ds and pmo == po+ps and aux == align(ds+ps, 64),
        'unsupported AVB authentication/key/descriptor layout')
    require(not any(meta[176:256]) and b'\0' in meta[128:176], 'AVB reserved/release fields differ')
    require(len(av['hash_descriptors']) == 1, 'requires exactly one hash descriptor')
    desc = 256+auth
    tag, length = struct.unpack_from('>QQ', meta, desc)
    nl, sl, dl, flags = struct.unpack_from('>4I', meta, desc+56)
    require(tag == 2 and length+16 == ds == align(132+nl+sl+dl, 8)
        and dl == 32 and flags == 0 and av['hash_descriptors'][0]['algorithm'] == 'sha256',
        'unsupported descriptor list/hash/flags')
    require(av['hash_descriptors'][0]['partition'] == PARTITIONS[inv['kind']], 'partition/kind differs')
    extent = av['original_image_size']
    require(inv['body_end'] <= extent <= offset, 'payload/extension/hash geometry differs')
    key_start = 256+auth+po; key = meta[key_start:key_start+ps]
    key_info = inspect_avb_rsa_key(key)
    require(key_info['key_num_bits'] == 4096, 'requires RSA4096')
    return dict(inventory=inv, meta=meta, descriptor=desc,
        digest_offset=desc+132+nl+sl, salt=meta[desc+132+nl:desc+132+nl+sl],
        key_offset=key_start, key=key, extent=extent, auth=auth)


def signature_valid(profile):
    """PKCS#1 v1.5 with the embedded key, without asserting key trust."""
    meta = profile['meta']; auth = profile['auth']
    expected = hashlib.sha256(meta[:256]+meta[256+auth:]).digest()
    if meta[256:288] != expected:
        return False
    signature = int.from_bytes(meta[288:800], 'big')
    modulus = int.from_bytes(profile['key'][8:520], 'big')
    if signature >= modulus:
        return False
    encoded = pow(signature, 65537, modulus).to_bytes(512, 'big')
    wanted = b'\0\1'+b'\xff'*(512-3-len(SHA256_DER)-32)+b'\0'+SHA256_DER+expected
    return encoded == wanted


def template(data):
    p = describe(data)
    require(p['inventory']['avb']['all_hashes_match'] and signature_valid(p),
        'template hash or embedded-key signature differs')
    return p


def stage(original, replacements):
    """Replace whole same-sized payloads; preserve every other original byte."""
    p = template(original); inv = p['inventory']
    require(isinstance(replacements, dict) and set(replacements) <= PAYLOADS[inv['kind']],
        'unsupported replacement payload')
    rows = {row['name']: row for row in inv['parts']}
    output = bytearray(original)
    for name, data in replacements.items():
        require(name in rows and type(data) is bytes and len(data) == rows[name]['bytes'],
            'replacement must retain the original payload length')
        row = rows[name]; output[row['start']:row['end']] = data
    return bytes(output)


def staged_profile(original, staged):
    p = template(original); inv = p['inventory']
    require(type(staged) is bytes and len(staged) == len(original), 'partition length/type differs')
    for row in inv['parts']:
        if row['name'] not in PAYLOADS[inv['kind']]:
            require(staged[row['start']:row['end']] == original[row['start']:row['end']],
                'staging changed a non-payload region: '+row['name'])
    return p


def rehash(original, staged):
    """Hash-only negative control. The old RSA authentication becomes stale."""
    p = staged_profile(original, staged); output = bytearray(staged)
    at = p['inventory']['avb']['offset']+p['digest_offset']
    h = hashlib.sha256(p['salt']); h.update(memoryview(staged)[:p['extent']])
    output[at:at+32] = h.digest()
    return bytes(output)


def seal_lab(original, staged, public_key, signer):
    """Rehash and authenticate with an explicit lab key and signing callback.

    The callback signs header+auxiliary bytes with RSA4096/PKCS1-v1.5/SHA256.
    Signature bytes are verified before returning. Samsung opaque bytes are
    preserved, not regenerated or authenticated by this operation.
    """
    p = staged_profile(original, staged)
    require(type(public_key) is bytes and len(public_key) == 1032, 'lab key size/type differs')
    require(inspect_avb_rsa_key(public_key)['key_num_bits'] == 4096, 'lab key must be RSA4096')
    require(public_key != p['key'], 'lab key must differ from the stock template key')
    output = bytearray(rehash(original, staged)); offset = p['inventory']['avb']['offset']
    start = offset+p['key_offset']; output[start:start+1032] = public_key
    meta = bytes(output[offset:offset+len(p['meta'])])
    signing_input = meta[:256]+meta[256+p['auth']:]
    signature = signer(signing_input)
    require(type(signature) is bytes and len(signature) == 512, 'signer output type/size differs')
    output[offset+256:offset+288] = hashlib.sha256(signing_input).digest()
    output[offset+288:offset+800] = signature
    output = bytes(output); result = describe(output)
    require(result['inventory']['avb']['all_hashes_match'] and signature_valid(result),
        'lab signature/hash verification failed')
    return output


def result(original, output):
    p = template(original); q = describe(output); inv = p['inventory']
    require(len(original) == len(output), 'result partition size differs')
    retained = [r for r in inv['parts'] if r['kind'] != 'payload' and r['name'] != 'vbmeta']
    retained_ok = all(original[r['start']:r['end']] == output[r['start']:r['end']] for r in retained)
    return dict(bytes=len(output), sha256=digest(output), byte_identical=original == output,
        payloads=[dict(name=r['name'], bytes=r['bytes'], before_sha256=r['sha256'],
            after_sha256=digest(output[r['start']:r['end']])) for r in inv['parts'] if r['kind'] == 'payload'],
        android_header_and_non_vbmeta_non_payload_bytes_preserved=retained_ok,
        avb_header_preserved=p['meta'][:256] == q['meta'][:256],
        footer_preserved=original[-64:] == output[-64:],
        signed_extension_bytes=p['extent']-inv['body_end'],
        opaque_extension_bytes=inv['avb']['offset']-inv['body_end'],
        original_embedded_key_sha256=digest(p['key']),
        output_embedded_key_sha256=digest(q['key']),
        original_hash_extent=[0, p['extent']],
        output_hash_extent=[0, q['extent']],
        hash_descriptors_match=q['inventory']['avb']['all_hashes_match'],
        rsa_signature_matches_embedded_key=signature_valid(q),
        embedded_key_changed=p['key'] != q['key'],
        key_trust_established=False, samsung_signature_validated=False,
        payload_semantics_validated=False, physical_acceptance_established=False)
