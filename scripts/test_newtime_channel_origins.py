import unittest

from inspect_newtime_channel_origins_hzc2 import (
    ARCHIVE_BASE, CHANNEL_BASE, CHANNEL_SIZE, CURSOR_LIMIT, fresh_archive, registration_prefix,
)


class ChannelArchiveTests(unittest.TestCase):
    def test_header_is_registered_without_copying_from_a_second_source(self):
        header = fresh_archive()['entries'][0]
        self.assertEqual(header['archive_address'], '0x223f000')
        self.assertEqual(header['bytes'], 416)
        self.assertIsNone(header['copy_source'])

    def test_four_channel_records_after_header(self):
        profile = fresh_archive()
        self.assertEqual(profile['final_cursor'], '0x2243060')
        self.assertEqual(profile['final_count'], 5)
        self.assertEqual([e['archive_address'] for e in profile['entries'][1:]],
                         ['0x223f1a0', '0x2240150', '0x2241100', '0x22420b0'])
        self.assertEqual([e['copy_source'] for e in profile['entries'][1:]],
                         ['0x2075a00', '0x20769b0', '0x2077960', '0x2078910'])

    def test_optional_record_shifts_all_channel_sources_in_archive(self):
        profile = fresh_archive(True)
        self.assertEqual(profile['final_cursor'], '0x2243094')
        self.assertEqual(profile['final_count'], 6)
        self.assertEqual(profile['entries'][2]['archive_address'], '0x223f1d4')
        self.assertEqual(profile['entries'][1]['name'], 'charac_lvcc')

    def test_selected_spans_do_not_read_the_cell_but_are_conditional(self):
        for profile in (fresh_archive(), fresh_archive(True)):
            self.assertTrue(profile['conditional_model_only'])
            self.assertFalse(profile['runtime_directory_observed'])
            for entry in profile['entries']:
                self.assertFalse(entry['archive_source_assessment']['source_intersects_cell'])

    def test_descriptor_fields_are_after_sixteen_byte_name(self):
        p = registration_prefix(ARCHIVE_BASE, 2, CHANNEL_SIZE)
        self.assertEqual(p['source_field_address'] - p['name_address'], 16)
        self.assertEqual(p['length_field_address'] - p['name_address'], 20)
        self.assertEqual(p['stored_source'], ARCHIVE_BASE)

    def test_fifteenth_record_is_accepted_sixteenth_is_written_before_guard(self):
        accepted = registration_prefix(ARCHIVE_BASE, 14, 1)
        self.assertIsNone(accepted['first_bounds_error_request'])
        refused = registration_prefix(ARCHIVE_BASE, 15, 1)
        self.assertEqual(refused['first_bounds_error_request'], 'count_limit_at_0x21e48')
        self.assertTrue(refused['metadata_written_before_bounds_error'])
        self.assertGreater(refused['length_field_address'] + 4, ARCHIVE_BASE + 416)

    def test_inclusive_cursor_limit_and_post_store_error(self):
        self.assertIsNone(registration_prefix(CURSOR_LIMIT - 10, 0, 10)['first_bounds_error_request'])
        p = registration_prefix(CURSOR_LIMIT - 10, 0, 11)
        self.assertEqual(p['first_bounds_error_request'], 'cursor_limit_at_0x21e30')
        self.assertTrue(p['metadata_written_before_bounds_error'])

    def test_cursor_error_precedes_count_error(self):
        p = registration_prefix(CURSOR_LIMIT, 15, 1)
        self.assertEqual(p['first_bounds_error_request'], 'cursor_limit_at_0x21e30')

    def test_W_arithmetic_wrap_is_not_misreported_as_an_overflow_guard(self):
        p = registration_prefix(0xfffffff0, 0, 32)
        self.assertEqual(p['stored_next_cursor'], 16)
        self.assertIsNone(p['first_bounds_error_request'])
        self.assertFalse(p['valid_accesses_or_normal_error_return_proved'])

    def test_adjacent_channel_buffers_end_at_configuration_buffer(self):
        self.assertEqual(CHANNEL_BASE + 4 * CHANNEL_SIZE, 0x020798c0)

    def test_invalid_host_values_are_rejected(self):
        for args in ((-1, 0, 1), (0, 1 << 32, 1), (0, 0, True), ('0', 0, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                registration_prefix(*args)
        with self.assertRaises(ValueError):
            fresh_archive(1)


if __name__ == '__main__':
    unittest.main()
