import unittest

from inspect_newtime_secondary_result_hzc2 import (
    adjusted_samples, apply_margin_pair, case_gate, metadata_write, record_span, result_word,
    route, selected_record,
)


class PathTests(unittest.TestCase):
    def test_zero_gates_return_original_for_two_selectors(self):
        self.assertEqual(route(2, 0)['return_kind'], 'original')
        self.assertEqual(route(3, 0)['return_kind'], 'original')

    def test_nonzero_gate_returns_allocated_result(self):
        self.assertEqual(route(2, 1)['return_kind'], 'allocated')
        self.assertEqual(route(3, 255)['return_kind'], 'allocated')

    def test_default_selectors_do_not_need_gate_pointer(self):
        for selector in (0, 1, 4, 0xffffffff):
            self.assertIsNone(route(selector)['metadata_offset'])

    def test_gate_offsets_and_metadata_fields_differ(self):
        self.assertEqual((route(2, 0)['gate_offset'], route(3, 0)['gate_offset']), (6, 7))
        self.assertEqual((route(2, 0)['metadata_offset'], route(3, 0)['metadata_offset']), (0x420, 0x422))

    def test_case_tag_and_gate_use_the_selected_bit(self):
        self.assertEqual((case_gate(2, 8), case_gate(3, 8)), (1, 0))
        self.assertEqual((case_gate(2, 4), case_gate(3, 4)), (0, 1))

    def test_selected_cases_never_publish_tag255(self):
        for selector in (2, 3):
            for source in range(256):
                tag = case_gate(selector, source)
                self.assertIn(tag, (0, 1))
                self.assertEqual(route(selector, tag)['return_kind'], 'original' if tag == 0 else 'allocated')


class SampleTests(unittest.TestCase):
    def test_selector3_uses_two_bytes_and_repeats_final_field(self):
        self.assertEqual(adjusted_samples(3, 0x90, 3, [10000, 20000, 30000, 40000]),
                         [3750, 7500, 11250, 21250])

    def test_selector2_repeats_top_two_bits_of_byte3(self):
        self.assertEqual(adjusted_samples(2, 0xff, 0x9c, [20000]*4), [1250, 13750, 7500, 7500])

    def test_subtraction_wraps_as_W(self):
        self.assertEqual(adjusted_samples(3, 0xff, 0xff, [0]*4), [0xffffb6c2]*4)

    def test_zero_fields_preserve_samples(self):
        self.assertEqual(adjusted_samples(2, 0, 0, [0, 1, 2, 0xffffffff]), [0, 1, 2, 0xffffffff])

    def test_bad_selector_or_sample_width_is_rejected(self):
        for selector, samples in ((0, [0]*4), (2, [0]*3), (3, [0, 0, 0, 1 << 32])):
            with self.subTest(selector=selector, samples=samples), self.assertRaises(ValueError):
                adjusted_samples(selector, 0, 0, samples)


class MetadataTests(unittest.TestCase):
    def test_destination_root_and_difference_root_are_distinct_inputs(self):
        result = metadata_write(2, 0, 0x1000, 0x3000, 0x13005, 0x16008)
        self.assertEqual(result, dict(address=0x1420, value=5, width=2))

    def test_extended_path_encodes_allocated_pointer(self):
        self.assertEqual(metadata_write(3, 1, 0x1000, 0x1000, 0x1010, 0x10042)['value'], 0xf042)

    def test_relative_difference_truncates_negative_and_high_bits(self):
        self.assertEqual(metadata_write(3, 0, 0, 0x1000, 0xfff, 0)['value'], 65535)

    def test_default_path_has_no_selected_metadata_store(self):
        self.assertIsNone(metadata_write(4, None, 0, 0, 0, 0))


class RecordTests(unittest.TestCase):
    def test_count_is_unsigned_and_multiply_is_64bit(self):
        self.assertEqual(record_span(0xffffffff), 206158430160)
        self.assertEqual(record_span(0x80000000), 103079215104)

    def test_first_match_wins(self):
        self.assertEqual(selected_record([1, 5, 5], 5, 3)['index'], 1)

    def test_no_match_retains_last_not_first_record(self):
        self.assertEqual(selected_record([1, 5, 9], 7, 3)['index'], 2)

    def test_zero_count_defers_zero_read_to_nonempty_level_loop(self):
        self.assertTrue(selected_record([], 0, 0)['zero_key_read_if_n_positive'])


class OutputAndAliasTests(unittest.TestCase):
    def test_final_word_combines_corrected_byte_and_low24(self):
        self.assertEqual(result_word(1, 100, 255), 0x050003e8)
        self.assertEqual(result_word(1, 100), 0x640003e8)

    def test_exact_alias_gets_two_ordered_additions(self):
        self.assertEqual(apply_margin_pair(10, 10, 3, 0, True),
                         dict(primary=16, secondary=16, stores=2))

    def test_disjoint_buffers_each_receive_one_addition(self):
        self.assertEqual(apply_margin_pair(10, 20, 3, 0, False),
                         dict(primary=13, secondary=23, stores=2))

    def test_tag255_skips_second_store_but_alias_view_tracks_first(self):
        self.assertEqual(apply_margin_pair(10, 10, 3, 255, True),
                         dict(primary=13, secondary=13, stores=1))

    def test_double_addition_wraps_in_byte(self):
        self.assertEqual(apply_margin_pair(250, 250, 10, 0, True)['primary'], 14)

    def test_inconsistent_alias_fixture_is_refused(self):
        with self.assertRaises(ValueError):
            apply_margin_pair(10, 20, 3, 0, True)


if __name__ == '__main__':
    unittest.main()
