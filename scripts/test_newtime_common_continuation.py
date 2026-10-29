import unittest

from inspect_newtime_common_continuation_hzc2 import (
    allocation_request, choose_record, corrected_byte, pack_level, packed_field,
    secondary_address, signed32,
)


class AllocationWidthTests(unittest.TestCase):
    def test_signed_W_boundaries(self):
        self.assertEqual([signed32(i) for i in (0, 0x7fffffff, 0x80000000, 0xffffffff)],
                         [0, 0x7fffffff, -0x80000000, -1])

    def test_size_is_nonnegative_only_below_signed_wrap(self):
        self.assertTrue(allocation_request(0x1fffffff)['equals_nonnegative_logical_size'])
        self.assertEqual(allocation_request(0x20000000)['signed_request'], -0x80000000)
        self.assertFalse(allocation_request(0x20000000)['equals_nonnegative_logical_size'])

    def test_allocation_W_shift_wraps_before_SXTW(self):
        self.assertEqual(allocation_request(0x40000000)['request_W'], 0)
        self.assertFalse(allocation_request(0x40000000)['equals_nonnegative_logical_size'])

    def test_invalid_W_inputs_are_rejected(self):
        for x in (-1, 1 << 32, True, 1.5):
            with self.subTest(x=x), self.assertRaises(ValueError):
                allocation_request(x)


class PackedFieldTests(unittest.TestCase):
    def test_four_parts_are_two_words_little_endian_halves(self):
        fields = [packed_field(0, p, 0xabcd1234) for p in range(4)]
        self.assertEqual([f['result'] for f in fields], [0x1234, 0xabcd, 0x1234, 0xabcd])
        self.assertEqual([f['word_file'] for f in fields], [0x31b14, 0x31b14, 0x31b18, 0x31b18])

    def test_selected_domain_is_exact_24_word_interval(self):
        addresses = {packed_field(s, p, 0)['word_file'] for s in range(12) for p in range(4)}
        self.assertEqual(addresses, set(range(0x31b14, 0x31b74, 4)))

    def test_unbounded_default_selector_is_not_clamped(self):
        self.assertGreater(packed_field(12, 0, 0)['word_file'], 0x31b70)

    def test_selector_shift_and_add_wrap_as_W_values(self):
        self.assertEqual(packed_field(0x80000000, 0, 0)['word_index'], 0)
        self.assertEqual(packed_field(0x7fffffff, 4, 0)['word_index'], 0)

    def test_memory_word_is_supplied_by_host_not_inferred(self):
        self.assertEqual(packed_field(1, 1, 0xffff0000)['result'], 65535)
        with self.assertRaises(ValueError):
            packed_field(0, 0, 1 << 32)


class RecordSearchTests(unittest.TestCase):
    def test_first_matching_record_is_selected(self):
        self.assertEqual(choose_record([5, 9, 9], 9, 3)['index'], 1)

    def test_no_match_uses_first_record(self):
        result = choose_record([5, 9], 7, 2)
        self.assertEqual(result['index'], 0)
        self.assertEqual(result['reason'], 'fallback to first record')

    def test_zero_negative_count_records_zero_read_without_fault_claim(self):
        for n in (0, 0x80000000, 0xffffffff):
            result = choose_record([], 0, n)
            self.assertEqual(result['first_key_read_address'], 0)
            self.assertIsNone(result['index'])

    def test_fixture_length_guard_is_host_only(self):
        with self.assertRaises(ValueError):
            choose_record([1], 1, 2)


class ResultLayoutTests(unittest.TestCase):
    def test_byte_correction_threshold_and_signed_encoding(self):
        self.assertEqual([corrected_byte(0, c) for c in (0, 160, 161, 255)], [0, 160, 255, 161])

    def test_correction_store_truncates_to_byte(self):
        self.assertEqual(corrected_byte(0xffffffff, 1), 0)
        self.assertEqual(corrected_byte(100, 255), 5)

    def test_low_24_bits_preserve_high_byte_and_clear_low_three(self):
        self.assertEqual(pack_level(0xabffffff, 1), 0xab0003e8)
        self.assertEqual(pack_level(0x7f000000, 0), 0x7f000000)

    def test_multiply_W_wraps_before_low_24_mask(self):
        level = 0xffffffff
        self.assertEqual(pack_level(0xcd000000, level), 0xcdfffc18)

    def test_secondary_tag_guard_does_not_imply_nonzero_base(self):
        self.assertIsNone(secondary_address(0, 0, 255))
        self.assertEqual(secondary_address(0, 0, 0), 3)
        self.assertEqual(secondary_address(0, 2, 254), 11)

    def test_secondary_X_address_wraps(self):
        self.assertEqual(secondary_address(0xffffffffffffffff, 1, 0), 6)

    def test_invalid_bytes_and_addresses_are_rejected(self):
        for code in (-1, 256, True):
            with self.subTest(code=code), self.assertRaises(ValueError):
                corrected_byte(0, code)
        with self.assertRaises(ValueError):
            secondary_address(1 << 64, 0, 0)


if __name__ == '__main__':
    unittest.main()
