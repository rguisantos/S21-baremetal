import unittest

from inspect_newtime_slot20_hzc2 import (
    adjacent_page_add, adr_target, bias_pair, bias_word, literal_x_target, optional_words, stack_transfer,
)


class OptionalBufferTests(unittest.TestCase):
    def test_null_input_preserves_initial_sixteen_zero_words(self):
        self.assertEqual(optional_words(None), (0,) * 16)
        self.assertEqual(bias_pair(None, 3, 1), (0, 0))

    def test_subtraction_is_W_arithmetic_without_saturation(self):
        self.assertEqual(bias_word(0, 0, 1), 0xffffffff)
        self.assertEqual(bias_word(0xfffffff0, 32, 0), 16)

    def test_consumer_uses_low_halves_of_selected_words(self):
        words = [0] * 16
        words[14:16] = [0x12348000, 0xffffabcd]
        self.assertEqual(bias_pair(words, 3, 1), (0x8000, 0xabcd))
        self.assertEqual(bias_pair(words, 3, 0), (0, 0))

    def test_other_word_halves_cannot_change_selected_pair(self):
        original = list(range(16))
        changed = [v | 0xffff0000 for v in original]
        for channel in range(4):
            for lane in range(2):
                self.assertEqual(bias_pair(original, channel, lane), bias_pair(changed, channel, lane))

    def test_host_model_rejects_wrong_widths_and_shapes(self):
        for values in ([0] * 15, [0] * 17, [True] * 16, [1 << 32] * 16):
            with self.subTest(values=values), self.assertRaises(ValueError):
                optional_words(values)
        for args in ((-1, 0, 0), (0, 1 << 16, 0), (0, 0, True)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                bias_word(*args)
        for channel, lane in ((-1, 0), (4, 0), (0, 2), (True, 0)):
            with self.subTest(channel=channel, lane=lane), self.assertRaises(ValueError):
                bias_pair(None, channel, lane)

    def test_callee_copy_uses_a_different_frame_interval(self):
        self.assertEqual(stack_transfer(0x1000),
                         {'source': (0x10c0, 0x1100), 'destination': (0xfc0, 0x1000)})

    def test_no_wrapping_or_unaligned_stack_example_is_admitted(self):
        for sp in (0, 0x1001, (1 << 64) - 16, True):
            with self.subTest(sp=sp), self.assertRaises(ValueError):
                stack_transfer(sp)


class AddressSearchTests(unittest.TestCase):
    def test_literal_sign_extension_and_width_filter(self):
        self.assertEqual(literal_x_target(0x58ffff80, 0x200), 0x1f0)
        self.assertIsNone(literal_x_target(0x18ffff80, 0x200))  # LDR W literal
        self.assertIsNone(literal_x_target(0x98ffff80, 0x200))  # LDRSW literal

    def test_ADR_signed_byte_offsets_and_ADRP_page_alignment(self):
        self.assertEqual(adr_target(0x10000020, 0x100), 0x104)
        self.assertEqual(adr_target(0x10ffffe0, 0x100), 0xfc)
        self.assertEqual(adr_target(0x90000000, 0x1234), 0x1000)
        self.assertEqual(adr_target(0xf0ffffe0, 0x1234), 0)

    def test_adjacent_page_and_ADD_must_share_the_base_register(self):
        self.assertEqual(adjacent_page_add(0x90000000, 0x91160001, 0x31000), 0x31580)
        self.assertIsNone(adjacent_page_add(0x90000000, 0x91160041, 0x31000))

    def test_32bit_ADD_and_discarded_or_SP_results_are_excluded(self):
        self.assertIsNone(adjacent_page_add(0x90000000, 0x11160001, 0x31000))
        self.assertIsNone(adjacent_page_add(0x9000001f, 0x911603e1, 0x31000))
        self.assertIsNone(adjacent_page_add(0x90000000, 0x9116001f, 0x31000))

    def test_ADD_shift_is_not_silently_ignored(self):
        self.assertEqual(adjacent_page_add(0x90000000, 0x91400401, 0x31000), 0x32000)

    def test_invalid_instruction_or_PC_is_rejected(self):
        for word, pc in ((-1, 0), (1 << 32, 0), (True, 0), (0, 1), (0, -4)):
            with self.subTest(word=word, pc=pc), self.assertRaises(ValueError):
                literal_x_target(word, pc)


if __name__ == '__main__':
    unittest.main()
