#!/usr/bin/env python3
"""Real synthetic RSA controls and refusals; no private firmware or network."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import capture_a0_container as pack
import capture_a0_formats as fmt
import check_capture_a0_container as audit
from test_capture_a0 import boot, vendor


class ContainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.openssl = shutil.which('openssl')
        if cls.openssl is None: raise RuntimeError('These RSA controls require openssl')
        cls.keys = []; cls.public = []
        for index in range(2):
            key = cls.root/('synthetic-%d.pem' % index)
            subprocess.run([cls.openssl, 'genrsa', '-out', str(key), '4096'], check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            modulus = subprocess.check_output([cls.openssl, 'rsa', '-in', str(key), '-modulus', '-noout'], stderr=subprocess.DEVNULL)
            n = int(modulus.decode().strip().split('=')[1], 16)
            encoded = struct.pack('>II', 4096, (-pow(n, -1, 2**32)) % 2**32)
            encoded += n.to_bytes(512, 'big')+pow(2, 8192, n).to_bytes(512, 'big')
            cls.keys.append(key); cls.public.append(encoded)
        cls.original = cls.fixture(boot(), 'boot')
        cls.vendor_original = cls.fixture(vendor(), 'vendor_boot')

    @classmethod
    def sign(cls, data, index=1):
        return subprocess.check_output([cls.openssl, 'dgst', '-sha256', '-sign', str(cls.keys[index])], input=data)

    @classmethod
    def fixture(cls, body, partition):
        prefix = body+b'SignerVer03-synthetic-opaque'
        salt = b'fixed-salt'; name = partition.encode(); wanted = hashlib.sha256(salt+prefix).digest()
        desc = bytearray(fmt.align(132+len(name)+len(salt)+32, 8))
        struct.pack_into('>3Q', desc, 0, 2, len(desc)-16, len(prefix))
        desc[24:30] = b'sha256'
        struct.pack_into('>4I', desc, 56, len(name), len(salt), 32, 0)
        desc[132:132+len(name+salt+wanted)] = name+salt+wanted
        auth = 576; aux = fmt.align(len(desc)+1032, 64)
        header = bytearray(256); header[:4] = b'AVB0'
        struct.pack_into('>IIQQI', header, 4, 1, 0, auth, aux, 2)
        struct.pack_into('>10Q', header, 32, 0, 32, 32, 512, len(desc), 1032, len(desc)+1032, 0, 0, len(desc))
        header[128:138] = b'test-only\0'
        auxiliary = bytes(desc)+cls.public[0]+b'\0'*(aux-len(desc)-1032)
        signed = bytes(header)+auxiliary
        meta = bytes(header)+hashlib.sha256(signed).digest()+cls.sign(signed, 0)+b'\0'*32+auxiliary
        offset = fmt.align(len(prefix), 4096); data = bytearray(offset+len(meta)+128)
        data[:len(prefix)] = prefix; data[offset:offset+len(meta)] = meta
        struct.pack_into('>4sIIQQQ', data, len(data)-64, b'AVBf', 1, 0, len(prefix), offset, len(meta))
        return bytes(data)

    def staged(self, original=None, name='kernel'):
        original = self.original if original is None else original
        row = next(p for p in fmt.layout(original)['parts'] if p['name'] == name)
        payload = bytearray(original[row['start']:row['end']]); payload[-1] ^= 1
        return pack.stage(original, {name: bytes(payload)})

    def test_no_change_is_byte_identical_and_authenticated(self):
        out = pack.stage(self.original, {})
        self.assertEqual(out, self.original)
        r = pack.result(self.original, out)
        self.assertTrue(r['hash_descriptors_match']); self.assertTrue(r['rsa_signature_matches_embedded_key'])
        self.assertFalse(r['key_trust_established'])

    def test_explicit_same_payload_is_identity(self):
        self.assertEqual(pack.stage(self.original, {'kernel': self.original[4096:4160]}), self.original)

    def test_staging_breaks_payload_digest_but_preserves_vbmeta_signature(self):
        r = pack.result(self.original, self.staged())
        self.assertFalse(r['hash_descriptors_match']); self.assertTrue(r['rsa_signature_matches_embedded_key'])

    def test_hash_only_repairs_digest_and_breaks_authentication(self):
        r = pack.result(self.original, pack.rehash(self.original, self.staged()))
        self.assertTrue(r['hash_descriptors_match']); self.assertFalse(r['rsa_signature_matches_embedded_key'])

    def test_lab_signature_matches_while_trust_remains_unproved(self):
        out = pack.seal_lab(self.original, self.staged(), self.public[1], self.sign)
        r = pack.result(self.original, out)
        for field in ('hash_descriptors_match', 'rsa_signature_matches_embedded_key', 'embedded_key_changed',
                'android_header_and_non_vbmeta_non_payload_bytes_preserved', 'avb_header_preserved', 'footer_preserved'):
            self.assertTrue(r[field], field)
        self.assertEqual(r['original_hash_extent'], r['output_hash_extent'])
        for field in ('key_trust_established', 'samsung_signature_validated', 'payload_semantics_validated', 'physical_acceptance_established'):
            self.assertFalse(r[field], field)

    def test_vendor_can_replace_both_declared_payloads(self):
        before = self.vendor_original
        after = pack.stage(before, {'ramdisk': b'Q'*16, 'dtb': b'F'*40})
        out = pack.seal_lab(before, after, self.public[1], self.sign)
        self.assertTrue(pack.result(before, out)['hash_descriptors_match'])

    def test_only_digest_key_and_authentication_change_inside_vbmeta(self):
        p = pack.describe(self.original)
        out = pack.seal_lab(self.original, self.staged(), self.public[1], self.sign)
        q = pack.describe(out)
        mutable = [(256, 800), (p['digest_offset'], p['digest_offset']+32),
            (p['key_offset'], p['key_offset']+1032)]
        for index, (old, new) in enumerate(zip(p['meta'], q['meta'])):
            if not any(start <= index < end for start, end in mutable):
                self.assertEqual(old, new, index)

    def test_repeated_signing_is_deterministic_for_same_key(self):
        staged = self.staged()
        self.assertEqual(pack.seal_lab(self.original, staged, self.public[1], self.sign),
            pack.seal_lab(self.original, staged, self.public[1], self.sign))

    def test_payload_resize_is_refused(self):
        for size in (0, 63, 65):
            with self.subTest(size=size), self.assertRaises(ValueError):
                pack.stage(self.original, {'kernel': b'X'*size})

    def test_unknown_header_or_absent_payload_replacement_is_refused(self):
        for name in ('header', 'avb_footer', 'opaque_extension', 'ramdisk', 'missing'):
            with self.subTest(name=name), self.assertRaises(ValueError):pack.stage(self.original, {name: b''})

    def test_non_bytes_replacement_is_refused(self):
        with self.assertRaises(ValueError): pack.stage(self.original, {'kernel': bytearray(64)})

    def test_changed_android_header_is_refused_before_signing(self):
        data = bytearray(self.staged()); data[16] ^= 1; sign = Mock()
        with self.assertRaises(ValueError):pack.seal_lab(self.original, bytes(data), self.public[1], sign)
        sign.assert_not_called()

    def test_changed_opaque_extension_is_refused(self):
        data = bytearray(self.staged()); data[len(boot())] ^= 1
        with self.assertRaises(ValueError):pack.rehash(self.original, bytes(data))

    def test_changed_footer_or_metadata_is_refused(self):
        for offset in (-1, fmt.avb(self.original)['offset']+128):
            data = bytearray(self.staged()); data[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):pack.rehash(self.original, bytes(data))

    def test_input_with_invalid_payload_hash_is_not_a_template(self):
        with self.assertRaises(ValueError):pack.stage(self.staged(), {})

    def test_input_with_invalid_rsa_is_not_a_template(self):
        data = bytearray(self.original); data[fmt.avb(self.original)['offset']+300] ^= 1
        with self.assertRaises(ValueError):pack.stage(bytes(data), {})

    def test_unsigned_or_different_auth_layout_is_refused(self):
        offset = fmt.avb(self.original)['offset']
        for field, value in ((28, 0), (32, 1), (72, 1024)):
            data = bytearray(self.original)
            struct.pack_into('>I' if field == 28 else '>Q', data, offset+field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):pack.describe(bytes(data))

    def test_extra_descriptor_is_refused(self):
        data = bytearray(self.original); offset = fmt.avb(self.original)['offset']
        ds = struct.unpack_from('>Q', data, offset+104)[0]
        struct.pack_into('>Q', data, offset+256+576+8, ds-24)
        with self.assertRaises(ValueError):pack.describe(bytes(data))

    def test_wrong_partition_name_is_refused(self):
        data = bytearray(self.original); p = pack.describe(self.original)
        data[p['inventory']['avb']['offset']+p['descriptor']+132] ^= 1
        with self.assertRaises(ValueError):pack.describe(bytes(data))

    def test_invalid_montgomery_key_is_refused_before_signing(self):
        data = bytearray(self.public[1]); data[4] ^= 1; sign = Mock()
        with self.assertRaises(ValueError):pack.seal_lab(self.original, self.staged(), bytes(data), sign)
        sign.assert_not_called()

    def test_wrong_key_length_or_template_key_is_refused(self):
        for key in (self.public[1][:-1], self.public[0]):
            with self.subTest(size=len(key)), self.assertRaises(ValueError):
                pack.seal_lab(self.original, self.staged(), key, Mock())

    def test_bad_signature_size_or_value_is_refused(self):
        for sig in (b'', b'X'*511, b'X'*512):
            with self.subTest(size=len(sig)), self.assertRaises(ValueError):
                pack.seal_lab(self.original, self.staged(), self.public[1], lambda data: sig)

    def test_signature_from_other_key_is_refused(self):
        with self.assertRaises(ValueError):
            pack.seal_lab(self.original, self.staged(), self.public[1], lambda data: self.sign(data, 0))

    def test_signature_equal_to_modulus_is_refused(self):
        with self.assertRaises(ValueError):
            pack.seal_lab(self.original, self.staged(), self.public[1], lambda data: self.public[1][8:520])

    def test_tampering_after_sealing_breaks_payload_hash(self):
        out = bytearray(pack.seal_lab(self.original, self.staged(), self.public[1], self.sign)); out[4096] ^= 1
        r = pack.result(self.original, bytes(out))
        self.assertFalse(r['hash_descriptors_match']); self.assertTrue(r['rsa_signature_matches_embedded_key'])

    def test_raw_or_truncated_partition_is_refused(self):
        for data in (boot(), self.original[:-1], self.original+b'\0'):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):pack.stage(data, {})


class RunnerRefusalTests(unittest.TestCase):
    def test_unpinned_avbtool_prevents_output_and_native_execution(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'native') as run:
            root = Path(temp); tool = root/'avbtool.py'; tool.write_bytes(b'bad')
            with self.assertRaises(ValueError):audit.inspect(root, tool, root/'key', root/'out')
            run.assert_not_called(); self.assertFalse((root/'out').exists())

    def test_existing_output_is_refused(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'native') as run:
            root = Path(temp)
            with self.assertRaises(ValueError):audit.inspect(root, root/'tool', root/'key', root)
            run.assert_not_called()

    def test_wrong_key_or_stock_prevents_execution(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'native') as run:
            root = Path(temp); tool = root/'tool'; key = root/'key'; tool.write_bytes(b'tool'); key.write_bytes(b'key')
            tools = root/'tools.json'
            for bad_key in (True, False):
                tools.write_text(json.dumps(dict(avbtool=dict(bytes=4, sha256=fmt.digest(b'tool')),
                    public_test_key=dict(bytes=3, sha256='0'*64 if bad_key else fmt.digest(b'key')))))
                (root/'boot.img').write_bytes(b'bad')
                with self.subTest(bad_key=bad_key), patch.object(audit, 'TOOL_PINS', tools), self.assertRaises(ValueError):
                    audit.inspect(root, tool, key, root/'out')
                run.assert_not_called(); self.assertFalse((root/'out').exists())


if __name__ == '__main__': unittest.main()
