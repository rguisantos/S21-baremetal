import struct
import unittest

from inspect_newtime_jump_tables_hzc2 import adr_target
from inspect_newtime_mif_bins_hzc2 import (
    THRESHOLDS, bin_index, leaf_contract, return_overwrite_frontier,
)


class ThresholdTests(unittest.TestCase):
    def test_equal_threshold_and_preceding_value(self):
        for k, t in enumerate(THRESHOLDS[:13]):
            with self.subTest(k=k):
                self.assertEqual(bin_index(t), k)
                self.assertEqual(bin_index(t - 1), k + 1)

    def test_zero_sentinel_stops_at_index_13(self):
        self.assertEqual(bin_index(0), 13)
        self.assertEqual(THRESHOLDS[bin_index(0)], 0)

    def test_comparison_is_unsigned(self):
        self.assertEqual(bin_index(0x80000000), 0)
        self.assertEqual(bin_index(0xffffffff), 0)

    def test_invalid_W_input_is_not_coerced(self):
        for value in (-1, 1 << 32, True, 2.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bin_index(value)

    def test_bins_are_monotone_nondecreasing_as_value_decreases(self):
        values = list(range(3173))
        bins = [bin_index(v) for v in values]
        self.assertTrue(all(a >= b for a, b in zip(bins, bins[1:])))


class ReturnContractTests(unittest.TestCase):
    def test_return_is_bin_of_second_argument(self):
        result = leaf_contract(3172, 421)
        self.assertEqual(result['X0'], 12)
        self.assertEqual(result['bin_W0'], 0)

    def test_X2_is_threshold_not_bin_or_constant_13(self):
        result = leaf_contract(3172, 2730)
        self.assertEqual(result['X0'], 1)
        self.assertEqual(result['X2'], 2730)
        self.assertNotEqual(result['X2'], 13)

    def test_X3_is_threshold_selected_by_first_argument(self):
        self.assertEqual(leaf_contract(1000, 2000)['X3'], 845)
        self.assertEqual(leaf_contract(1000, 2000)['X2'], 1716)

    def test_both_zero_inputs_leave_zero_thresholds(self):
        result = leaf_contract(0, 0)
        self.assertEqual((result['X0'], result['X2'], result['X3']), (13, 0, 0))

    def test_raw_second_argument_is_retained_in_global_contract(self):
        self.assertEqual(leaf_contract(0, 0xffffffff)['raw_W1'], 0xffffffff)


def prefix_lines():
    return {
        0x1aff0: (0xb4000258, 'cbz', 'x24, 0x1b038'),
        0x1aff4: (0x52800001, 'mov', 'w1, #0x0'),
        0x1aff8: (0xb9401305, 'ldr', 'w5, [x24, #16]'),
        0x1affc: (0x14000002, 'b', '0x1b004'),
        0x1b004: (0x6b05003f, 'cmp', 'w1, w5'),
        0x1b008: (0x5400018a, 'b.ge', '0x1b038'),
        0x1b00c: (0xb9400f00, 'ldr', 'w0, [x24, #12]'),
        0x1b038: (0xd2800000, 'mov', 'x0, #0x0'),
    }


class ReturnLivenessTests(unittest.TestCase):
    def test_both_conditional_paths_reach_an_overwrite(self):
        result = return_overwrite_frontier(prefix_lines())
        self.assertEqual(result['overwrites'], ['0x1b00c', '0x1b038'])
        self.assertEqual(len(result['visited']), 8)

    def test_omitting_bypass_path_is_refused(self):
        lines = prefix_lines()
        del lines[0x1b038]
        with self.assertRaises(ValueError):
            return_overwrite_frontier(lines)

    def test_X0_read_before_overwrite_is_refused(self):
        lines = prefix_lines()
        lines[0x1aff4] = (0x91000401, 'add', 'x1, x0, #0x1')
        with self.assertRaises(ValueError):
            return_overwrite_frontier(lines)

    def test_unaccounted_call_is_refused(self):
        lines = prefix_lines()
        lines[0x1aff4] = (0x94000000, 'bl', '0x1aff4')
        with self.assertRaises(ValueError):
            return_overwrite_frontier(lines)

    def test_overwrite_shape_is_checked(self):
        lines = prefix_lines()
        lines[0x1b038] = (0xaa0003e1, 'mov', 'x1, x0')
        with self.assertRaises(ValueError):
            return_overwrite_frontier(lines)


class MappingPremiseTests(unittest.TestCase):
    def test_same_ADR_word_is_translation_invariant(self):
        word = 0x10000061
        a, b = 0x1ad9c, 0x2104d9c
        self.assertEqual(adr_target(word, a) - a, 12)
        self.assertEqual(adr_target(word, b) - b, 12)
        self.assertEqual(struct.pack('<I', word).hex(), '61000010')


if __name__ == '__main__':
    unittest.main()
