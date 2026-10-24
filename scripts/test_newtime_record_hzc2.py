"""Allocator, gate and partial-record boundary cases for the conditional model."""
import unittest

from inspect_newtime_record_hzc2 import (DATA, DIRECTORY, LIMIT, U64,
                                        allocation, gated_key, plan, wrapper_result)


def fixture(keys=None, columns=1, rows=15):
    return {0x11111111: dict(columns=17, rows=1, cells=(0xcafe,)+tuple(keys or [0x108]*16)),
            0x108: dict(columns=columns, rows=rows)}


class RecordTests(unittest.TestCase):
    def test_exact_fit_and_exhaustion_update_cursor_before_decision(self):
        self.assertEqual(allocation(0x1000, 0x103c, 60),
            dict(returned_pointer=0x1000, cursor_after=0x103c, parked=False))
        self.assertEqual(allocation(0x1000, 0x1038, 60),
            dict(returned_pointer=None, cursor_after=0x103c, parked=True))

    def test_rounding_does_not_align_the_returned_old_pointer(self):
        self.assertEqual(allocation(0x1001, 0x1008, 5),
            dict(returned_pointer=0x1001, cursor_after=0x1008, parked=False))

    def test_w_request_is_signed_and_address_arithmetic_wraps(self):
        self.assertEqual(allocation(0x1004, 0x2000, 0xffffffff)['cursor_after'], 0x1004)
        self.assertEqual(allocation(0, U64, 0x80000000)['cursor_after'], 0xffffffff80000000)
        self.assertEqual(allocation(U64-3, U64, 4)['cursor_after'], 0)

    def test_unsigned_inputs_do_not_coerce_bool_negative_or_oversized(self):
        for value in (True, -1, 1 << 64, '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                allocation(value, 0x2000, 4)
        for mask in (True, -1, 512):
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                gated_key(0x108, 0, mask)

    def test_selected_key_transform_depends_on_the_low_nibble(self):
        self.assertEqual(gated_key(0x108, 0, 1), 0x10b)
        self.assertEqual(gated_key(0x10b, 0, 1), 0x108)
        self.assertEqual(gated_key(0x105, 0, 1), 0x102)

    def test_each_of_the_first_nine_gate_choices_is_independent(self):
        for index in range(9):
            with self.subTest(index=index):
                self.assertEqual(gated_key(0x108, index, 1 << index), 0x10b)
                self.assertEqual(gated_key(0x108, index, 511 ^ (1 << index)), 0x108)
        self.assertEqual(gated_key(0x108, 9, 511), 0x108)
        self.assertEqual(gated_key(0x108, 15, 511), 0x108)

    def test_key_subtraction_wraps_as_u64(self):
        self.assertEqual(gated_key(0, 0, 1), U64-2)

    def test_success_reserves_directory_and_commits_used_size_only_at_end(self):
        result = plan(fixture(), 0, 0)
        self.assertEqual((result['return_code'], result['cursor']), (0, DATA+16*60))
        self.assertTrue(result['final_used_field_written'])
        self.assertEqual(result['steps'][0]['descriptor_offset'], DIRECTORY)
        self.assertEqual(result['steps'][-1]['descriptor_offset']+16, DATA)
        self.assertLessEqual(result['cursor'], LIMIT)

    def test_missing_key_keeps_preceding_allocation_and_omits_final_used_size(self):
        result = plan(fixture([0x108, 0xdead]+[0x108]*14), 0, 0)
        self.assertEqual((result['return_code'], result['failed_index'], result['failed_key']), (4, 1, 0xdead))
        self.assertEqual((len(result['steps']), result['cursor']), (1, DATA+60))
        self.assertFalse(result['final_used_field_written'])

    def test_allocator_park_is_not_a_null_return_or_descriptor_commit(self):
        result = plan(fixture(columns=50, rows=50), 0, 0)
        self.assertEqual(result['status'], 'parked_allocator')
        self.assertIsNone(result['return_code'])
        self.assertEqual((result['cursor'], result['steps']), (DATA+10000, []))
        self.assertFalse(result['final_used_field_written'])

    def test_wrapper_routes_errors_and_returns_wrapped_subtraction_for_zero(self):
        for status in (1, 3, 4):
            self.assertEqual(wrapper_result(status)['w0_argument'], 27)
        self.assertEqual(wrapper_result(2)['w0_argument'], 5)
        self.assertEqual(wrapper_result(0), dict(returned_w0=0xfffffffd, returns_directly=True))
        self.assertEqual(wrapper_result(5)['returned_w0'], 2)
        self.assertEqual(wrapper_result(0xffffffff)['returned_w0'], 0xfffffffc)

    def test_shape_and_row_bounds_are_checked(self):
        for row, mask in ((1, 0), (0, 512), (-1, 0), (True, 0)):
            with self.subTest(row=row, mask=mask), self.assertRaises(ValueError):
                plan(fixture(), row, mask)


if __name__ == '__main__':
    unittest.main()
