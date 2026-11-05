#!/usr/bin/env python3
"""Compare pinned stock/B with the candidate parent extracted from the BL tar."""
import argparse
from contextlib import ExitStack
import ctypes as c
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import tarfile

from capture_a0_container import describe
from capture_a0_formats import require
from capture_a0_inputs import checked_buffer, read_checked, sealed_input, unique_object
from capture_a0_parent import compare, pin

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT/'docs/references'


def selected_members(data, names, compressed=False, exact=False):
    """No extraction or reopened archive; reject duplicates including unselected."""
    require(type(data) is bytes and len(data) <= 512*1024*1024, 'archive buffer bound')
    selected = {}; seen = set(); total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r|gz' if compressed else 'r|') as tar:
        for m in tar:
            path = PurePosixPath(m.name)
            require(path.parts and not path.is_absolute() and '..' not in path.parts
                and str(path) == m.name and '\\' not in m.name and m.isfile()
                and m.name not in seen and len(seen) < 1000 and 0 <= m.size <= 128*1024*1024,
                'archive path/type/duplicate/budget')
            seen.add(m.name); total += m.size
            require(total <= 512*1024*1024, 'archive logical budget')
            if m.name in names:
                with tar.extractfile(m) as stream: raw = stream.read(m.size+1)
                require(len(raw) == m.size, 'archive member truncated')
                selected[m.name] = raw
    require(selected.keys() == set(names) and (not exact or seen == set(names)), 'archive member set differs')
    return selected


def lz4_frame(data, limit):
    """Single bounded frame from an already checked buffer; no CLI path reopen."""
    require(type(data) is bytes and 0 < len(data) <= 128*1024*1024
        and type(limit) is int and 0 < limit <= 128*1024*1024, 'LZ4 input/output budget')
    lib = c.CDLL('liblz4.so.1')
    lib.LZ4F_createDecompressionContext.argtypes = [c.POINTER(c.c_void_p), c.c_uint]
    lib.LZ4F_createDecompressionContext.restype = c.c_size_t
    lib.LZ4F_decompress.argtypes = [c.c_void_p, c.c_void_p, c.POINTER(c.c_size_t),
        c.c_void_p, c.POINTER(c.c_size_t), c.c_void_p]
    lib.LZ4F_decompress.restype = c.c_size_t
    lib.LZ4F_isError.argtypes = [c.c_size_t]; lib.LZ4F_isError.restype = c.c_uint
    lib.LZ4F_freeDecompressionContext.argtypes = [c.c_void_p]
    source = c.create_string_buffer(data); ctx = c.c_void_p(); at = 0; total = 0; chunks = []
    require(lib.LZ4F_createDecompressionContext(c.byref(ctx), 100) == 0, 'LZ4 context failure')
    try:
        while True:
            output = c.create_string_buffer(min(1024*1024, limit-total+1))
            nd = c.c_size_t(len(output)); ns = c.c_size_t(len(data)-at)
            hint = lib.LZ4F_decompress(ctx, output, c.byref(nd), c.byref(source, at), c.byref(ns), None)
            require(not lib.LZ4F_isError(hint), 'invalid LZ4 frame')
            total += nd.value; at += ns.value
            require(total <= limit, 'LZ4 output exceeds budget')
            chunks.append(output.raw[:nd.value])
            if hint == 0:
                require(at == len(data), 'LZ4 trailing/concatenated input')
                return b''.join(chunks)
            require(ns.value or nd.value, 'truncated/stalled LZ4 frame')
    finally:
        lib.LZ4F_freeDecompressionContext(ctx)


