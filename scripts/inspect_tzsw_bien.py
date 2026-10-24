#!/usr/bin/env python3
"""Read-only HZC2 BiEn envelope and candidate-plaintext acceptance gate.

An optional single, pinned Exynos9830 reference trial is checked with two AES
implementations. It never writes plaintext, keys, firmware or signatures.
Matching a stored digest would not authenticate a Samsung signature.
"""
import argparse
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import struct
import subprocess

from inspect_el2_hzc2 import read_exact
from check_epbl_hash_sources import read_reference

SIZE = 1572864
SHA256 = '83eedef172714cc2e24624a12e77ab7e7a2e04891fe98366f653b3e3a6c533c0'
REPOSITORY = 'Creeeeger/CreckerROM'
COMMIT = 'bc9aa7039a6cd5f8cfcfd803ac74f37161fe94a3'
REFERENCES = {
    'tzsw_crypt_tool.py': ('54a974f39fc46949e8645d165fc14382db0a1b53', '656d8ba1070e6bdf0a07529eed3748ca963fe81ea9e68ecf612738ed06cc09a4'),
    'aes_cbc.py': ('af8e23239168be42ec38fefd54442cc164ea8077', '634afa3493c33eb661ac93ca509e1cefc7bf571f7bf9cbf3ca2878bc4b4f5c4c'),
    'binary_io.py': ('fd9aee77fdfa1aed1dd184b26887295c59732581', '56406a41244b7d276941052266d71bca6ef83bfe0974e0695eca73f15c55cf6e'),
    'soc_data.py': ('edbdfbc39c3b020bb819f36087d8745f9efba3b8', '306980d4b1d2e782ecdc0230205e142b2eec8f6ed3e92091b503311f7c192e54'),
}
MARKER = b'ub_tzar_walk_cb\0'


def envelope(data):
    if len(data) < 0x90 or data[0x10:0x14] != b'BiEn' or data[0x18:0x20] != b'teegris\0':
        raise ValueError('unsupported BiEn/teegris envelope')
    start, end = struct.unpack_from('<II', data, 0x28)
    if not 0x90 <= start < end <= len(data) or (end - start) % 16:
        raise ValueError('invalid candidate transformation extent')
    return start, end


def candidate_result(original, candidate):
    """Use original fields/digest; do not accept a candidate's replacement hash."""
    start, end = envelope(original)
    if len(candidate) != len(original):
        return dict(accepted=False, reason='candidate_size_differs')
    outside_equal = candidate[:start] == original[:start] and candidate[end:] == original[end:]
    digest = hashlib.sha256(candidate[start:end]).digest()
    matched = digest == original[0x70:0x90]
    return dict(accepted=outside_equal and matched, outside_region_identical=outside_equal,
        matches_original_stored_SHA256=matched, candidate_region_sha256=digest.hex(),
        reference_marker_present=MARKER in candidate[start:end],
        acceptance_scope='stored-digest correspondence only; Samsung signature/runtime not verified')


def public_constants(source):
    """Read two bytes.fromhex literals with AST only; never import the source."""
    result = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name not in ('MASTER_KEY', 'MASTER_IV'):
            continue
        if name in result:
            raise ValueError('duplicate public reference constant')
        value = node.value
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
            and isinstance(value.func.value, ast.Name) and value.func.value.id == 'bytes'
            and value.func.attr == 'fromhex' and len(value.args) == 1 and not value.keywords
            and isinstance(value.args[0], ast.Constant) and type(value.args[0].value) is str):
            raise ValueError('unsupported public constant expression')
        text = value.args[0].value
        if not re.fullmatch('[0-9a-fA-F]{' + str(64 if name == 'MASTER_KEY' else 32) + '}', text):
            raise ValueError('invalid public reference key/IV width')
        result[name] = bytes.fromhex(text)
    if set(result) != {'MASTER_KEY', 'MASTER_IV'}:
        raise ValueError('public reference constants missing')
    return result['MASTER_KEY'], result['MASTER_IV']


def soc_profiles(source):
    assignments = [n for n in ast.parse(source).body if isinstance(n, ast.Assign) and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'EXYNOS_DATA']
    if len(assignments) != 1:
        raise ValueError('expected one literal EXYNOS_DATA assignment')
    value = ast.literal_eval(assignments[0].value)
    if type(value) is not dict or len(value) > 64 or any(type(k) is not str for k in value):
        raise ValueError('invalid literal SoC profiles')
    return sorted(value)


def aes_trial(data, key, iv, decrypt):
    """Decryptor supplied by this inspector, never by the referenced code."""
    if len(key) != 32 or len(iv) != 16 or not data or len(data) % 16:
        raise ValueError('explicit AES256-CBC block/key/IV widths required')
    return decrypt(data, key, iv)


