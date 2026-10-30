#!/usr/bin/env python3
"""Verify Build-id cache binding and refusal logic using host-only fixtures."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_build_id import add_immediate_x, build_id_binding, inspect, load_unsigned_w, page_plus_add


class DecoderTests(unittest.TestCase):
    def test_add_preserves_distinct_source_and_destination(self):
        self.assertEqual(add_immediate_x(0x91224060), (0, 3, 0x890))
        self.assertEqual(add_immediate_x(0x91400420), (0, 1, 4096))

    def test_add_rejects_other_width_flags_and_subtraction(self):
        for word in (0x11224060, 0xb1224060, 0xd1224060, -1, 0x191224060, True):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, 'ADD X'):
                add_immediate_x(word)

    def test_w_load_offsets_are_scaled_by_four(self):
        self.assertEqual(load_unsigned_w(0xb9470c21), (1, 1, 0x70c))
        self.assertEqual(load_unsigned_w(0xb97ffc20), (0, 1, 16380))

    def test_load_rejects_store_wrong_width_and_addressing_mode(self):
        for word in (0xf9470c21, 0xb9070c21, 0xb8404421, -1, 0x1b9470c21, True):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, 'LDR W'):
                load_unsigned_w(word)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.words = {0x17dec0: 0x90005c53, 0x17dec8: 0x91224273,
                      0x17ea48: 0xf0005c23, 0x17ea50: 0x91224060,
                      0x154bc4: 0xd0005c14, 0x154bd4: 0x910a8280,
                      0x17deec: 0x91004294,
                      0x17df08: 0xb0004961, 0x17df10: 0xb9470c21}

    def changed(self, pc, word):
        result = dict(self.words); result[pc] = word
        return result

    def test_selected_producer_consumer_and_reference_cache(self):
        result = build_id_binding(self.words)
        self.assertEqual(result['vbmeta_build_id_relative_address'], '0xd05890')
        self.assertEqual(result['selected_producer_relative_address'], '0xd05890')
        self.assertEqual(result['super_sign_info_cache_relative_address'], '0xcd62a0')
        self.assertEqual(result['super_build_id_offset'], 16)
        self.assertEqual(result['policy_word_relative_address'], '0xaaa70c')
        self.assertFalse(result['runtime_alias_preservation_and_freshness_established'])

    def test_page_plus_add_can_write_a_different_register(self):
        self.assertEqual(page_plus_add(self.words, 0x17ea48, 0x17ea50), (0, 0xd05890))

    def test_different_producer_address_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'addresses differ'):
            build_id_binding(self.changed(0x17ea50, self.words[0x17ea50]+0x1000))

    def test_add_source_must_match_page_register(self):
        with self.assertRaisesRegex(ValueError, 'ADD source'):
            build_id_binding(self.changed(0x17ea50, 0x91224080))

    def test_destination_registers_are_checked(self):
        for pc in (0x17dec8, 0x17ea50, 0x154bd4):
            with self.subTest(pc=hex(pc)), self.assertRaisesRegex(ValueError, 'address register'):
                build_id_binding(self.changed(pc, self.words[pc]^1))

    def test_reference_offset_must_remain_sixteen(self):
        with self.assertRaisesRegex(ValueError, 'displacement'):
            build_id_binding(self.changed(0x17deec, self.words[0x17deec]+0x400))

    def test_policy_load_must_keep_its_page_register(self):
        with self.assertRaisesRegex(ValueError, 'policy load'):
            build_id_binding(self.changed(0x17df10, self.words[0x17df10]^(1 << 5)))

    def test_policy_load_cannot_widen_to_u64(self):
        with self.assertRaisesRegex(ValueError, 'LDR W'):
            build_id_binding(self.changed(0x17df10, 0xf9470c21))


class ImageRefusalTests(unittest.TestCase):
    def test_unidentified_image_is_refused_before_disassembly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'
            for content in (b'not firmware', bytes(IMAGES['sboot'][0])):
                path.write_bytes(content)
                with self.subTest(size=len(content)), patch('inspect_lk_build_id.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError, 'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_error_produces_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'; path.write_bytes(b'bad')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('inspect_lk_build_id.py')), str(path)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
