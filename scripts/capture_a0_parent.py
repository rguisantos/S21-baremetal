#!/usr/bin/env python3
"""Bounded HZC2 candidate-parent comparison. Embedded RSA is not device trust."""
import hashlib
import re
import struct

from capture_a0_container import signature_valid
from capture_a0_formats import align, digest, require
from inspect_lk_embedded_key import inspect_avb_rsa_key


def pin(data):
    return dict(bytes=len(data), sha256=digest(data))


def partition_name(data):
    require(re.fullmatch(rb'[a-z][a-z0-9_]{0,63}', data) is not None,
        'unsupported partition name')
    return data.decode('ascii')


def parse_parent(data):
    """Support only the observed SHA256_RSA4096 layout, retaining a full census.

    Property/cmdline descriptor bytes and bytes after the AVB structure are
    identified but not interpreted. This is not a complete libavb policy engine.
    """
    require(type(data) is bytes and 256 <= len(data) <= 1024*1024
        and data[:4] == b'AVB0', 'standalone AVB header/budget')
    major, minor, auth, aux, algorithm = struct.unpack_from('>IIQQI', data, 4)
    ho, hs, so, ss, po, ps, pmo, pms, do, ds = struct.unpack_from('>10Q', data, 32)
    require((major, minor, auth, algorithm) == (1, 0, 576, 2)
        and (ho, hs, so, ss, ps, pms, do) == (0, 32, 32, 512, 1032, 0, 0)
        and po == ds and pmo == po+ps and 0 < ds <= 512*1024
        and aux == align(ds+ps, 64), 'unsupported parent authentication layout')
    extent = 256+auth+aux
    require(extent <= len(data) and not any(data[176:256])
        and b'\0' in data[128:176] and not any(data[800:832])
        and not any(data[832+pmo:extent]), 'truncated parent/reserved/padding')
    meta = data[:extent]; key = meta[832+po:832+po+ps]
    require(inspect_avb_rsa_key(key)['key_num_bits'] == 4096, 'parent key size')
    rollback, flags, rollback_location = struct.unpack_from('>QII', meta, 112)
    require(flags == 0, 'unsupported parent policy flags')
    records = []; names = set(); at = 832; end = at+ds
    while at < end:
        require(len(records) < 128 and at+16 <= end, 'descriptor count/header bound')
        tag, following = struct.unpack_from('>QQ', meta, at)
        size = 16+following
        require(following % 8 == 0 and at+size <= end and tag in (0, 1, 2, 4),
            'descriptor tag/extent')
        raw = meta[at:at+size]
        row = dict(tag=tag, offset=at, **pin(raw))
        if tag == 2:
            require(size >= 132, 'short hash descriptor')
            image_size = struct.unpack_from('>Q', raw, 16)[0]
            nl, sl, dl, df = struct.unpack_from('>4I', raw, 56)
            require(0 < image_size <= 512*1024*1024 and 1 <= nl <= 64
                and sl <= 4096 and dl == 32 and df == 0
                and raw[24:56] == b'sha256'+b'\0'*26 and not any(raw[72:132])
                and size == align(132+nl+sl+dl, 8), 'unsupported hash descriptor')
            name = partition_name(raw[132:132+nl]); salt = raw[132+nl:132+nl+sl]
            wanted = raw[132+nl+sl:132+nl+sl+dl]
            require(not any(raw[132+nl+sl+dl:]), 'hash descriptor padding')
            row.update(partition=name, image_size=image_size, algorithm='sha256',
                flags=df, salt=salt.hex(), digest=wanted.hex())
        elif tag == 4:
            require(size >= 92, 'short chain descriptor')
            location, nl, kl, df = struct.unpack_from('>4I', raw, 16)
            require(1 <= nl <= 64 and kl == 1032 and df == 0
                and not any(raw[32:92]) and size == align(92+nl+kl, 8),
                'unsupported chain descriptor')
            name = partition_name(raw[92:92+nl]); delegated = raw[92+nl:92+nl+kl]
            require(inspect_avb_rsa_key(delegated)['key_num_bits'] == 4096
                and not any(raw[92+nl+kl:]), 'chain key/padding')
            row.update(partition=name, rollback_index_location=location,
                flags=df, public_key_sha256=digest(delegated))
        if tag in (2, 4):
            require(name not in names, 'duplicate partition descriptor')
            names.add(name)
        else:
            row['semantics_evaluated'] = False
        records.append(row); at += size
    require(at == end, 'descriptor list extent')
    return dict(file=pin(data), avb_structure_bytes=extent,
        required_libavb_version=[major, minor], algorithm='SHA256_RSA4096',
        rollback_index=rollback, flags=flags, rollback_index_location=rollback_location,
        public_key_sha256=digest(key),
        rsa_signature_matches_embedded_key=signature_valid(dict(meta=meta, auth=auth, key=key)),
        descriptors=records, trailing_opaque=dict(offset=extent, **pin(data[extent:]), validated=False))


def hash_image(descriptor, image):
    require(type(image) is bytes and descriptor['tag'] == 2
        and descriptor['algorithm'] == 'sha256'
        and 0 < descriptor['image_size'] <= len(image) <= 512*1024*1024,
        'image type/descriptor/extent')
    h = hashlib.sha256(bytes.fromhex(descriptor['salt']))
    h.update(memoryview(image)[:descriptor['image_size']])
    return h.hexdigest()


def compare(parent, stock, prototype):
    info = parse_parent(parent)
    require(info['rsa_signature_matches_embedded_key'], 'candidate parent RSA differs')
    required = {'boot', 'vendor_boot'}
    require(stock.keys() == prototype.keys() == required, 'stock/B positive controls required')
    rows = {}
    for name in sorted(required):
        found = [r for r in info['descriptors'] if r.get('partition') == name and r['tag'] == 2]
        require(len(found) == 1, 'direct parent hash missing')
        d = found[0]; variants = {}
        for label, images in (('stock', stock), ('B', prototype)):
            got = hash_image(d, images[name])
            variants[label] = dict(file=pin(images[name]), calculated_digest=got,
                matches_parent=got == d['digest'])
        require(variants['stock']['matches_parent'], 'stock does not satisfy candidate parent: '+name)
        rows[name] = dict(parent_descriptor=d, variants=variants)
    return dict(parent=info, comparisons=rows,
        stock_positive_controls_pass=True,
        B_satisfies_unchanged_candidate_parent=all(r['variants']['B']['matches_parent'] for r in rows.values()),
        installed_parent_identity_established=False, device_key_trust_established=False,
        full_avb_chain_verified=False, samsung_acceptance_established=False,
        signer_ver03_validated=False, a0_complete=False, a1_started=False,
        device_action_performed=False, physical_use_authorized=False)