def der(tag, data):
    length = len(data); encoded = length.to_bytes(max(1, (length.bit_length()+7)//8), 'big')
    return bytes([tag])+(bytes([length]) if length < 128 else bytes([128+len(encoded)])+encoded)+data


def native_auth(parent, openssl):
    """Independent OpenSSL RSA; public key/signature come from sealed buffers."""
    auth, aux = struct.unpack_from('>QQ', parent, 12)
    po = struct.unpack_from('>Q', parent, 64)[0]
    n = parent[256+auth+po+8:256+auth+po+520]
    rsa = der(48, der(2, b'\0'+n)+der(2, b'\x01\x00\x01'))
    spki = der(48, bytes.fromhex('300d06092a864886f70d0101010500')+der(3, b'\0'+rsa))
    signature = parent[288:800]; signed = parent[:256]+parent[256+auth:256+auth+aux]
    with ExitStack() as stack:
        key_fd, key_path = stack.enter_context(sealed_input(spki, pin(spki)))
        sig_fd, sig_path = stack.enter_context(sealed_input(signature, pin(signature)))
        r = subprocess.run([openssl, 'dgst', '-sha256', '-keyform', 'DER', '-verify', key_path,
            '-signature', sig_path], input=signed, pass_fds=(key_fd, sig_fd),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, env={'PATH':os.defpath,'LC_ALL':'C'})
    return dict(returncode=r.returncode, signature_matches_embedded_key=r.returncode == 0,
        stdout=r.stdout.decode(errors='replace'), stderr=r.stderr.decode(errors='replace'),
        signing_input=pin(signed), embedded_public_key_only=True, device_key_trust_established=False)


def native_hash(descriptor, image, openssl):
    data = bytes.fromhex(descriptor['salt'])+image[:descriptor['image_size']]
    r = subprocess.run([openssl, 'dgst', '-sha256', '-binary'], input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True,
        env={'PATH':os.defpath,'LC_ALL':'C'})
    require(len(r.stdout) == 32, 'OpenSSL digest output size')
    return r.stdout.hex()


def inspect(bl_path, stock_dir, prototype_path):
    refs = lambda name: json.loads((REFERENCES/name).read_text(), object_pairs_hook=unique_object)
    pins = refs('capture-a0-parent-pins-hzc2.json')
    stock_pins = refs('capture-a0-pins-hzc2.json')
    artifact = refs('capture-a0-natural-b-artifact-20261104.json')
    bl = read_checked(bl_path, pins['bl_archive'])
    packed = selected_members(bl, {'vbmeta.img.lz4'})['vbmeta.img.lz4']
    checked_buffer(packed, pins['parent_lz4'])
    parent = checked_buffer(lz4_frame(packed, pins['parent_raw']['bytes']), pins['parent_raw'])
    stock = {}
    for name in ('boot', 'vendor_boot'):
        filename = name+'.img'
        compressed = read_checked(stock_dir/(filename+'.lz4'), stock_pins['stock_lz4'][filename+'.lz4'])
        stock[name] = checked_buffer(lz4_frame(compressed, stock_pins['stock_raw'][filename]['bytes']),
            stock_pins['stock_raw'][filename])
    archive = read_checked(prototype_path, artifact)
    members = selected_members(archive, set(artifact['payloads']) | {'manifest.json'}, compressed=True, exact=True)
    require(pin(members['manifest.json'])['sha256'] == artifact['manifest_sha256'], 'B manifest identity differs')
    manifest = json.loads(members['manifest.json'], object_pairs_hook=unique_object)
    require(manifest['files'] == artifact['payloads'], 'B manifest/payload pins differ')
    for name, expected in artifact['payloads'].items(): checked_buffer(members[name], expected)
    prototype = {name: members[name+'.img'] for name in stock}
    report = compare(parent, stock, prototype)
    openssl = shutil.which('openssl', path=os.defpath); require(openssl is not None, 'openssl missing')
    report['independent_parent_rsa'] = native_auth(parent, openssl)
    require(report['independent_parent_rsa']['signature_matches_embedded_key'], 'OpenSSL parent RSA differs')
    key_at = 832+struct.unpack_from('>Q', parent, 64)[0]
    parent_key = parent[key_at:key_at+1032]
    for name, row in report['comparisons'].items():
        for label, images in (('stock', stock), ('B', prototype)):
            got = native_hash(row['parent_descriptor'], images[name], openssl)
            require(got == row['variants'][label]['calculated_digest'], 'OpenSSL/hashlib digest differs')
            child = describe(images[name])
            row['variants'][label].update(openssl_digest=got, openssl_matches_hashlib=True,
                child_embedded_key_sha256=pin(child['key'])['sha256'],
                child_key_equals_candidate_parent=child['key'] == parent_key)
    report.update(schema='S21-A0-PARENT-COMPARISON-v1', analysis_completed=True,
        provenance=dict(bl_archive=pins['bl_archive'], member='vbmeta.img.lz4',
            parent_lz4=pin(packed), stock_lz4={n:stock_pins['stock_lz4'][n+'.img.lz4'] for n in stock},
            prototype_archive=pin(archive), prototype_manifest=pin(members['manifest.json']),
            prototype_payloads_verified=len(artifact['payloads']), archive_members_verified=len(members),
            bl_archive_md5_trailer_validated=False),
        method=dict(hash='SHA256(salt || image[0:parent_descriptor.image_size])',
            input_buffers_verified_and_consumed_without_reopen=True, independent_digest_tool='OpenSSL',
            openssl_version=subprocess.check_output([openssl,'version'],env={'PATH':os.defpath,'LC_ALL':'C'}).decode().strip(),
            sources={n:pin((ROOT/'scripts'/n).read_bytes()) for n in
                ('capture_a0_parent.py','check_capture_a0_parent.py','capture_a0_inputs.py','capture_a0_container.py',
                 'capture_a0_formats.py','inspect_lk_embedded_key.py')},
            external_user_verification_completed=False))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bl-archive','stock-lz4-dir','prototype-archive','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.bl_archive, args.stock_lz4_dir, args.prototype_archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f: json.dump(report, f, indent=2); f.write('\n')
    print('PARENT COMPARISON: stock 2/2 PASS; B satisfies unchanged candidate parent:',
        report['B_satisfies_unchanged_candidate_parent'])


if __name__ == '__main__': main()
