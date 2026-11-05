#!/usr/bin/env python3
"""Synthetic parent/stock/B controls, archive refusals and independent RSA."""
import ctypes as c
import hashlib
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import capture_a0_parent as parent
import check_capture_a0_parent as audit
from capture_a0_formats import align


def hash_descriptor(name, image, size=None, salt=b'parent-salt'):
    size = len(image) if size is None else size
    name = name.encode(); wanted = hashlib.sha256(salt+image[:size]).digest()
    d = bytearray(align(132+len(name+salt+wanted), 8))
    struct.pack_into('>3Q', d, 0, 2, len(d)-16, size); d[24:30] = b'sha256'
    struct.pack_into('>4I', d, 56, len(name), len(salt), 32, 0)
    d[132:132+len(name+salt+wanted)] = name+salt+wanted
    return bytes(d)


def chain_descriptor(name, key):
    name = name.encode(); d = bytearray(align(92+len(name+key), 8))
    struct.pack_into('>QQ4I', d, 0, 4, len(d)-16, 6, len(name), len(key), 0)
    d[92:92+len(name+key)] = name+key
    return bytes(d)


def archive(entries, compressed=False):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz' if compressed else 'w:') as t:
        for name, data in entries:
            info = tarfile.TarInfo(name); info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return output.getvalue()


def lz4(data):
    lib = c.CDLL('liblz4.so.1')
    lib.LZ4F_compressFrameBound.argtypes = [c.c_size_t, c.c_void_p]
    lib.LZ4F_compressFrameBound.restype = c.c_size_t
    lib.LZ4F_compressFrame.argtypes = [c.c_void_p, c.c_size_t, c.c_void_p, c.c_size_t, c.c_void_p]
    lib.LZ4F_compressFrame.restype = c.c_size_t
    output = c.create_string_buffer(lib.LZ4F_compressFrameBound(len(data), None))
    source = c.create_string_buffer(data)
    size = lib.LZ4F_compressFrame(output, len(output), source, len(data), None)
    if size > len(output): raise RuntimeError('fixture LZ4 failure')
    return output.raw[:size]


class ParentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Local only: unittest must not collect ContainerTests a second time.
        from test_capture_a0_container import ContainerTests
        class Fixtures(ContainerTests): pass
        Fixtures.setUpClass(); cls.addClassCleanup(Fixtures.doClassCleanups)
        cls.fixtures = Fixtures
        cls.stock = {'boot': Fixtures.original, 'vendor_boot': Fixtures.vendor_original}
        cls.modified = {name: b'X'+data[1:] for name, data in cls.stock.items()}
        cls.descriptors = [hash_descriptor(name, data) for name, data in cls.stock.items()]
        cls.original = cls.build()

    @classmethod
    def build(cls, descriptors=None, tail=b'SignerVer03-unvalidated-synthetic'):
        ds = b''.join(cls.descriptors if descriptors is None else descriptors)
        key = cls.fixtures.public[0]; aux = align(len(ds)+len(key), 64)
        h = bytearray(256); h[:4] = b'AVB0'
        struct.pack_into('>IIQQI', h, 4, 1, 0, 576, aux, 2)
        struct.pack_into('>10Q', h, 32, 0, 32, 32, 512, len(ds), len(key), len(ds)+len(key), 0, 0, len(ds))
        h[128:138] = b'test-only\0'
        auxiliary = ds+key+b'\0'*(aux-len(ds)-len(key)); signed = bytes(h)+auxiliary
        return bytes(h)+hashlib.sha256(signed).digest()+cls.fixtures.sign(signed, 0)+b'\0'*32+auxiliary+tail

    def mutate(self, offset, fmt, value):
        b = bytearray(self.original); struct.pack_into(fmt, b, offset, value); return bytes(b)

    def test_stock_positive_and_B_negative(self):
        r = parent.compare(self.original, self.stock, self.modified)
        self.assertTrue(r['stock_positive_controls_pass'])
        self.assertFalse(r['B_satisfies_unchanged_candidate_parent'])
        for row in r['comparisons'].values():
            self.assertTrue(row['variants']['stock']['matches_parent'])
            self.assertFalse(row['variants']['B']['matches_parent'])

    def test_unchanged_B_passes_file_comparison_without_trust(self):
        r = parent.compare(self.original, self.stock, self.stock)
        self.assertTrue(r['B_satisfies_unchanged_candidate_parent'])
        for k in ('installed_parent_identity_established','device_key_trust_established',
                'full_avb_chain_verified','samsung_acceptance_established','signer_ver03_validated',
                'a0_complete','a1_started','device_action_performed','physical_use_authorized'):
            self.assertFalse(r[k], k)

    def test_wrong_stock_refused_instead_of_concluding_B_incompatible(self):
        with self.assertRaisesRegex(ValueError, 'stock does not satisfy'):
            parent.compare(self.original, self.modified, self.modified)

    def test_missing_stock_or_B_control_refused(self):
        for stock, b in (({}, self.modified), (self.stock, {}),
                ({'boot': self.stock['boot']}, self.modified)):
            with self.subTest(stock=list(stock), B=list(b)), self.assertRaises(ValueError):
                parent.compare(self.original, stock, b)

    def test_hash_uses_parent_extent_not_child_footer(self):
        d = parent.parse_parent(self.build([hash_descriptor('boot', b'abcdef', 3)]))['descriptors'][0]
        self.assertEqual(parent.hash_image(d, b'abcXYZ'), hashlib.sha256(b'parent-saltabc').hexdigest())
        self.assertNotEqual(parent.hash_image(d, b'abXdef'), d['digest'])

    def test_salt_is_included(self):
        d = parent.parse_parent(self.original)['descriptors'][0]
        self.assertNotEqual(parent.hash_image(d, self.stock['boot']), hashlib.sha256(self.stock['boot']).hexdigest())

    def test_image_shorter_than_descriptor_refused(self):
        d = parent.parse_parent(self.original)['descriptors'][0]
        with self.assertRaises(ValueError): parent.hash_image(d, self.stock['boot'][:-1])

    def test_non_bytes_image_refused(self):
        d = parent.parse_parent(self.original)['descriptors'][0]
        with self.assertRaises(ValueError): parent.hash_image(d, bytearray(self.stock['boot']))

    def test_parent_signature_independently_verifies(self):
        self.assertTrue(parent.parse_parent(self.original)['rsa_signature_matches_embedded_key'])
        self.assertTrue(audit.native_auth(self.original, self.fixtures.openssl)['signature_matches_embedded_key'])

    def test_signature_corruption_fails_both_methods(self):
        b = bytearray(self.original); b[300] ^= 1; b = bytes(b)
        self.assertFalse(parent.parse_parent(b)['rsa_signature_matches_embedded_key'])
        self.assertFalse(audit.native_auth(b, self.fixtures.openssl)['signature_matches_embedded_key'])
        with self.assertRaisesRegex(ValueError, 'RSA'): parent.compare(b, self.stock, self.modified)

    def test_signed_digest_mutation_fails_RSA(self):
        b = bytearray(self.original); b[832+150] ^= 1
        self.assertFalse(parent.parse_parent(bytes(b))['rsa_signature_matches_embedded_key'])

    def test_unsigned_opaque_tail_never_claimed_validated(self):
        a = parent.parse_parent(self.original)
        b = parent.parse_parent(self.build(tail=b'other-tail'))
        self.assertTrue(b['rsa_signature_matches_embedded_key'])
        self.assertNotEqual(a['trailing_opaque']['sha256'], b['trailing_opaque']['sha256'])
        self.assertFalse(b['trailing_opaque']['validated'])

    def test_chain_is_distinguished_from_direct_hash(self):
        data = self.build(self.descriptors+[chain_descriptor('recovery', self.fixtures.public[1])])
        rows = parent.parse_parent(data)['descriptors']
        self.assertEqual(rows[-1]['tag'], 4)
        self.assertEqual(rows[-1]['partition'], 'recovery')
        self.assertEqual(rows[-1]['public_key_sha256'], parent.pin(self.fixtures.public[1])['sha256'])

    def test_property_and_cmdline_only_censused(self):
        opaque = [struct.pack('>QQ', tag, 8)+b'\0'*8 for tag in (0, 1)]
        rows = parent.parse_parent(self.build(self.descriptors+opaque))['descriptors']
        self.assertEqual([r['tag'] for r in rows], [2, 2, 0, 1])
        self.assertTrue(all(r['semantics_evaluated'] is False for r in rows[-2:]))

    def test_bad_magic_type_or_truncation_refused(self):
        for b in (b'', self.original[:200], b'NOPE'+self.original[4:], bytearray(self.original), self.original[:900]):
            with self.subTest(size=len(b)), self.assertRaises(ValueError): parent.parse_parent(b)

    def test_unsupported_header_layout_refused(self):
        for offset, fmt, value in ((4,'>I',2),(28,'>I',0),(32,'>Q',1),(64,'>Q',0),(80,'>Q',0),
                (104,'>Q',2**60),(120,'>I',1)):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                parent.parse_parent(self.mutate(offset, fmt, value))

    def test_reserved_auth_and_aux_padding_refused(self):
        extent = parent.parse_parent(self.original)['avb_structure_bytes']
        for offset in (176, 810, extent-1):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                parent.parse_parent(self.mutate(offset, '>B', 1))

    def test_unknown_or_overflowing_descriptor_refused(self):
        for offset, value in ((832, 99), (840, 2**63), (840, 1)):
            with self.subTest(offset=offset,value=value), self.assertRaises(ValueError):
                parent.parse_parent(self.mutate(offset, '>Q', value))

    def test_duplicate_hash_or_chain_partition_refused(self):
        for extra in (self.descriptors[0], chain_descriptor('boot', self.fixtures.public[0])):
            with self.assertRaisesRegex(ValueError, 'duplicate partition'):
                parent.parse_parent(self.build(self.descriptors+[extra]))

    def test_chain_cannot_substitute_for_required_direct_hash(self):
        data = self.build([self.descriptors[1], chain_descriptor('boot', self.fixtures.public[0])])
        with self.assertRaisesRegex(ValueError, 'direct parent hash missing'):
            parent.compare(data, self.stock, self.modified)

    def test_hash_fields_reserved_names_and_padding_refused(self):
        for offset, value in ((832+16,0),(832+24,0),(832+56,255),(832+60,255),
                (832+64,1),(832+68,1),(832+72,1),(832+132,ord('/'))):
            b = self.mutate(offset, '>B', value) if offset != 848 else self.mutate(offset, '>Q', value)
            with self.subTest(offset=offset), self.assertRaises(ValueError): parent.parse_parent(b)
        at = parent.parse_parent(self.original)['descriptors'][0]
        with self.assertRaises(ValueError):
            parent.parse_parent(self.mutate(at['offset']+at['bytes']-1, '>B', 1))

    def test_chain_reserved_and_key_length_refused(self):
        data = self.build(self.descriptors+[chain_descriptor('recovery', self.fixtures.public[0])])
        at = parent.parse_parent(data)['descriptors'][-1]['offset']
        for offset in (at+24, at+28, at+32):
            b = bytearray(data); struct.pack_into('>I', b, offset, 1)
            with self.subTest(offset=offset), self.assertRaises(ValueError): parent.parse_parent(bytes(b))

    def test_native_hash_uses_exact_same_extent_and_salt(self):
        d = parent.parse_parent(self.original)['descriptors'][0]
        self.assertEqual(audit.native_hash(d, self.stock['boot'], self.fixtures.openssl), d['digest'])

    def test_safe_archive_selection_and_full_set(self):
        b = archive([('a', b'one'), ('b', b'two')])
        self.assertEqual(audit.selected_members(b, {'a'}), {'a':b'one'})
        with self.assertRaises(ValueError): audit.selected_members(b, {'a'}, exact=True)

    def test_archive_duplicate_unselected_member_refused(self):
        with self.assertRaises(ValueError):
            audit.selected_members(archive([('a',b''),('x',b''),('x',b'')]), {'a'})

    def test_unsafe_archive_paths_refused(self):
        for name in ('/absolute','../up','a/../b','a\\b','./dot'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.selected_members(archive([(name,b'')]), {name})

    def test_missing_archive_member_refused(self):
        with self.assertRaises(ValueError): audit.selected_members(archive([('a',b'')]), {'b'})

    def test_archive_symlink_refused(self):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:') as t:
            m = tarfile.TarInfo('link'); m.type = tarfile.SYMTYPE; m.linkname = 'other'; t.addfile(m)
        with self.assertRaises(ValueError): audit.selected_members(output.getvalue(), {'link'})

    def test_lz4_exact_round_trip(self):
        data = b'A'*100000
        self.assertEqual(audit.lz4_frame(lz4(data), len(data)), data)

    def test_lz4_over_budget_invalid_and_truncated_refused(self):
        good = lz4(b'A'*100000)
        for packed, limit in ((good,99999),(good[:-3],100000),(b'not-lz4',100000),(good,0)):
            with self.subTest(limit=limit,size=len(packed)), self.assertRaises(ValueError): audit.lz4_frame(packed, limit)

    def test_lz4_trailing_and_concatenated_input_refused(self):
        good = lz4(b'A'*1000)
        for packed in (good+b'extra',good+good):
            with self.assertRaises(ValueError): audit.lz4_frame(packed, 3000)

    def test_full_pinned_archive_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp); refs = p/'refs'; refs.mkdir()
            packed = lz4(self.original); bl = archive([('vbmeta.img.lz4',packed)])+b'ignored-md5-trailer'
            (p/'BL.tar.md5').write_bytes(bl)
            raw = self.stock
            inputs = {'stock_raw':{},'stock_lz4':{}}
            for name, data in raw.items():
                zipped = lz4(data); (p/(name+'.img.lz4')).write_bytes(zipped)
                inputs['stock_raw'][name+'.img'] = parent.pin(data)
                inputs['stock_lz4'][name+'.img.lz4'] = parent.pin(zipped)
            # Keep Android header intact so the runner can identify child keys.
            modified = {n: b[:4096]+bytes([b[4096]^1])+b[4097:] for n,b in raw.items()}
            members = {n+'.img':b for n,b in modified.items()}; members.update({'report.json':b'{}','README.txt':b'lab'})
            mpins = {n:parent.pin(b) for n,b in members.items()}
            manifest = json.dumps({'files':mpins}).encode()
            bundle = archive(list(members.items())+[('manifest.json',manifest)], True); (p/'B.tar.gz').write_bytes(bundle)
            for name, obj in (
                    ('capture-a0-parent-pins-hzc2.json',dict(bl_archive=parent.pin(bl),parent_lz4=parent.pin(packed),parent_raw=parent.pin(self.original))),
                    ('capture-a0-pins-hzc2.json',inputs),
                    ('capture-a0-natural-b-artifact-20261104.json',dict(**parent.pin(bundle),payloads=mpins,manifest_sha256=parent.pin(manifest)['sha256']))):
                (refs/name).write_text(json.dumps(obj))
            with patch.object(audit,'REFERENCES',refs):
                r = audit.inspect(p/'BL.tar.md5', p, p/'B.tar.gz')
                self.assertTrue(r['stock_positive_controls_pass'])
                self.assertFalse(r['B_satisfies_unchanged_candidate_parent'])
                self.assertEqual(r['provenance']['prototype_payloads_verified'],4)
                for row in r['comparisons'].values():
                    self.assertTrue(all(v['openssl_matches_hashlib'] for v in row['variants'].values()))
                # A consumed input changed later is refused, not silently compared.
                (p/'boot.img.lz4').write_bytes(b'truncated')
                with self.assertRaisesRegex(ValueError,'identity differs'):
                    audit.inspect(p/'BL.tar.md5', p, p/'B.tar.gz')


if __name__ == '__main__': unittest.main()
