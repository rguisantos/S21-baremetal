#!/usr/bin/env python3
"""Hash coverage and metadata movement controls, without private firmware."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import capture_a0_formats as fmt
import check_capture_a0_repack as audit
from test_capture_a0 import boot, signed_container


class ExtentTests(unittest.TestCase):
    def test_footer_is_outside_descriptor_extent(self):
        data = signed_container(); result = audit.changed_regions(data, data)
        self.assertLess(result['original_hash_extent'][1], result['original_footer_extent'][0])
        self.assertFalse(result['footer_inside_original_hash'])
        self.assertTrue(result['no_change_gate_passed'])
        self.assertFalse(result['signature_verified'])

    def test_extension_mutation_invalidates_payload_hash(self):
        before = signed_container(); after = bytearray(before); after[len(boot())] ^= 1
        result = audit.changed_regions(before, bytes(after))
        self.assertTrue(result['header_and_payloads_identical'])
        self.assertEqual(result['changed_inside_original_hash'], 1)
        self.assertEqual(result['changed_outside_original_hash'], 0)
        self.assertFalse(result['repacked_avb']['hash_descriptors'][0]['matches'])

    def test_footer_geometry_change_preserves_digest_but_fails_gate(self):
        before = signed_container(); after = bytearray(before)
        end = fmt.avb(before)['original_image_size']
        struct.pack_into('>Q', after, len(after)-64+12, end+1)
        result = audit.changed_regions(before, bytes(after))
        self.assertEqual(result['original_hash_extent'], [0, end])
        self.assertEqual(result['changed_inside_original_hash'], 0)
        self.assertEqual(result['changed_outside_original_hash'], 1)
        self.assertTrue(result['repacked_avb']['hash_descriptors'][0]['matches'])
        self.assertFalse(result['repacked_avb']['all_hashes_match'])
        self.assertFalse(result['no_change_gate_passed'])

    def test_unsigned_padding_change_is_not_hash_change(self):
        before = signed_container(); after = bytearray(before)
        after[fmt.avb(before)['original_image_size']+1] ^= 1
        result = audit.changed_regions(before, bytes(after))
        self.assertEqual(result['changed_inside_original_hash'], 0)
        self.assertEqual(result['changed_outside_original_hash'], 1)
        self.assertTrue(result['repacked_avb']['all_hashes_match'])
        self.assertFalse(result['no_change_gate_passed'])

    def test_moved_vbmeta_overwrites_old_hashed_extension(self):
        before = signed_container(); after = bytearray(before); av = fmt.avb(before)
        offset, size, body = av['offset'], av['bytes'], len(boot())
        after[body:body+size] = before[offset:offset+size]
        after[offset:offset+size] = b'\0'*size
        struct.pack_into('>QQ', after, len(after)-64+12, body, body)
        result = audit.changed_regions(before, bytes(after))
        self.assertTrue(result['header_and_payloads_identical'])
        self.assertTrue(result['vbmeta_blob_identical'])
        self.assertEqual(result['repacked_vbmeta_overlap_original_hash'], av['original_image_size']-body)
        self.assertFalse(result['repacked_avb']['hash_descriptors'][0]['matches'])

    def test_android_header_change_is_distinguished(self):
        before = signed_container(); after = bytearray(before); after[16] ^= 1
        result = audit.changed_regions(before, bytes(after))
        self.assertFalse(result['header_and_payloads_identical'])
        self.assertEqual(result['regions_in_original_coordinates'][0]['changed_bytes'], 1)

    def test_partition_resize_refused(self):
        before = signed_container()
        with self.assertRaises(ValueError): audit.changed_regions(before, before+b'\0')

    def test_invalid_original_digest_refused(self):
        data = bytearray(signed_container()); data[4096] ^= 1
        with self.assertRaises(ValueError): audit.changed_regions(bytes(data), bytes(data))

    def test_missing_footer_refused(self):
        before = signed_container(); after = bytearray(before); after[-64:] = b'\0'*64
        with self.assertRaises(ValueError): audit.changed_regions(before, bytes(after))

    def test_ambiguous_multiple_descriptors_refused(self):
        old = signed_container(); av = fmt.avb(old); offset = av['offset']
        header = bytearray(old[offset:offset+256]); desc = old[offset+256:offset+av['bytes']]
        struct.pack_into('>Q', header, 20, 2*len(desc))
        struct.pack_into('>Q', header, 104, 2*len(desc))
        meta = header+desc+desc
        data = bytearray(65536); data[:offset] = old[:offset]
        data[offset:offset+len(meta)] = meta; data[-64:] = old[-64:]
        struct.pack_into('>Q', data, len(data)-64+28, len(meta))
        self.assertTrue(fmt.avb(bytes(data))['all_hashes_match'])
        with self.assertRaises(ValueError): audit.changed_regions(bytes(data), bytes(data))


class InputTests(unittest.TestCase):
    def test_unverified_binary_never_executed(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'run_tool') as run:
            root = Path(temp); binary = root/'tool'; binary.write_bytes(b'bad')
            with self.assertRaises(ValueError): audit.inspect(root, binary, root/'out')
            run.assert_not_called(); self.assertFalse((root/'out').exists())

    def test_stock_hashes_checked_before_execution(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'run_tool') as run:
            root = Path(temp); binary = root/'tool'; binary.write_bytes(b'fixture')
            stock = root/'boot.img.lz4'; stock.write_bytes(b'bad')
            pins = root/'pins.json'; pins.write_text(json.dumps(dict(
                magisk=dict(host_binary=dict(bytes=7, sha256=fmt.digest(b'fixture'))),
                stock_lz4={'boot.img.lz4':dict(bytes=3, sha256='0'*64)})))
            with patch.object(audit, 'PINS', pins), self.assertRaises(ValueError):
                audit.inspect(root, binary, root/'out')
            run.assert_not_called(); self.assertFalse((root/'out').exists())


if __name__ == '__main__':
    unittest.main()
