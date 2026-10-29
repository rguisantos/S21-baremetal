import json
from pathlib import Path
import struct
import unittest

from inspect_newtime_method56_hzc2 import (
    advance, channel_config, doorbell, marker_stores, record_address,
    packed_level, relative_vector, reply_matches, request_words, ring_addresses,
)


class RequestTests(unittest.TestCase):
    def test_packet_contains_low24_and_two_command6_words(self):
        self.assertEqual(request_words(0xab123456), [0, 0x123456, 6, 6])

    def test_selected_word_is_not_the_index(self):
        self.assertEqual(record_address(0x1000, 20, 7), 0x1030)
        self.assertEqual(request_words(0xffffffff), [0, 0xffffff, 6, 6])

    def test_UXTW_shift_uses_X_result_not_u32_product(self):
        self.assertEqual(record_address(0x1000, 0, 0xffffffff), 0x400000ffc)

    def test_root_addition_wraps_at64(self):
        self.assertEqual(record_address((1 << 64)-16, 12, 2), 4)

    def test_fixture_requires_declared_widths(self):
        for args in ((True, 0, 0), (0, 65536, 0), (0, 0, -1), (0, 0, 1 << 32)):
            with self.assertRaises(ValueError):
                record_address(*args)


class RingTests(unittest.TestCase):
    def test_four_words_are_published_in_order(self):
        self.assertEqual(ring_addresses(0x203a000, 16, 3),
                         [0x203a030, 0x203a034, 0x203a038, 0x203a03c])

    def test_W_address_arithmetic_wraps_and_zero_extends(self):
        self.assertEqual(ring_addresses(0xfffffff8, 16, 0), [0xfffffff8, 0xfffffffc, 0, 4])
        self.assertEqual(ring_addresses(0, 16, 0x10000000), [0, 4, 8, 12])

    def test_no_capacity_guard_limits_index_in_address_formula(self):
        self.assertEqual(ring_addresses(0x1000, 16, 100)[0], 0x1640)

    def test_increment_wraps_before_remainder(self):
        self.assertEqual(advance(0xffffffff, 7), 0)
        self.assertNotEqual(advance(0xffffffff, 7), (0xffffffff+1) % 7)

    def test_zero_count_uses_UDIV_zero_semantics(self):
        self.assertEqual(advance(7, 0), 8)
        self.assertEqual(advance(0xffffffff, 0), 0)

    def test_count1_wraps_to_zero(self):
        self.assertEqual(advance(300, 1), 0)

    def test_doorbell_W_shift_masks_count_to5bits(self):
        self.assertEqual(doorbell(1), 0x20000)
        self.assertEqual(doorbell(17), 2)
        self.assertEqual(doorbell(0xffffffff), 0x8000)


class VectorProducerTests(unittest.TestCase):
    def test_selected_relative_offset_roundtrips_within16bits(self):
        v = relative_vector(0x211c800, 0x211cf04)
        self.assertTrue(v['exact'])
        self.assertEqual(v['offset16'], 0x704)

    def test_far_vector_truncates_and_does_not_roundtrip(self):
        v = relative_vector(0x1000, 0x11004)
        self.assertEqual(v['offset16'], 4)
        self.assertEqual(v['reconstructed'], 0x1004)
        self.assertFalse(v['exact'])

    def test_negative_relative_offset_is_not_sign_extended(self):
        v = relative_vector(0x1000, 0xffc)
        self.assertEqual(v['reconstructed'], 0x10ffc)
        self.assertFalse(v['exact'])

    def test_upper_MARGIN_byte_changes_do_not_change_packet_low24(self):
        for level in (3172, 2730, 421, 0xffffffff):
            values = {tuple(request_words(packed_level(byte<<24, level))) for byte in range(256)}
            self.assertEqual(len(values), 1)

    def test_packing_multiplies_in_W_and_clears_low3bits(self):
        self.assertEqual(packed_level(0xaa000007, 3172), 0xaa3066a0)
        self.assertEqual(packed_level(0, 0xffffffff), 0xfffc18)


class ReplyTests(unittest.TestCase):
    def test_nonzero_status_low_nibble_and_exact_zero_match(self):
        self.assertTrue(reply_matches(1, 0))
        self.assertTrue(reply_matches(0xffffffff, 0))

    def test_high_status_bits_do_not_release_poll(self):
        self.assertFalse(reply_matches(0x10, 0))
        self.assertFalse(reply_matches(0, 0))

    def test_whole_reply_word_must_match_masked_request(self):
        self.assertFalse(reply_matches(1, 1))
        self.assertFalse(reply_matches(1, 0x10000))
        self.assertTrue(reply_matches(1, 0x12340000, 0x12345678))
        self.assertFalse(reply_matches(1, 0x12340001, 0x12345678))

    def test_completed_reply_does_not_restore_published_memory(self):
        before = bytes(range(72)); buffer = bytearray(before)
        buffer[1] &= ~2
        queue = dict(zip(ring_addresses(0x1000, 16, 0), request_words(0xaa123456)))
        self.assertTrue(reply_matches(1, 0))
        buffer[:] = before
        self.assertEqual(buffer, before)
        self.assertEqual(queue[0x1004], 0x123456)
        # Independent RAM objects: restore alone cannot undo an earlier publication.


