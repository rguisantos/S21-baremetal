import struct
import unittest

from inspect_newtime_margin_hzc2 import (
    bump_step, case_filter, lookup_record, margin_index, name_skip, parse_margin,
    record_layout, record_request,
)


def one_record():
    return (struct.pack('<I4sI', 2, b'0.0 ', 1) + struct.pack('<I', 3) + b'MIF\0'
            + struct.pack('<III', 24, 2, 2) + bytes([6, 4, 4, 4]))


class WidthTests(unittest.TestCase):
    def test_skip_counts_nul_and_aligned_payload(self):
        self.assertEqual([name_skip(n) for n in (0, 3, 4, 7, 8)], [4, 4, 8, 8, 12])

    def test_skip_wraps_before_X_add(self):
        self.assertEqual(name_skip(0xfffffffb), 0xfffffffc)
        for n in (0xfffffffc, 0xfffffffd, 0xfffffffe, 0xffffffff):
            self.assertEqual(name_skip(n), 0)

    def test_bump_wraps_at_64_not_32_bits(self):
        self.assertEqual(bump_step(0xfffffffffffffffc, 4), (0xfffffffffffffffc, 0))
        self.assertEqual(bump_step(0x1000, 0xffffffd0), (0x1000, 0x100000fd0))

    def test_zero_return_does_not_imply_cursor_unmodified(self):
        self.assertEqual(bump_step(0, 24), (0, 24))

    def test_record_multiply_wraps_at_W_width(self):
        self.assertEqual(record_request(0x05555556), 0x20)
        self.assertEqual(record_request(0xffffffff), 0xffffffd0)

    def test_invalid_typed_inputs_are_refused(self):
        for value in (-1, 1 << 32, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                name_skip(value)
        with self.assertRaises(ValueError):
            bump_step(1 << 64, 0)


class LookupTests(unittest.TestCase):
    def test_positive_count_bounds_search_even_with_extra_fixture_records(self):
        self.assertIsNone(lookup_record(1, [b'A', b'B'], b'B'))
        self.assertEqual(lookup_record(2, [b'A', b'B'], b'B'), 1)

    def test_signed_nonpositive_count_skips_records(self):
        for count in (0, 0xffffffff, 0x80000000):
            self.assertIsNone(lookup_record(count, [b'MIF'], b'MIF'))

    def test_lookup_is_not_prefix_matching(self):
        self.assertIsNone(lookup_record(1, [b'INTSCI'], b'INT'))

    def test_NUL_terminates_C_name(self):
        self.assertEqual(lookup_record(1, [b'MIF\0ignored'], b'MIF\0tail'), 0)

    def test_missing_host_records_are_not_silently_skipped(self):
        with self.assertRaises(ValueError):
            lookup_record(2, [b'MIF'], b'MIF')

    def test_null_object_or_name_returns_none(self):
        self.assertIsNone(lookup_record(1, None, b'MIF'))
        self.assertIsNone(lookup_record(1, [b'MIF'], None))


class PayloadTests(unittest.TestCase):
    def test_version2_record_shape_and_bytes(self):
        obj = parse_margin(one_record())
        row = obj['records'][0]
        self.assertEqual((obj['version'], obj['count']), (2, 1))
        self.assertEqual((row['name'], row['columns'], row['rows']), ('MIF', 2, 2))
        self.assertEqual(row['data_hex'], '06040404')
        self.assertEqual((row['data_offset'], row['end']), (32, 36))

    def test_four_character_name_needs_eight_payload_bytes(self):
        block = (struct.pack('<I4sII', 2, b'0.0 ', 1, 4) + b'MIFX\0\0\0\0'
                 + struct.pack('<III', 28, 1, 1) + b'\x08')
        self.assertEqual(parse_margin(block)['records'][0]['data_offset'], 36)

    def test_empty_supported_object_has_no_records(self):
        self.assertEqual(parse_margin(struct.pack('<I4sI', 2, b'0.0 ', 0))['records'], [])

    def test_truncated_matrix_is_refused_by_host(self):
        with self.assertRaises(ValueError):
            parse_margin(one_record()[:-1])

    def test_offset_into_directory_is_refused_by_host(self):
        block = bytearray(one_record())
        struct.pack_into('<I', block, 20, 12)
        with self.assertRaises(ValueError):
            parse_margin(block)

    def test_version_layout_uses_signed_comparison(self):
        self.assertEqual(record_layout(2, 0x1234), {24: 0, 32: 0x1234, 40: 6250})
        self.assertEqual(record_layout(1, 0x1234), {24: 0x1234, 32: 0})
        self.assertEqual(record_layout(0x80000002, 0x1234), {24: 0x1234, 32: 0})


class CaseFilterTests(unittest.TestCase):
    NAMES = ['MIF', 'INT', 'CPUCL0', 'CPUCL1'] + ['UNUSED']*15 + ['INTSCI']
    TAGS = {0: {255}, 19: {255}, 2: {0, 1}, 3: {0, 1}}

    def test_fresh_margin_does_not_intersect_fast_alias_cases(self):
        result = case_filter(self.NAMES, ['MIF', 'INTSCI'], self.TAGS)
        self.assertEqual(result, dict(present=[0, 19], secondary=[], fast_alias_intersection=[]))

    def test_changed_record_set_invalidates_exclusion(self):
        result = case_filter(self.NAMES, ['MIF', 'CPUCL0', 'INTSCI'], self.TAGS)
        self.assertEqual(result['secondary'], [2])
        self.assertEqual(result['fast_alias_intersection'], [2])

    def test_unproved_matched_tag_is_not_assumed_255(self):
        with self.assertRaises(ValueError):
            case_filter(self.NAMES, ['MIF'], {})

    def test_no_INT_prefix_match_against_INTSCI(self):
        self.assertNotIn(1, case_filter(self.NAMES, ['INTSCI'], self.TAGS)['present'])


class IndexTests(unittest.TestCase):
    def test_last_cell_and_first_outside_row(self):
        self.assertEqual(margin_index(12, 12, 11, 156), dict(index=155, in_host_matrix=True))
        self.assertEqual(margin_index(12, 13, 0, 156), dict(index=156, in_host_matrix=False))

    def test_negative_W_pattern_is_zero_extended_offset(self):
        self.assertFalse(margin_index(12, 0, 0xfffffff8, 156)['in_host_matrix'])

    def test_MADD_wrap_is_not_a_row_bound_check(self):
        self.assertEqual(margin_index(12, 0x40000000, 0, 156), dict(index=0, in_host_matrix=True))


if __name__ == '__main__':
    unittest.main()
