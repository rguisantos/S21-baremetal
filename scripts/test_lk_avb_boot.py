#!/usr/bin/env python3
"""Test bounded immediate/reference decoding without proprietary firmware."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_avb_boot import direct_references, inspect, wide_constant


class WideImmediateTests(unittest.TestCase):
    def test_nonadjacent_wrapper_error_materialization(self):
        self.assertEqual(wide_constant([0x52880040, 0x72bfb540]), (0, 32, 0xfdaa4002))

    def test_smc_identifier_is_zero_extended_64_bit(self):
        self.assertEqual(wide_constant([0xd28203a0, 0xf2b84000]), (0, 64, 0xc200101d))

    def test_movn_uses_the_selected_register_width(self):
        self.assertEqual(wide_constant([0x12800013]), (19, 32, 0xffffffff))
        self.assertEqual(wide_constant([0x92800000]), (0, 64, 0xffffffffffffffff))
        self.assertEqual(wide_constant([0x12a00020]), (0, 32, 0xfffeffff))

    def test_high_halfword_and_low_halfword_are_preserved(self):
        self.assertEqual(wide_constant([0xd2e24682, 0xf29fffe2]), (2, 64, 0x123400000000ffff))

    def test_movk_replaces_existing_halfword(self):
        self.assertEqual(wide_constant([0x12800000, 0x72800000]), (0, 32, 0xffff0000))
        self.assertEqual(wide_constant([0x52800020, 0x72800040, 0x72800060]), (0, 32, 3))

    def test_empty_sequence_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'empty'):
            wide_constant([])

    def test_first_instruction_cannot_be_movk(self):
        with self.assertRaisesRegex(ValueError, 'start'):
            wide_constant([0x72800000])

    def test_wrong_register_width_and_operation_are_refused(self):
        for second in (0x72800001, 0xf2800000, 0x52800000, 0x12800000):
            with self.subTest(second=hex(second)), self.assertRaisesRegex(ValueError, 'differs'):
                wide_constant([0x52800000, second])

    def test_reserved_opcode_and_w32_high_shifts_are_refused(self):
        for word in (0x32800000, 0x52c00000, 0x52e00000):
            with self.subTest(word=hex(word)), self.assertRaisesRegex(ValueError, 'reserved'):
                wide_constant([word])

    def test_other_instructions_and_non_words_are_refused(self):
        for word in (0x2a0003e0, 0xd503201f, -1, 1 << 32, True, '52800000'):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, 'move-wide'):
                wide_constant([word])


class ReferenceTests(unittest.TestCase):
    def test_forward_bl_and_backward_b_are_found(self):
        data = struct.pack('<5I', 0x94000002, 0, 0, 0, 0x17fffffe)
        self.assertEqual(direct_references(data, 8, 0, len(data)),
                         [dict(pc='0x0', kind='bl'), dict(pc='0x10', kind='b')])

    def test_other_controls_are_not_mistaken_for_direct_calls(self):
        data = struct.pack('<5I', 0xd63f0000, 0x54000020, 0xd4000003, 0xf491f194, 0)
        self.assertEqual(direct_references(data, 8, 0, len(data)), [])

    def test_only_aligned_encodings_inside_scan_window_are_considered(self):
        data = bytearray(20)
        struct.pack_into('<I', data, 1, 0x94000002)
        self.assertEqual(direct_references(data, 8, 0, 20), [])
        struct.pack_into('<I', data, 0, 0x94000002)
        self.assertEqual(direct_references(data, 8, 4, 20), [])

    def test_direct_call_to_another_target_is_excluded(self):
        self.assertEqual(direct_references(struct.pack('<3I', 0x94000001, 0, 0), 8, 0, 12), [])

    def test_invalid_reference_bounds_and_target_are_refused(self):
        for target, low, high in ((-4, 0, 20), (20, 0, 20), (2, 0, 20),
                                  (8, -4, 20), (8, 1, 20), (8, 0, 19),
                                  (8, 0, 24), (8, 8, 8), (True, 0, 20)):
            with self.subTest(target=target, low=low, high=high), self.assertRaisesRegex(ValueError, 'bounds'):
                direct_references(bytes(20), target, low, high)


class RefusalTests(unittest.TestCase):
    def test_bad_image_is_refused_before_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'
            for content in (b'not firmware', bytes(IMAGES['sboot'][0])):
                path.write_bytes(content)
                with self.subTest(size=len(content)), patch('inspect_lk_avb_boot.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError, 'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_failure_has_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'; path.write_bytes(b'bad')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('inspect_lk_avb_boot.py')), str(path)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