def reference_probe(data, reference_dir):
    texts, identities = {}, {}
    for name, (blob, digest) in REFERENCES.items():
        identity = (REPOSITORY, COMMIT, 'scripts/samsung_signing/' + name, blob, digest)
        texts[name], identities[name] = read_reference(Path(reference_dir) / name, identity)
    key, iv = public_constants(texts['tzsw_crypt_tool.py'])
    profiles = soc_profiles(texts['soc_data.py'])
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    def cryptography_decrypt(block, key, iv):
        context = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        return context.update(block) + context.finalize()

    def openssl_decrypt(block, key, iv):
        return subprocess.run(['openssl', 'enc', '-aes-256-cbc', '-d', '-nopad', '-nosalt',
            '-K', key.hex(), '-iv', iv.hex()], input=block, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=True, timeout=15).stdout

    start, end = envelope(data)
    results, region, previous_bundle = [], None, None
    for decrypt in (cryptography_decrypt, openssl_decrypt):
        bundle = aes_trial(data[0x40:0x70], key, iv, decrypt)
        if previous_bundle is not None and bundle != previous_bundle:
            raise ValueError('independent AES header-bundle outputs differ')
        previous_bundle = bundle
        transformed = aes_trial(data[start:end], bundle[:32], bundle[32:], decrypt)
        if len(transformed) != end - start:
            raise ValueError('AES backend changed payload size')
        if region is not None and transformed != region:
            raise ValueError('independent AES backend outputs differ')
        region = transformed
        results.append(hashlib.sha256(transformed).hexdigest())
    candidate = data[:start] + region + data[end:]
    return dict(sources=identities, reference_declared_target='Exynos9830',
        reference_soc_profiles=profiles, reference_declares_Exynos2100='Exynos2100\0' in profiles,
        transform_hypothesis='AES256-CBC header bundle [0x40,0x70), then payload using its 32+16 bytes',
        backend_names=['cryptography', 'openssl enc'], backend_region_sha256=results,
        backend_versions=[importlib.metadata.version('cryptography'), subprocess.run(['openssl', 'version'],
            capture_output=True, text=True, check=True, timeout=5).stdout.strip()],
        backend_bundle_bytes_identical=True, backend_bytes_identical=True, result=candidate_result(data, candidate),
        reference_source_executed=False, plaintext_written=False, derived_keys_emitted=False,
        HZC2_algorithm_or_key_proven=False)


def evidence(path, *, reference_dir=None, candidate_path=None):
    data = read_exact(path, SIZE, SHA256)
    start, end = envelope(data)
    report = dict(mode='static_BiEn_envelope_and_candidate_gate', input=dict(size=SIZE, sha256=SHA256),
        envelope=dict(magic_offset='0x10', magic='BiEn', version_bytes=data[0x14:0x18].hex(),
            image_tag='teegris', raw_u32={hex(o): hex(struct.unpack_from('<I', data, o)[0]) for o in range(0x20, 0x40, 4)},
            candidate_region=[hex(start), hex(end)], candidate_size=end - start,
            declared_extent_words_match=struct.unpack_from('<II', data, 0x30) == (end - start, end - start),
            header_bundle_region=['0x40', '0x70'], stored_digest_region=['0x70', '0x90'],
            stored_digest=data[0x70:0x90].hex(), raw_region_sha256=hashlib.sha256(data[start:end]).hexdigest(),
            raw_region_matches_stored_digest=hashlib.sha256(data[start:end]).digest() == data[0x70:0x90],
            layout_source_scope='Exynos9830 reference; HZC2 loader binding not established'),
        original_reference_marker_present=MARKER in data[start:end],
        Samsung_signature_verified=False, syscall_handler_identified=False, firmware_executed=False,
        plaintext_written=False, original_modified=False)
    if reference_dir is not None:
        report['reference_probe'] = reference_probe(data, reference_dir)
    if candidate_path is not None:
        with Path(candidate_path).open('rb') as stream:
            candidate = stream.read(SIZE + 1)
        report['supplied_candidate'] = candidate_result(data, candidate)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tzsw', help='exact received HZC2 tzsw.img')
    parser.add_argument('--probe-reference-dir', help='four pinned reference files; performs one hypothesis with two backends')
    parser.add_argument('--candidate', help='optional full image; read/validate only, never written')
    args = parser.parse_args()
    try:
        report = evidence(args.tzsw, reference_dir=args.probe_reference_dir, candidate_path=args.candidate)
        print(json.dumps(report, indent=2))
        if args.candidate is not None and not report['supplied_candidate']['accepted']:
            parser.exit(1)
    except (ValueError, OSError, KeyError, SyntaxError, struct.error, ImportError, subprocess.SubprocessError) as error:
        # Do not expose a subprocess command containing a per-image derived key.
        parser.exit(2, f'TZSW inspection failed: {type(error).__name__}\n')