class MarkerAndConfigTests(unittest.TestCase):
    def test_selected_W1zero_sets_then_clears_byte25(self):
        stores = marker_stores(0, 0x1000, 0x1000)
        self.assertEqual([(s['address'], s['width'], s['value']) for s in stores],
                         [(0x1019, 1, 0x5a), (0x1019, 1, 0), (0x1014, 4, 0)])

    def test_nonzero_flag_skips_initial_marker_only(self):
        self.assertEqual(len(marker_stores(1, 0x1000, 0x1000)), 2)

    def test_changed_P_does_not_clear_original_marker(self):
        stores = marker_stores(0, 0x1000, 0x2000)
        mem = {}
        for s in stores:
            mem[s['address']] = s['value']
        self.assertEqual(mem[0x1019], 0x5a)
        self.assertEqual(mem[0x2019], 0)

    def test_zero_input_offset_is_not_a_null_runtime_table(self):
        c = channel_config(0, 0x100, 0x200, 8, 16)
        self.assertTrue(c['config_written'])
        self.assertEqual(c['table'], 0x02039000)
        self.assertEqual((c['tx'], c['rx']), (0x02039100, 0x02039200))

    def test_wrapped_zero_table_skips_publication(self):
        self.assertFalse(channel_config((-0x02039000)&0xffffffff, 1, 2, 8, 16)['config_written'])

    def test_runtime_table_fields_wrap_in_W(self):
        c = channel_config(1, 0xffffffff, 0xfffffffe, 0, 0)
        self.assertEqual((c['tx'], c['rx']), (0x02038fff, 0x02038ffe))
        self.assertEqual((c['count'], c['stride']), (0, 0))


def arithmetic_word(word, regs):
    """Independent raw-field decoder for selected A64 integer instructions only."""
    rd, rn, rm = word&31, (word>>5)&31, (word>>16)&31
    mask = (1 << (64 if word>>31 else 32))-1
    read = lambda reg: 0 if reg == 31 else regs.get(reg, 0)
    if word & 0x7fe0fc00 == 0x1ac00800:  # UDIV
        divisor = read(rm)&mask
        value = (read(rn)&mask)//divisor if divisor else 0
    elif word & 0x7fe0fc00 == 0x1ac02000:  # LSLV / LSL register alias
        value = (read(rn)&mask) << (read(rm)&(63 if word>>31 else 31))
    elif word & 0x7fe00000 == 0x1b000000:  # MADD / MSUB
        product = (read(rn)&mask)*(read(rm)&mask)
        addend = read((word>>10)&31)&mask
        value = addend-product if word & (1 << 15) else addend+product
    elif word & 0xffe00000 == 0x8b200000:  # ADD X, extended W UXTW
        if (word>>13)&7 != 2:
            raise ValueError('expected UXTW')
        value = read(rn)+((read(rm)&0xffffffff)<<((word>>10)&7))
    else:
        raise ValueError(f'unsupported fixture word {word:08x}')
    return rd, value&mask


class RealWordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((Path(__file__).resolve().parent.parent /
            'docs/references/newtime-method56-hzc2.json').read_text())
        cls.words = {int(w['pc'],16):int(w['word'],16) for w in cls.report['witnesses']}

    def test_real_request_ADD_preserves34bit_index_offset(self):
        for k in (0, 7, 255, 0x40000000, 0xffffffff):
            rd, value = arithmetic_word(self.words[0x17d38], {1:65535, 0:k})
            self.assertEqual((rd, value), (0, record_address(0, 65535, k)))

    def test_real_MADD_matches_wrapping_queue_address(self):
        for base in (0, 0x203a000, 0xfffffff8):
            for stride in (0, 16, 0xffffffff):
                for index in (0, 7, 0xffffffff):
                    rd, value = arithmetic_word(self.words[0x17c20], {4:index, 5:stride, 6:base})
                    self.assertEqual((rd, value), (5, ring_addresses(base,stride,index)[0]))

    def test_real_UDIV_MSUB_matches_advance_including_zero_and_wrap(self):
        for index in (0, 7, 0xfffffffe, 0xffffffff):
            for count in (0, 1, 8, 0xffffffff):
                regs = {4:(index+1)&0xffffffff, 1:count}
                rd, value = arithmetic_word(self.words[0x17c78], regs); regs[rd] = value
                self.assertEqual(arithmetic_word(self.words[0x17c7c],regs), (4, advance(index,count)))

    def test_real_doorbell_alias_uses_W_shift_mask(self):
        for channel in range(64):
            self.assertEqual(arithmetic_word(self.words[0x17ca4], {0:1,1:channel+16}),
                             (0, doorbell(channel)))

    def test_report_has_no_on_device_claim(self):
        self.assertFalse(self.report['firmware_executed'])
        self.assertFalse(self.report['physical_device_tested'])
        self.assertFalse(self.report['request']['direct_buffer_B_argument'])
        self.assertFalse(self.report['reply']['syntactic_timeout_or_retry_limit'])


if __name__ == '__main__':
    unittest.main()
