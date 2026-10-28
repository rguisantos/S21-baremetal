import unittest

from inspect_newtime_copy_arguments_hzc2 import (
    CELL, DELTA, assess_source, copy_length, indexed_source,
)


class CopyArgumentBoundsTests(unittest.TestCase):
    def test_signed_nonpositive_length_does_not_access_source(self):
        for bits in (0, 0x80000000, 0xffffffff):
            with self.subTest(bits=bits):
                self.assertEqual(copy_length(bits), 0)
                self.assertEqual(assess_source(None, bits)['whole_cell_source'], False)

    def test_largest_positive_length_and_invalid_W_values(self):
        self.assertEqual(copy_length(0x7fffffff), 0x7fffffff)
        for bits in (-1, 1 << 32, True, '6'):
            with self.subTest(bits=bits), self.assertRaises(ValueError):
                copy_length(bits)

    def test_unresolved_source_and_length_are_not_exclusions(self):
        self.assertIsNone(assess_source(None, 64)['whole_cell_source'])
        self.assertIsNone(assess_source(CELL + 100, None)['source_intersects_cell'])
        self.assertIsNone(assess_source(CELL, None)['whole_cell_source'])

    def test_subword_copy_can_read_partial_cell(self):
        result = assess_source(CELL, 6)
        self.assertTrue(result['source_intersects_cell'])
        self.assertFalse(result['whole_cell_source'])
        self.assertFalse(assess_source(None, 6)['whole_cell_source'])

    def test_whole_cell_requires_all_eight_bytes(self):
        self.assertTrue(assess_source(CELL, 8)['whole_cell_source'])
        self.assertFalse(assess_source(CELL - 1, 8)['whole_cell_source'])
        self.assertTrue(assess_source(CELL - 1, 9)['whole_cell_source'])

    def test_exclusive_end_does_not_intersect(self):
        self.assertFalse(assess_source(CELL - 8, 8)['source_intersects_cell'])
        self.assertFalse(assess_source(CELL + 8, 8)['source_intersects_cell'])

    def test_wrapping_or_invalid_source_is_not_a_safe_interval(self):
        for source, size in (((1 << 64) - 4, 8), (-1, 8), (1 << 64, 8), (True, 8)):
            with self.subTest(source=source), self.assertRaises(ValueError):
                assess_source(source, size)

    def test_negative_index_is_not_silently_treated_as_unsigned(self):
        # Arbitrary entry.W3=-8 really would select a span containing the cell.
        # Only the separate caller dataflow rules that out on its selected path.
        source = indexed_source(0x31668, 0xfffffff8, 32)
        self.assertEqual(source, DELTA + 0x31568)
        self.assertTrue(assess_source(source, 32)['whole_cell_source'])

    def test_nonnegative_caller_extremes_stay_above_cell(self):
        for base, stride, length in ((0x31630, 4, 4), (0x31668, 32, 32)):
            for index in (0, 1, 3, 0x7ffffffe):
                with self.subTest(base=base, index=index):
                    source = indexed_source(base, index, stride)
                    self.assertGreater(source, CELL + 7)
                    self.assertFalse(assess_source(source, length)['source_intersects_cell'])

    def test_unsupported_index_formula_is_rejected(self):
        for args in ((0x31668, 0, 4), (0x31580, 0, 32), (0x31630, -1, 4), (0x31630, True, 4)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                indexed_source(*args)


if __name__ == '__main__':
    unittest.main()
