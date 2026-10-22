"""Independent LK reply scenarios and bounded LDFW container fixtures."""
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest

from inspect_sec_pgtbl_hzc2 import parse_ldfw_records, response_model


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


def container_fixture():
    """Two independently constructed page-sized records and a signer trailer."""
    data = bytearray(0x20a4)
    for offset, name, flag in ((0, b'fixture_fw', 1), (0x1000, b'tail_fw', 0)):
        struct.pack_into('<II', data, offset, 0x10adab1e, 0x1000)
        struct.pack_into('<I', data, offset + 0x28, flag)
        data[offset + 0x30:offset + 0x30 + len(name)] = name
    struct.pack_into('<II', data, 0x44, 0x150, 0x250)
    data[0x2000:0x200b] = b'SignerVer03'
    return data


class ContainerTests(unittest.TestCase):
    def test_walks_record_sizes_instead_of_scanning_for_magic(self):
        data = container_fixture()
        struct.pack_into('<I', data, 0x800, 0x10adab1e)
        result = parse_ldfw_records(data)
        self.assertEqual([r['name'] for r in result['records']], ['fixture_fw', 'tail_fw'])
        self.assertEqual(result['record_span_bytes'], 0x2000)
        self.assertEqual(result['signer_info_offset'], '0x2000')
        self.assertFalse(result['signature_verified'])
        region = result['records'][0]['encrypted_interval_by_related_format']
        # 0x48 is the EXCLUSIVE END from the related format, not its length.
        self.assertEqual(region['size'], 0x100)
        self.assertEqual(region['end_exclusive_file'], '0x250')
        self.assertIsNone(result['records'][1]['encrypted_interval_by_related_format'])

    def test_rejects_bad_sizes_and_truncation(self):
        for size in (0, 0x40, 0x1001, 0x3000):
            data = container_fixture()
            struct.pack_into('<I', data, 4, size)
            with self.subTest(size=size), self.assertRaises(ValueError):
                parse_ldfw_records(data)
        for length in (0, 0x20, 0x1000, 0x2000, 0x20a3):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parse_ldfw_records(container_fixture()[:length])

    def test_rejects_invalid_encrypted_intervals(self):
        for start, end in ((0x30, 0x250), (0x150, 0x150), (0x250, 0x150),
                           (0x151, 0x250), (0x150, 0x251), (0x150, 0x1010)):
            data = container_fixture()
            struct.pack_into('<II', data, 0x44, start, end)
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                parse_ldfw_records(data)

    def test_rejects_unknown_flags_names_and_missing_tail(self):
        for offset, value in ((0x28, 2), (0x30, 0), (0x30, 0xff), (0x1030, ord('x'))):
            data = container_fixture()
            data[offset] = value
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                parse_ldfw_records(data)
        data = container_fixture()
        data[0x1030:0x1040] = data[0x30:0x40]
        with self.assertRaises(ValueError):
            parse_ldfw_records(data)

    def test_rejects_record_after_tail_and_nonrecord_bytes(self):
        data = container_fixture()
        data[0x30:0x40], data[0x1030:0x1040] = data[0x1030:0x1040], data[0x30:0x40]
        with self.assertRaises(ValueError):
            parse_ldfw_records(data)
        data = container_fixture()
        data[0x1000] = 0
        with self.assertRaises(ValueError):
            parse_ldfw_records(data)

    def test_bounded_number_of_records(self):
        data = bytearray(33 * 0x1000 + 0xa4)
        for index in range(33):
            offset = index * 0x1000
            struct.pack_into('<II', data, offset, 0x10adab1e, 0x1000)
            name = f'fixture{index}'.encode()
            data[offset + 0x30:offset + 0x30 + len(name)] = name
        data[-0xa4:-0xa4 + 11] = b'SignerVer03'
        with self.assertRaises(ValueError):
            parse_ldfw_records(data)

    def test_emulator_rejects_foreign_firmware_before_loading_unicorn(self):
        from emulate_sec_pgtbl_hzc2 import emulate_caller
        with self.assertRaisesRegex(ValueError, 'exact HZC2'):
            emulate_caller(b'not the firmware', 0xe0000000, 0x1000)


if __name__ == '__main__':
    unittest.main()
