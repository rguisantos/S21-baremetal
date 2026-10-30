#!/usr/bin/env python3
"""Verify callback-slot decoding and refusals, without Samsung firmware."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_avb_trust import inspect, load_x, pair_store_x, resolve_bindings


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.words = {
            0x180de8: 0xb0005c21, 0x180df0: 0x91240021,
            0x180e78: 0xb0005c21, 0x180e7c: 0x91240021,
            0x180e18: 0x90000008, 0x180e3c: 0x91354108,
            0x180e20: 0xf0ffffe6, 0x180e40: 0x913f40c6,
            0x180e58: 0xa902a029, 0x180e5c: 0xa9049426,
            0x122870: 0xf9401b26, 0x122880: 0xd63f00c0,
            0x17f690: 0xf9402442, 0x17f694: 0xd63f0040,
        }

    def changed(self, pc, word):
        result = dict(self.words); result[pc] = word
        return result

    def test_installer_exporter_and_consumers_agree(self):
        result = resolve_bindings(self.words)
        self.assertEqual(result['ops_relative_address'], '0xd05900')
        self.assertEqual(result['exported_ops_relative_address'], '0xd05900')
        self.assertEqual(result['validate_key_slot'], 48)
        self.assertEqual(result['validate_key_target_file_offset'], '0x180d50')
        self.assertEqual(result['read_unlocked_slot'], 72)
        self.assertEqual(result['read_unlocked_target_file_offset'], '0x17ffd0')
        self.assertFalse(result['runtime_binding_and_preservation_established'])

    def test_pair_offsets_are_signed_and_scaled(self):
        self.assertEqual(pair_store_x(0xa902a029), (9, 8, 1, 40))
        self.assertEqual(pair_store_x(0xa93f8020), (0, 0, 1, -8))

    def test_pair_rejects_other_addressing_width_and_load(self):
        for word in (0xa882a029, 0xa982a029, 0x2902a029, 0xa942a029):
            with self.subTest(word=hex(word)), self.assertRaisesRegex(ValueError, 'STP X'):
                pair_store_x(word)

    def test_load_offsets_are_scaled_to_eight_bytes(self):
        self.assertEqual(load_x(0xf9401b26), (6, 25, 48))
        self.assertEqual(load_x(0xf97ffc20), (0, 1, 32760))

    def test_load_rejects_wrong_width_or_addressing(self):
        for word in (0xb9401b26, 0xf8408726, 0xf9001b26):
            with self.subTest(word=hex(word)), self.assertRaisesRegex(ValueError, 'LDR X'):
                load_x(word)

    def test_exporting_another_table_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exported ops'):
            resolve_bindings(self.changed(0x180e7c, 0x91244021))

    def test_add_with_wrong_source_register_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ADRP/ADD'):
            resolve_bindings(self.changed(0x180e3c, 0x91354128))

    def test_key_store_with_wrong_source_register_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'key-trust'):
            resolve_bindings(self.changed(0x180e58, 0xa902a429))

    def test_consumer_using_another_slot_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'key-trust'):
            resolve_bindings(self.changed(0x122870, 0xf9401f26))

    def test_indirect_call_register_must_match_load(self):
        with self.assertRaisesRegex(ValueError, 'key-trust'):
            resolve_bindings(self.changed(0x122880, 0xd63f00a0))

    def test_unlock_consumer_and_store_must_agree(self):
        for pc, word in ((0x17f690, 0xf9402842), (0x180e5c, 0xa9049427),
                         (0x17f694, 0xd63f0060)):
            with self.subTest(pc=hex(pc)), self.assertRaisesRegex(ValueError, 'read-unlocked'):
                resolve_bindings(self.changed(pc, word))

    def test_unidentified_image_refused_before_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'
            for content in (b'not firmware', bytes(IMAGES['sboot'][0])):
                path.write_bytes(content)
                with self.subTest(size=len(content)), patch('inspect_lk_avb_trust.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError, 'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_failure_has_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'; path.write_bytes(b'bad')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('inspect_lk_avb_trust.py')), str(path)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
