import unittest

from inspect_newtime_slot38_buffers_hzc2 import (
    backup_ranges, copy_cycle, forward_copy, overlaps, target_buffer, windows,
)

COPY = [int(v, 16) for v in (
    'd2800003 4b030044 6b1f009f 540000ad 38636824 38236804 '
    '91000463 17fffffa d65f03c0').split()]
MASK = (1 << 64) - 1
LOW_WORDS = [int(v, 16) for v in (
    'd286fe00 f2a040e0 29408014 531e7400 0b020294 1b157c00 93407c00 8b34c014').split()]
HIGH_WORDS = [int(v, 16) for v in (
    'd2870000 f2a040e0 29408014 531e7400 0b010294 1b027c00 93407c42 93407c00 8b34c014').split()]


def decoded_row(index, offset, columns, upper=False):
    """Independent fixed-word decoder, including W-pair loads and SXTW."""
    registers = [0xfeed000000000000 + i for i in range(31)]
    registers[21] = index
    registers[1] = 0x02073600
    registers[2] = (index - 6) & 0xffffffff if upper else 0x02073600
    base = 0x02073800 if upper else 0x020737f0
    memory = {base + 4: offset, base + 8: columns}
    reads = []
    def r(i, bits=64):
        return 0 if i == 31 else registers[i] & ((1 << bits) - 1)
    def signed_w(value):
        return value - (1 << 32) if value & 0x80000000 else value
    for word in HIGH_WORDS if upper else LOW_WORDS:
        rd, rn, rm = word & 31, (word >> 5) & 31, (word >> 16) & 31
        if word & 0xff800000 in (0xd2800000, 0xf2800000):
            shift = ((word >> 21) & 3) * 16
            value = ((word >> 5) & 65535) << shift
            registers[rd] = value if word & 0xff800000 == 0xd2800000 else (r(rd) & ~(65535 << shift)) | value
        elif word & 0xffc00000 == 0x29400000:
            displacement = (word >> 15) & 127
            if displacement & 64:
                displacement -= 128
            a = (r(rn) + displacement * 4) & MASK
            values = [memory[a], memory[(a + 4) & MASK]]
            reads.extend([a, (a + 4) & MASK])
            registers[rd], registers[(word >> 10) & 31] = (v & 0xffffffff for v in values)
        elif word & 0xfffffc00 == 0x531e7400:
            registers[rd] = (r(rn, 32) << 2) & 0xffffffff
        elif word & 0xffe0fc00 == 0x0b000000:
            registers[rd] = (r(rn, 32) + r(rm, 32)) & 0xffffffff
        elif word & 0xffe08000 == 0x1b000000 and (word >> 10) & 31 == 31:
            registers[rd] = (r(rn, 32) * r(rm, 32)) & 0xffffffff
        elif word & 0xfffffc00 == 0x93407c00:
            registers[rd] = signed_w(r(rn, 32)) & MASK
        elif word & 0xffe0fc00 == 0x8b20c000:
            registers[rd] = (r(rn) + signed_w(r(rm, 32))) & MASK
        else:
            raise AssertionError(f'unsupported row word {word:08x}')
    return registers[20], reads


