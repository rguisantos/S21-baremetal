import struct
import unittest

from inspect_newtime_jump_tables_hzc2 import (
    adr_target, adrp_add_base, bhi_target, case_walk, cmp_w0_limit,
    entries, selected_target, sx,
)


def image(*words):
    return b''.join(struct.pack('<I', w) for w in words)


class RelativeEntryTests(unittest.TestCase):
    def test_signed_byte_boundaries(self):
        self.assertEqual([sx(v, 8) for v in (0, 127, 128, 255)], [0, 127, -128, -1])

    def test_signed_halfword_boundaries(self):
        self.assertEqual([sx(v, 16) for v in (0, 32767, 32768, 65535)], [0, 32767, -32768, -1])

    def test_signed_encoding_rejects_bad_widths_and_types(self):
        for v, width in ((-1, 8), (256, 8), (True, 8), (0, True), (0, 32)):
            with self.subTest(v=v, width=width), self.assertRaises(ValueError):
                sx(v, width)

    def test_byte_targets_are_scaled_and_can_point_backward(self):
        es = entries(bytes([0, 1, 255]), 8, 0x100, 0, 0x200)
        self.assertEqual([e['target'] for e in es], [0x100, 0x104, 0xfc])

    def test_halfwords_are_little_endian_before_sign_extension(self):
        es = entries(bytes.fromhex('0100ffff'), 16, 0x100, 0, 0x200)
        self.assertEqual([e['target'] for e in es], [0x104, 0xfc])

    def test_empty_truncated_or_outside_tables_are_refused(self):
        for raw, bits in ((b'', 8), (b'\x01', 16), (b'\x40', 8)):
            with self.subTest(raw=raw, bits=bits), self.assertRaises(ValueError):
                entries(raw, bits, 0x100, 0, 0x200)

    def test_bounds_and_anchor_require_aligned_integers(self):
        for anchor, lo, hi in ((1, 0, 8), (0, 1, 8), (0, 0, 7), (True, 0, 8), (8, 0, 8)):
            with self.subTest(anchor=anchor, lo=lo, hi=hi), self.assertRaises(ValueError):
                entries(b'\x00', 8, anchor, lo, hi)

    def test_unsigned_default_includes_negative_W_bit_pattern(self):
        targets = [0x100, 0x104]
        self.assertEqual([selected_target(i, targets, 0x200) for i in (0, 1, 2, 0xffffffff)],
                         [0x100, 0x104, 0x200, 0x200])

    def test_W_model_rejects_python_values_outside_u32(self):
        for i in (-1, 1 << 32, True, 1.0):
            with self.subTest(i=i), self.assertRaises(ValueError):
                selected_target(i, [0x100], 0x200)


class AddressEncodingTests(unittest.TestCase):
    def test_W0_comparison_recovers_inclusive_maximum(self):
        self.assertEqual(cmp_w0_limit(0x71004c1f), 19)
        self.assertEqual(cmp_w0_limit(0x7100101f), 4)

    def test_comparison_rejects_X_other_register_and_page_shift(self):
        for w in (0xf1004c1f, 0x71004c3f, 0x71404c1f, -1, True):
            with self.subTest(word=w), self.assertRaises(ValueError):
                cmp_w0_limit(w)

    def test_BHI_is_unsigned_and_signed_relative(self):
        self.assertEqual(bhi_target(0x54001348, 0x1ad88), 0x1aff0)
        self.assertEqual(bhi_target(0x54ffffe8, 8), 4)
        with self.assertRaises(ValueError):
            bhi_target(0x54001349, 0)

    def test_ADR_uses_its_PC_once_and_supports_negative_displacements(self):
        self.assertEqual(adr_target(0x10000061, 0x1ad9c), 0x1ada8)
        imm = (-4) & ((1 << 21) - 1)
        word = 0x10000000 | ((imm & 3) << 29) | ((imm >> 2) << 5)
        self.assertEqual(adr_target(word, 0x100), 0xfc)
        with self.assertRaises(ValueError):
            adr_target(0x90000061, 0x100)

    def test_nominal_ADRP_and_nonadjacent_ADD_recover_file_array(self):
        self.assertEqual(adrp_add_base(0xd00000a0, 0x91042000, 0x1ad8c), 0x30108)
        self.assertEqual(adrp_add_base(0xb0000005, 0x9104c0a5, 0x2f914), 0x30130)

    def test_ADRP_ADD_requires_matching_X_register_and_unshifted_immediate(self):
        for second in (0x11042000, 0x91442000, 0x91042020):
            with self.subTest(second=second), self.assertRaises(ValueError):
                adrp_add_base(0xd00000a0, second, 0x1ad8c)


class LocalWalkTests(unittest.TestCase):
    def test_conditional_edges_and_return_are_both_recorded(self):
        result = case_walk(image(0xb4000040, 0xd65f03c0, 0xd65f03c0), [0], 0, 12)
        self.assertEqual(result['visited'], ['0x0', '0x4', '0x8'])
        self.assertEqual([x['reason'] for x in result['exits']], ['ret', 'ret'])

    def test_direct_callee_is_opaque_and_continuation_requires_return(self):
        result = case_walk(image(0x94000003, 0xd65f03c0, 0xd503201f, 0xd65f03c0), [0], 0, 16)
        self.assertEqual(result['visited'], ['0x0', '0x4'])
        self.assertEqual(result['calls'], [dict(pc='0x0', kind='bl', target_file='0xc',
                                              continuation_requires_normal_return=True)])

    def test_indirect_call_retains_register_without_inventing_target(self):
        result = case_walk(image(0xd63f0020, 0xd65f03c0), [0], 0, 8)
        self.assertEqual(result['calls'][0]['register'], 1)
        self.assertEqual(result['calls'][0]['kind'], 'blr')

    def test_outside_common_continuation_is_a_frontier(self):
        result = case_walk(image(0x14000002, 0xd65f03c0), [0], 0, 8)
        self.assertEqual(result['visited'], ['0x0'])
        self.assertEqual(result['exits'], [dict(pc='0x8', reason='outside_case_window')])

    def test_indirect_branch_is_not_followed(self):
        result = case_walk(image(0xd61f0000, 0xd65f03c0), [0], 0, 8)
        self.assertEqual(result['visited'], ['0x0'])
        self.assertEqual(result['exits'][0]['reason'], 'br')

    def test_cycle_is_finite_but_instruction_budget_is_enforced(self):
        result = case_walk(image(0x14000000), [0], 0, 4)
        self.assertEqual(result['visited'], ['0x0'])
        with self.assertRaises(ValueError):
            case_walk(image(0xd503201f, 0xd65f03c0), [0], 0, 8, budget=1)

    def test_invalid_bounds_and_unaligned_root_are_refused(self):
        with self.assertRaises(ValueError):
            case_walk(image(0xd65f03c0), [1], 0, 4)
        with self.assertRaises(ValueError):
            case_walk(image(0xd65f03c0), [0], 0, 8)

    def test_unknown_system_operation_is_a_boundary(self):
        result = case_walk(image(0xd503207f, 0xd65f03c0), [0], 0, 8)
        self.assertEqual(result['visited'], ['0x0'])
        self.assertEqual(result['exits'][0]['reason'], 'system')


if __name__ == '__main__':
    unittest.main()
