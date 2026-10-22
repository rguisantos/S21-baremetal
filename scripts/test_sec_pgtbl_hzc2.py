"""Independent register scenarios for the traced LK SEC_PGTBL result handling."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from inspect_sec_pgtbl_hzc2 import response_model


class ReplyTests(unittest.TestCase):
    def test_aligned_scenario_preserves_values_but_does_not_verify_memory(self):
        result = response_model(0xe0000000, 0x200000)
        self.assertEqual(result['lk']['normalized_base'], '0xe0000000')
        self.assertEqual(result['lk']['x27_end_wrapped64'], '0xe0200000')
        self.assertEqual(result['lk']['w22_split_flag'], 1)
        self.assertTrue(result['host_arithmetic_guard']['passes'])
        self.assertFalse(result['memory_map_verified'])
        self.assertFalse(result['range_is_free'])
        self.assertFalse(result['runtime_observed'])

    def test_base_sentinels_and_unaligned_base_disable_split(self):
        for base, status in ((0, 'invalid_type'), (3, 'unsupported'),
                             (0xffffffffffffffff, 'ldfw_not_initialized'),
                             (0xffffffff, 'base_unaligned'),
                             (0xe0001000, 'base_unaligned')):
            result = response_model(base, 0x200000)['lk']
            self.assertEqual(result['normalized_base'], '0x0')
            self.assertEqual(result['base_status'], status)
            self.assertEqual(result['w22_split_flag'], 0)
        # Base comparisons use X0: 0x100000000 is not the zero sentinel.
        self.assertEqual(response_model(0x100000000, 0x200000)['lk']['w22_split_flag'], 1)

    def test_size_sentinels_use_only_low_32_bits(self):
        for low, status in ((0, 'invalid_type'), (3, 'unsupported'),
                            (0xffffffff, 'ldfw_not_initialized')):
            for high in (0, 0x12345678):
                result = response_model(0xe0000000, (high << 32) | low)['lk']
                self.assertEqual(result['size_status'], status)
                self.assertEqual(result['size_low32'], '0x0')
                self.assertEqual(result['w22_split_flag'], 0)

    def test_unaligned_size_is_kept_by_lk_and_rejected_by_host_guard(self):
        for size in (1, 0x1000, 0x180000):
            result = response_model(0xe0000000, size)
            self.assertEqual(result['lk']['size_low32'], hex(size))
            self.assertEqual(result['lk']['w22_split_flag'], 1)
            self.assertFalse(result['lk']['size_alignment_was_checked'])
            self.assertFalse(result['host_arithmetic_guard']['passes'])

    def test_size_upper_bits_are_ignored_and_end_can_wrap(self):
        result = response_model(0xe0000000, 0x1234567800200000)
        self.assertEqual(result['lk']['size_low32'], '0x200000')
        self.assertEqual(result['lk']['size_reply_upper32_ignored'], '0x12345678')
        result = response_model(0xfffffffffff00000, 0x200000)
        self.assertEqual(result['lk']['x27_end_wrapped64'], '0x100000')
        self.assertTrue(result['lk']['x27_addition_overflows'])
        self.assertEqual(result['lk']['w22_split_flag'], 1)
        self.assertFalse(result['host_arithmetic_guard']['passes'])

    def test_replies_must_be_raw_unsigned_64_bit_integers(self):
        for value in (-1, 1 << 64, True, 0.5, '0xe0000000'):
            for args in ((value, 0x200000), (0xe0000000, value)):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    response_model(*args)

    def test_cli_refuses_wrong_image_without_scenario_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wrong.bin'
            path.write_bytes(b'not the firmware')
            script = Path(__file__).with_name('inspect_sec_pgtbl_hzc2.py')
            result = subprocess.run([sys.executable, str(script), str(path), str(path),
                                     '--base-result', '0xe0000000', '--size-result', '0x1000'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
