"""Regressions for the closed leaf words and conditional caller model."""
import unittest

from inspect_newtime_slot38_hzc2 import (
    caller_effect, leaf_reads, leaf_result, pointer_from_offset,
)

LEAF = tuple(int(x, 16) for x in (
    '90000021 71001c1f f9447821 b9404421 7a5fd024 540000c0 '
    '1ac02821 12000021 6b1f003f 5a9f1000 d65f03c0 12800000 d65f03c0').split())
U32, U64 = (1 << 32) - 1, (1 << 64) - 1


def execute_leaf(index_x, mask, pointer=0x100000, memory=None, reads=None):
    """Independent decoder for these 13 words; host interpretation, not QEMU."""
    registers = [0xabc0000000000000 + i for i in range(31)]
    original = registers.copy()
    registers[0] = index_x
    mem = {0x0211b8f0: pointer, (pointer + 68) & U64: mask} if memory is None else memory
    loads = [] if reads is None else reads
    n = z = c = v = 0
    pc = 0x2d2e4

    def r(i, width=64):
        return 0 if i == 31 else registers[i] & ((1 << width) - 1)

    def put(i, value, width=64):
        if i != 31:
            registers[i] = value & ((1 << width) - 1)

    def subtract(a, b):
        value = (a - b) & U32
        return (value >> 31, int(value == 0), int(a >= b),
                int(bool(((a ^ b) & (a ^ value)) & (1 << 31))))

    for _ in range(20):
        word = LEAF[(pc - 0x2d2e4) // 4]
        rd, rn, rm = word & 31, (word >> 5) & 31, (word >> 16) & 31
        following = pc + 4
        if word & 0x9f000000 == 0x90000000:  # ADRP
            immediate = ((word >> 5) & 0x7ffff) * 4 + ((word >> 29) & 3)
            if immediate & (1 << 20):
                immediate -= 1 << 21
            put(rd, ((pc + 0x020ea000) & ~4095) + immediate * 4096)
        elif word & 0xffc0001f == 0x7100001f:  # CMP Wn,imm
            n, z, c, v = subtract(r(rn, 32), (word >> 10) & 4095)
        elif word & 0xffc00000 in (0xf9400000, 0xb9400000):
            width = 64 if word & (1 << 30) else 32
            address = (r(rn) + ((word >> 10) & 4095) * (width // 8)) & U64
            loads.append((address, width // 8))
            put(rd, mem[address], width)
        elif word & 0xffe00c10 == 0x7a400000:  # CCMP register, condition LE
            if (word >> 12) & 15 != 13:
                raise AssertionError('unexpected CCMP condition')
            if z or n != v:
                n, z, c, v = subtract(r(rn, 32), r(rm, 32))
            else:
                flags = word & 15
                n, z, c, v = ((flags >> shift) & 1 for shift in (3, 2, 1, 0))
        elif word & 0xff00001f == 0x54000000:  # B.EQ
            immediate = (word >> 5) & 0x7ffff
            if immediate & (1 << 18):
                immediate -= 1 << 19
            if z:
                following = pc + immediate * 4
        elif word & 0xffe0fc00 == 0x1ac02800:  # ASRV W
            value = r(rn, 32)
            if value & 0x80000000:
                value -= 1 << 32
            put(rd, value >> (r(rm, 32) & 31), 32)
        elif word & 0xfffffc00 == 0x12000000:  # AND W,#1 encoding
            put(rd, r(rn, 32) & 1, 32)
        elif word & 0xffe0fc1f == 0x6b00001f:  # CMP Wn,Wm
            n, z, c, v = subtract(r(rn, 32), r(rm, 32))
        elif word & 0xffe00c00 == 0x5a800000:  # CSINV W, NE
            if (word >> 12) & 15 != 1:
                raise AssertionError('unexpected CSINV condition')
            put(rd, r(rn, 32) if not z else ~r(rm, 32), 32)
        elif word & 0xff800000 == 0x12800000:  # MOVN W
            put(rd, ~(((word >> 5) & 65535) << (((word >> 21) & 3) * 16)), 32)
        elif word == 0xd65f03c0:
            return dict(x0=registers[0], reads=loads, other_registers_preserved=registers[2:] == original[2:])
        else:
            raise AssertionError(f'unsupported word {word:08x}')
        pc = following
    raise AssertionError('closed leaf did not return')


class LeafTests(unittest.TestCase):
    def test_zero_through_seven_with_real_mask(self):
        self.assertEqual([leaf_result(i, 0x1ff) for i in range(8)], list(range(8)))

    def test_eight_is_rejected_even_with_its_bit_set(self):
        self.assertEqual(leaf_result(8, 0x1ff), U32)

    def test_zero_mask_rejects_every_supplied_index(self):
        for index in (0, 7, 8, 0xffffffe0, U32):
            self.assertEqual(leaf_result(index, 0), U32)

    def test_unset_bit_rejects_low_index(self):
        self.assertEqual(leaf_result(3, 0xf7), U32)
        self.assertEqual(leaf_result(3, 8), 3)

    def test_negative_signed_index_can_return_a_negative_W_pattern(self):
        self.assertEqual(leaf_result(0xffffffe0, 1), 0xffffffe0)

    def test_negative_shift_count_uses_five_low_bits(self):
        self.assertEqual(leaf_result(0xffffffe7, 1 << 7), 0xffffffe7)
        self.assertEqual(leaf_result(0xffffffe7, 1 << 6), U32)

    def test_minimum_signed_integer_tests_bit_zero(self):
        self.assertEqual(leaf_result(0x80000000, 1), 0x80000000)

    def test_minus_one_remains_sentinel_even_if_bit31_set(self):
        self.assertEqual(leaf_result(U32, 0x80000000), U32)

    def test_positive_signed_maximum_is_rejected(self):
        self.assertEqual(leaf_result(0x7fffffff, U32), U32)

    def test_host_refuses_non_W_inputs(self):
        for value in (-1, 1 << 32, True):
            with self.assertRaises(ValueError):
                leaf_result(value, 1)
            with self.assertRaises(ValueError):
                leaf_result(0, value)


class DecodedWordTests(unittest.TestCase):
    def test_real_words_against_algebra_over_signed_and_bit_boundaries(self):
        indices = list(range(40)) + [0x7fffffff, 0x80000000] + list(range(0xffffffc0, 1 << 32))
        masks = [0, U32, 0x1ff, 0x80000000, 0x40000000] + [1 << bit for bit in range(32)]
        for index in indices:
            for mask in masks:
                with self.subTest(index=hex(index), mask=hex(mask)):
                    state = execute_leaf(index, mask)
                    self.assertEqual(state['x0'], leaf_result(index, mask))
                    self.assertTrue(state['other_registers_preserved'])

    def test_written_W0_clears_high_X0_bits(self):
        self.assertEqual(execute_leaf(0xdeadbeef00000003, 0x1ff)['x0'], 3)
        self.assertEqual(execute_leaf(0xdeadbeef00000008, U32)['x0'], U32)

    def test_unconditional_load_order_even_for_rejected_index(self):
        self.assertEqual(execute_leaf(99, 0)['reads'], [(0x0211b8f0, 8), (0x100044, 4)])

    def test_invalid_index_does_not_guard_null_pointer_read(self):
        reads = []
        with self.assertRaises(KeyError):
            execute_leaf(99, 0, memory={0x0211b8f0: 0}, reads=reads)
        self.assertEqual(reads, [(0x0211b8f0, 8), (68, 4)])

    def test_read_address_wraps_at_X_width(self):
        pointer = 0xfffffffffffffffc
        self.assertEqual(execute_leaf(0, 1, pointer=pointer)['reads'][1], (64, 4))


class CallerTests(unittest.TestCase):
    def test_gate_off_skips_callback_and_store(self):
        out = caller_effect(0, 0, 0, 0x1ff, 255)
        self.assertFalse(out['callback_called'])
        self.assertFalse(out['byte_store'])
        self.assertEqual(out['byte_after'], 255)

    def test_only_bit12_controls_selected_gate(self):
        self.assertTrue(caller_effect(0, 0x1000, 0, 1, 255)['callback_called'])
        self.assertFalse(caller_effect(0, 0xffffefff, 0, 1, 255)['callback_called'])

    def test_nonzero_selector_is_outside_this_arm(self):
        for selector in (1, 2, 3, 4, 5, U32):
            self.assertFalse(caller_effect(selector, 0x1000, 0, 1, 255)['in_case0'])

    def test_zero_return_is_success_not_failure(self):
        out = caller_effect(0, 0x1000, 0, 0x1ff, 255)
        self.assertTrue(out['byte_store'])
        self.assertEqual(out['byte_after'], 253)

    def test_only_bit1_is_cleared_for_every_byte(self):
        for byte in range(256):
            out = caller_effect(0, 0x1000, 7, 0x1ff, byte)
            self.assertEqual(out['byte_after'], byte & 0xfd)

    def test_sentinel_skips_descriptor_store(self):
        out = caller_effect(0, 0x1000, 8, 0x1ff, 255)
        self.assertFalse(out['byte_store'])
        self.assertEqual(out['byte_after'], 255)

    def test_raw_negative_success_differs_from_minus_one(self):
        self.assertTrue(caller_effect(0, 0x1000, 0xffffffe0, 0x1ff, 255)['byte_store'])
        self.assertFalse(caller_effect(0, 0x1000, U32, U32, 255)['byte_store'])

    def test_u8_upstream_domain_excludes_negative_counterexample(self):
        accepted = [v for v in range(256) if caller_effect(0, 0x1000, v, 0x1ff, 255)['byte_store']]
        self.assertEqual(accepted, list(range(8)))

    def test_byte_fixture_bounds_are_checked(self):
        for value in (-1, 256, True):
            with self.assertRaises(ValueError):
                caller_effect(0, 0, 0, 1, value)


class PointerTests(unittest.TestCase):
    def test_pointer_addition_is_W_then_signed_extension(self):
        self.assertEqual(pointer_from_offset(0x100), 0x02073700)
        self.assertEqual(pointer_from_offset(0x80000000 - 0x02073600), 0xffffffff80000000)

    def test_pointer_addition_can_wrap_before_SXTW(self):
        self.assertEqual(pointer_from_offset((1 << 32) - 0x02073600), 0)

    def test_read_addresses_do_not_validate_mapping(self):
        self.assertEqual(leaf_reads(0), [(0x0211b8f0, 8), (68, 4)])
        self.assertEqual(leaf_reads(U64), [(0x0211b8f0, 8), (67, 4)])

    def test_host_rejects_pointer_outside_X_width(self):
        for pointer in (-1, 1 << 64, True):
            with self.assertRaises(ValueError):
                leaf_reads(pointer)


if __name__ == '__main__':
    unittest.main()
