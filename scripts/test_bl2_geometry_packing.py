"""Packing boundaries using explicit replies; no hardware answers are implied."""
import unittest

from inspect_bl2_geometry_packing import SPECIAL, pack_four, pack_slot


class PackingTests(unittest.TestCase):
    def test_zero_full_selector5_skips_other_replies_but_keeps_revision(self):
        result = pack_slot(((0, 255, 255, 255), (0, 255, 255, 255)), 9, 0)
        self.assertEqual((result['packed'], result['mode'], result['query_count']), (9 << 48, 0, 2))

    def test_nonzero_full_w_with_zero_low_byte_still_activates_term(self):
        result = pack_slot(((0x100, 8, 9, 0x18), (0, 0, 0, 0)), 0, 0)
        self.assertEqual(result['mode'], 1)
        self.assertEqual(result['query_count'], 5)
        self.assertEqual((result['packed'] >> 8) & 255, 0)
        self.assertEqual((result['packed'] >> 32) & 0xffff, 0x0908)

    def test_second_term_alone_selects_mode3_and_its_nibbles(self):
        result = pack_slot(((0, 0, 0, 0), (1, 17, 18, 0xff)), 0, 0)
        self.assertEqual(result['packed'], 0x00f30030)

    def test_density_and_factor_widths_are_four_and_two_bits(self):
        result = pack_slot(((1, 0, 0, 0xff), (0, 0, 0, 0)), 0, 0)
        self.assertEqual(result['packed'], 0xf3000110)

    def test_high_reply_bits_and_second_term_selectors6_7_do_not_pack(self):
        a = pack_slot(((1, 8, 9, 0x18), (1, 0, 0, 0x14)), 0, 0)
        b = pack_slot(((0xffff0001, 0xffff0008, 0xffff0009, 0xffff0018),
                       (1, 0xffffffff, 0xffffffff, 0xffff0014)), 0, 0)
        self.assertEqual(a['packed'], b['packed'])

    def test_special_one_term_constant_and_extension_threshold(self):
        replies = ((1, 8, 0, 0x18), (0, 0, 0, 0))
        for nibble in range(16):
            result = pack_slot(replies, 1, nibble)
            self.assertEqual(result['before_extension'], SPECIAL[0])
            self.assertTrue(result['queried_extension'])
            self.assertEqual(result['packed'], SPECIAL[0] | ((nibble if nibble > 3 else 0) << 56))

    def test_third_constant_retains_even_small_extension_nibbles(self):
        replies = ((1, 8, 0, 0x18), (1, 0, 0, 0x18))
        for extension in (0, 1, 3, 4, 15, 0xfffffffd):
            result = pack_slot(replies, 1, extension)
            self.assertEqual(result['before_extension'], SPECIAL[2])
            self.assertEqual(result['packed'], SPECIAL[2] | ((extension & 15) << 56))

    def test_exact_comparison_excludes_near_match_and_other_revision(self):
        for replies, rev in ((((1, 8, 1, 0x18), (0, 0, 0, 0)), 1),
                             (((1, 8, 0, 0x18), (0, 0, 0, 0)), 2)):
            self.assertFalse(pack_slot(replies, rev, 15)['queried_extension'])

    def test_return_and_byte_follow_last_slot_while_size_leaf_follows_slot0(self):
        two = ((1, 0, 0, 0x18), (1, 0, 0, 0x18))
        zero = ((0, 0, 0, 0), (0, 0, 0, 0))
        result = pack_four((two, zero, zero, zero), (0,)*4, (0,)*4)
        self.assertEqual((result['returned_w0'], result['mode_byte']), (0, 0))
        self.assertEqual((result['slots'][0]['packed'] >> 4) & 15, 3)

    def test_inputs_refuse_bool_overflow_negative_and_wrong_shapes(self):
        good = ((1, 8, 0, 0x18), (0, 0, 0, 0))
        for bad in (True, -1, 1 << 32, '1'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pack_slot(((bad, 0, 0, 0), (0,)*4), 1, 0)
        for args in ((good, 16, 0), (good, True, 0), (good, 1, -1),
                     (good[:1], 1, 0), (((1,), (0,)*4), 1, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                pack_slot(*args)
        with self.assertRaises(ValueError):
            pack_four((good,)*3, (0,)*4, (0,)*4)


if __name__ == '__main__':
    unittest.main()