def decoded_copy(memory, destination, source, count):
    """Independent decoder restricted to the nine real 1fcc4 words."""
    registers = [destination, source, count, 0xdead, 0xbeef]
    pc = 0x1fcc4
    negative = zero = False
    for _ in range(8192):
        word = COPY[(pc - 0x1fcc4) // 4]
        rd, rn, rm = word & 31, (word >> 5) & 31, (word >> 16) & 31
        next_pc = pc + 4
        if word & 0xff800000 == 0xd2800000:
            registers[rd] = ((word >> 5) & 65535) << (((word >> 21) & 3) * 16)
        elif word & 0xffe0fc00 == 0x4b000000:
            registers[rd] = (registers[rn] - registers[rm]) & 0xffffffff
        elif word == 0x6b1f009f:
            negative, zero = bool(registers[4] & 0x80000000), registers[4] == 0
        elif word & 0xff00001f == 0x5400000d:
            displacement = (word >> 5) & 0x7ffff
            if displacement & (1 << 18):
                displacement -= 1 << 19
            if negative or zero:
                next_pc = pc + 4 * displacement
        elif word & 0xffe0fc00 == 0x38606800:
            registers[rd] = memory[(registers[rn] + registers[rm]) & MASK]
        elif word & 0xffe0fc00 == 0x38206800:
            memory[(registers[rn] + registers[rm]) & MASK] = registers[rd] & 255
        elif word & 0xffc00000 == 0x91000000:
            registers[rd] = (registers[rn] + ((word >> 10) & 4095)) & MASK
        elif word >> 26 == 5:
            displacement = word & 0x3ffffff
            if displacement & (1 << 25):
                displacement -= 1 << 26
            next_pc = pc + 4 * displacement
        elif word == 0xd65f03c0:
            return registers
        else:
            raise AssertionError(f'unsupported copy word {word:08x}')
        pc = next_pc
    raise AssertionError('host instruction budget exceeded')


def desc(offset, columns=18, rows=13):
    return dict(payload_offset=offset, columns=columns, rows=rows, bytes=columns * rows * 4)


class BufferTests(unittest.TestCase):
    LOW, HIGH = desc(0x1000), desc(0x1800, rows=7)

    def test_low_row_pointer_and_72_byte_extent(self):
        b = target_buffer(3, 0, self.LOW, self.HIGH)
        self.assertEqual((b['column'], b['row'], b['address'], b['copy_bytes']), (6, 3, 0x020746d8, 72))
        self.assertTrue(b['inside_payload'])

    def test_index_six_selects_upper_row_zero_only_with_control_bit(self):
        b = target_buffer(6, 1 << 6, self.LOW, self.HIGH)
        self.assertEqual((b['column'], b['row'], b['address']), (7, 0, 0x02074e00))
        self.assertEqual(target_buffer(6, 0, self.LOW, self.HIGH)['column'], 6)

    def test_index_seven_upper_row_one(self):
        b = target_buffer(7, 1 << 7, self.LOW, self.HIGH)
        self.assertEqual((b['row'], b['address']), (1, 0x02074e48))

    def test_low_indices_ignore_control_bits(self):
        for i in range(6):
            self.assertEqual(target_buffer(i, 65535, self.LOW, self.HIGH)['column'], 6)

    def test_control_is_truncated_to_low16(self):
        self.assertEqual(target_buffer(16, 1 << 16, self.LOW, self.HIGH)['column'], 6)

    def test_variable_shift_masks_count_to_five_bits(self):
        b = target_buffer(38, 1 << 6, self.LOW, self.HIGH)
        self.assertEqual((b['column'], b['row']), (7, 32))
        self.assertFalse(b['inside_payload'])

    def test_signed_negative_index_uses_low_path_and_signed_row_offset(self):
        b = target_buffer(0xffffffff, 65535, self.LOW, self.HIGH)
        self.assertEqual((b['column'], b['address']), (6, 0x020745b8))
        self.assertFalse(b['inside_payload'])

    def test_row_product_wraps_before_SXTW(self):
        b = target_buffer(0x40000000, 0, self.LOW, self.HIGH)
        self.assertEqual(b['address'], 0x02074600)
        self.assertFalse(b['row_in_dimensions'])

    def test_payload_base_sign_extension(self):
        low = desc(0x80000000 - 0x02073600)
        self.assertEqual(target_buffer(0, 0, low, self.HIGH)['address'], 0xffffffff80000000)

    def test_copy_can_exceed_row_width_even_inside_total_payload(self):
        b = target_buffer(0, 0, desc(0x1000, columns=17), self.HIGH)
        self.assertTrue(b['inside_payload'])
        self.assertFalse(b['copy_within_row'])

    def test_first_row_outside_payload_is_not_host_clamped(self):
        b = target_buffer(13, 0, self.LOW, self.HIGH)
        self.assertFalse(b['inside_payload'])
        self.assertEqual(b['address'], 0x020749a8)

    def test_all_indices_accepted_by_real_mask_fit_both_selected_paths(self):
        for i in range(8):
            for control in (0, 65535):
                b = target_buffer(i, control, self.LOW, self.HIGH)
                self.assertTrue(b['inside_payload'] and b['row_in_dimensions'] and b['copy_within_row'])

    def test_host_rejects_non_W_index(self):
        for value in (-1, 1 << 32, True):
            with self.assertRaises(ValueError):
                target_buffer(value, 0, self.LOW, self.HIGH)


class WindowTests(unittest.TestCase):
    def test_touching_half_open_ranges_do_not_overlap(self):
        self.assertFalse(overlaps(100, 72, 172, 8))
        self.assertTrue(overlaps(100, 72, 171, 8))

    def test_X_wrap_is_split_before_comparing(self):
        self.assertEqual(windows(MASK - 1, 4), [(MASK - 1, 1 << 64), (0, 2)])
        self.assertTrue(overlaps(MASK - 1, 4, 1, 8))

    def test_empty_range_is_not_an_access(self):
        self.assertEqual(windows(1, 0), [])
        self.assertFalse(overlaps(0, 0, 0, 8))

    def test_nominal_envelope_does_not_reach_slot47_or_binding(self):
        for start, size in ((0x211b580, 8), (0x211b998, 8)):
            self.assertFalse(overlaps(0x2074600, 0x207925c - 0x2074600, start, size))


class DecodedRowTests(unittest.TestCase):
    def test_actual_low_words_match_width_and_wrap_boundaries(self):
        for index in (0, 7, 13, 255, 0x40000000, 0xffffffff):
            for offset in (0x1000, 0xffffffff, 0x7df8ca00):
                for columns in (18, 0x40000000, 0xffffffff):
                    d = dict(payload_offset=offset, columns=columns, rows=13,
                             bytes=(columns * 13 * 4) & 0xffffffff)
                    actual, reads = decoded_row(index, offset, columns)
                    self.assertEqual(actual, target_buffer(index, 0, d, d)['address'])
                    self.assertEqual(reads, [0x020737f4, 0x020737f8])

    def test_actual_upper_words_match_subtract_six_and_width_boundaries(self):
        for index in (6, 7, 38, 0x7fffffe6):
            for offset in (0x1000, 0xffffffff, 0x7df8ca00):
                for columns in (18, 0x40000000, 0xffffffff):
                    d = dict(payload_offset=offset, columns=columns, rows=7,
                             bytes=(columns * 7 * 4) & 0xffffffff)
                    actual, reads = decoded_row(index, offset, columns, upper=True)
                    self.assertEqual(actual, target_buffer(index, 1 << (index & 31), d, d)['address'])
                    self.assertEqual(reads, [0x02073804, 0x02073808])


class CopyTests(unittest.TestCase):
    def test_decoded_words_match_forward_model_over_lengths(self):
        for n in (0, 1, 2, 4, 64, 68, 72, 160, 0x80000000, 0xffffffff):
            a = {1000 + i: (i * 7) & 255 for i in range(160)}
            b = a.copy()
            forward_copy(a, 2000, 1000, n)
            registers = decoded_copy(b, 2000, 1000, n)
            self.assertEqual(a, b)
            self.assertEqual(registers[:3], [2000, 1000, n])

    def test_overlap_propagates_forward_instead_of_memmove(self):
        a = {1000 + i: i + 1 for i in range(5)}
        b = a.copy()
        forward_copy(a, 1001, 1000, 4)
        decoded_copy(b, 1001, 1000, 4)
        self.assertEqual([a[1000 + i] for i in range(5)], [1] * 5)
        self.assertEqual(a, b)

    def test_missing_source_leaves_previous_writes(self):
        memory = {1000: 1, 1001: 2}
        with self.assertRaises(KeyError):
            forward_copy(memory, 2000, 1000, 3)
        self.assertEqual([memory[2000], memory[2001]], [1, 2])

    def test_negative_count_skips_even_unmapped_fixture_addresses(self):
        self.assertEqual(forward_copy({}, 0, 0, 0xffffffff), 0)

    def test_copy_addresses_wrap_at_X_width(self):
        memory = {MASK: 4, 0: 5}
        forward_copy(memory, 1000, MASK, 2)
        self.assertEqual([memory[1000], memory[1001]], [4, 5])

    def test_host_budget_is_separate_from_firmware_count(self):
        with self.assertRaises(ValueError):
            forward_copy({}, 0, 0, 2049)


class CycleTests(unittest.TestCase):
    F, A, B, C = 0x8000, 0x1000, 0x2000, 0x3000

    def memory(self, b=None):
        b = self.B if b is None else b
        m = {self.F + i: 0xa5 for i in range(448)}
        for base, size, value in ((self.A, 160, 0x11), (b, 72, 0x33), (self.C, 68, 0x55)):
            m.update({base + i: value for i in range(size)})
        return m

    def test_byte_changes_in_window_then_original_is_restored(self):
        m = self.memory(); seen = []
        def action(memory):
            memory[self.B + 1] &= 0xfd
            seen.append(memory[self.B + 1])
        copy_cycle(m, self.F, [self.A, self.B, self.C], 17, 17, action)
        self.assertEqual(seen, [0x31])
        self.assertEqual([m[self.B + i] for i in range(72)], [0x33] * 72)

    def test_corrupted_backup_changes_what_is_restored(self):
        m = self.memory()
        def action(memory):
            memory[self.F + 257] ^= 2
        copy_cycle(m, self.F, [self.A, self.B, self.C], 17, 17, action)
        self.assertEqual(m[self.B + 1], 0x31)

    def test_stack_alias_disables_original_byte_restoration(self):
        b = self.F + 256; m = self.memory(b)
        def action(memory):
            memory[b + 1] &= 0xfd
        copy_cycle(m, self.F, [self.A, b, self.C], 17, 17, action)
        self.assertEqual(m[b + 1], 0x31)

    def test_intervening_failure_does_not_automatically_restore(self):
        m = self.memory()
        def action(memory):
            memory[self.B + 1] &= 0xfd
            raise RuntimeError('fixture has no normal return')
        with self.assertRaises(RuntimeError):
            copy_cycle(m, self.F, [self.A, self.B, self.C], 17, 17, action)
        self.assertEqual(m[self.B + 1], 0x31)

    def test_reloaded_count_can_copy_bytes_never_backed_up(self):
        m = self.memory()
        copy_cycle(m, self.F, [self.A, self.B, self.C], 16, 17, lambda _: None)
        self.assertEqual([m[self.C + i] for i in range(64, 68)], [0xa5] * 4)

    def test_changed_count_and_C_alias_can_overwrite_B_after_its_restore(self):
        m = self.memory(); c = self.B + 4
        m.update({c + i: 0x55 for i in range(68)})
        before = [m[self.B + i] for i in range(72)]
        copy_cycle(m, self.F, [self.A, self.B, c], 16, 17, lambda _: None)
        self.assertEqual(before[-4:], [0x55] * 4)
        self.assertEqual([m[self.B + i] for i in range(68, 72)], [0xa5] * 4)

    def test_initial_counts_fit_frame_but_raw_byte_is_not_a_guard(self):
        for n in (16, 17):
            start, length = backup_ranges(self.F, n)[-1]
            self.assertLessEqual(start + length, self.F + 448)
        start, length = backup_ranges(self.F, 31)[-1]
        self.assertGreater(start + length, self.F + 448)


if __name__ == '__main__':
    unittest.main()
