"""Publication sampling/lookup boundaries; no physical values are supplied."""
import unittest

from inspect_bl2_geometry_publication import phase_counter, publication

TABLE = dict(columns=2, rows=2, cells=(0xcafe, 11, 0x1000860000110, 22))


class PublicationTests(unittest.TestCase):
    def test_stable_sample_reaches_first_store_without_declaring_full_success(self):
        result = publication(TABLE, 0x1000860000110, 0x1000860000110)
        self.assertTrue(result['first_store_reached'])
        self.assertEqual(result['row'], 1)
        self.assertIsNone(result['prefix_error'])

    def test_argument_copy_and_callback_input_can_be_different_samples(self):
        result = publication(TABLE, 0xcafe, 0x1000860000110)
        self.assertEqual(result['fixed_argument_copy'], 0xcafe)
        self.assertEqual(result['first_u64_written'], 0x1000860000110)

    def test_caller_match_does_not_rescue_wrapper_reload_miss(self):
        result = publication(TABLE, 0xcafe, 0xdeadbeef)
        self.assertEqual(result['prefix_error'], 1)
        self.assertFalse(result['first_store_reached'])
        self.assertIsNone(result['first_u64_written'])

    def test_caller_miss_does_not_prevent_wrapper_reload_match(self):
        self.assertTrue(publication(TABLE, 0xdeadbeef, 0xcafe)['first_store_reached'])

    def test_signed_comparison_normalization_keeps_original_stored_value(self):
        value = 0x800000000000cafe
        result = publication(TABLE, value, value)
        self.assertEqual(result['comparison_key'], 0xcafe)
        self.assertEqual(result['first_u64_written'], value)

    def test_name_and_key_errors_keep_fixed_argument_copy_but_no_first_store(self):
        for control, code in (('name', 3), ('key', 2)):
            result = publication(TABLE, 0xcafe, 0xcafe, control)
            self.assertEqual((result['fixed_argument_copy'], result['prefix_error']), (0xcafe, code))
            self.assertFalse(result['first_store_reached'])

    def test_phase_counter_wraps_as_w(self):
        self.assertEqual(phase_counter(0xffffffff), 0)
        self.assertEqual(phase_counter(0x10203040), 0x10203041)

    def test_strict_sample_counter_and_control_types(self):
        for bad in (True, -1, 1 << 64, '1'):
            for args in ((bad, 0xcafe), (0xcafe, bad)):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    publication(TABLE, *args)
        for bad in (True, -1, 1 << 32):
            with self.assertRaises(ValueError):
                phase_counter(bad)
        with self.assertRaises(ValueError):
            publication(TABLE, 0xcafe, 0xcafe, 'unsupported')


if __name__ == '__main__':
    unittest.main()
