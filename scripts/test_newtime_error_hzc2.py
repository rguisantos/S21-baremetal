"""Boundaries of the dump reader and the original W-width error flag update."""
import unittest

from inspect_newtime_error_hzc2 import dump_plan, error_flags


class ErrorTests(unittest.TestCase):
    def test_actual_header_dump_stops_before_directory(self):
        result = dump_plan(0x02073600, 0x1a0)
        self.assertTrue(result['finite'])
        self.assertEqual((result['word_count'], result['first_read'], result['read_end']),
                         (104, 0x02073600, 0x020737a0))

    def test_whole_words_are_loaded_even_for_short_requests(self):
        self.assertEqual(dump_plan(0x1000, 1)['read_end'], 0x1004)
        self.assertEqual(dump_plan(0x1000, 17)['read_end'], 0x1014)

    def test_unaligned_zero_request_can_still_load_blanked_words(self):
        self.assertEqual(dump_plan(0x1000, 0)['word_count'], 0)
        result = dump_plan(0x100f, 0)
        self.assertEqual((result['first_read'], result['read_end'], result['word_count']),
                         (0x1000, 0x1010, 4))

    def test_w_limit_addition_wraps_before_comparison(self):
        self.assertEqual(dump_plan(0x1003, 0xfffffffd)['word_count'], 0)
        self.assertEqual(dump_plan(0x1003, 0xffffffff)['word_count'], 1)

    def test_w_counter_wrap_prevents_termination_for_top_three_limits(self):
        finite = dump_plan(0, 0xfffffffc)
        self.assertTrue(finite['finite'])
        self.assertEqual(finite['last_read'], 0xfffffff8)
        for limit in (0xfffffffd, 0xfffffffe, 0xffffffff):
            result = dump_plan(0, limit)
            self.assertFalse(result['finite'])
            self.assertIsNone(result['word_count'])
            self.assertEqual(result['cycle_word_count'], 1 << 30)

    def test_effective_ldr_address_uses_64_bit_base_plus_index(self):
        result = dump_plan(0xfffffff0, 32)
        self.assertEqual(result['last_read'], 0x10000000c)

    def test_error_flag_preserves_existing_bits_and_repeated_updates(self):
        self.assertEqual(error_flags(0x12345678, 27), 0x1a345678)
        self.assertEqual(error_flags(0, 5), 0x20)
        self.assertEqual(error_flags(0x08000000, 27), 0x08000000)

    def test_variable_shift_masks_argument_to_five_bits(self):
        self.assertEqual(error_flags(0, 32), 1)
        self.assertEqual(error_flags(0, 33), 2)
        self.assertEqual(error_flags(0, 0xffffffff), 0x80000000)

    def test_inputs_are_strict_unsigned_w_values(self):
        for value in (True, -1, 1 << 32, '1'):
            for operation in (lambda: dump_plan(value, 0), lambda: dump_plan(0, value),
                              lambda: error_flags(value, 0), lambda: error_flags(0, value)):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    operation()


if __name__ == '__main__':
    unittest.main()
