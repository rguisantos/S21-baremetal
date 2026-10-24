"""Decoder/provenance boundaries. No firmware, hardware or success MMIO mocks."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_epbl_protocol import (MMIO, bounded_poll, constant_before, join_dma_pair, hash_counter_upload,
    download_words, logical_immediate, mmio_inventory, request_control,
    unsigned_access, upload_words)
from check_epbl_protocol_gnu import direct_target, parse_lines, text_mmio


def code(*words):
    return struct.pack('<' + 'I' * len(words), *words)


class Protocol(unittest.TestCase):
    def test_integer_transfer_widths_and_scaled_offsets(self):
        self.assertEqual(unsigned_access(0xb9400c41), ('read', 4, 1, 2, 12))
        self.assertEqual(unsigned_access(0xf9000c41), ('write', 8, 1, 2, 24))
        self.assertEqual(unsigned_access(0x39400c41), ('read', 1, 1, 2, 3))

    def test_signed_load_vector_and_writeback_are_outside_decoder(self):
        for w in (0xb9800041, 0x3dc00041, 0xb8404441):
            self.assertIsNone(unsigned_access(w))

    def test_logical_literal_decodes_rotated_mask_and_width(self):
        self.assertEqual(logical_immediate(0x32161be2), (1, 32, 2, 31, 0x1fc00))
        self.assertEqual(logical_immediate(0x121e7400)[-1], 0xfffffffc)

    def test_reserved_logical_masks_are_rejected(self):
        for w in (0x12400000, 0x1200fc00, 0x1200f800):
            with self.assertRaises(ValueError):
                logical_immediate(w)

    def test_x_literal_preserves_upper_address_bits(self):
        data = code(0xd2800000, 0xf2c00020)
        self.assertEqual(constant_before(data, 8, 0, lower=0), 1 << 32)

    def test_movk_patches_only_selected_halfword(self):
        data = code(0xd2803180, 0xf2a30660)
        self.assertEqual(constant_before(data, 8, 0, lower=0), MMIO + 0x18c)

    def test_later_w_write_zero_extends_x_value(self):
        data = code(0xd2800000, 0xf2c00020, 0x52800040)
        self.assertEqual(constant_before(data, 12, 0, lower=0), 2)

    def test_movk_without_known_base_stays_unknown(self):
        self.assertIsNone(constant_before(code(0xf2a30660), 4, 0, lower=0))

    def test_literal_slice_stops_at_branch(self):
        self.assertIsNone(constant_before(code(0xd2803180, 0x14000001), 8, 0, lower=0))

    def test_mmio_read_is_unknown_not_a_success_value(self):
        self.assertIsNone(constant_before(code(0xd2803180, 0xf2a30660, 0xb9400000), 12, 0, lower=0))

    def test_unrelated_load_can_be_skipped_without_using_its_value(self):
        data = code(0xd2803180, 0xf2a30660, 0xb94003a1)
        self.assertEqual(constant_before(data, 12, 0, lower=0), MMIO + 0x18c)
        self.assertIsNone(constant_before(data, 12, 1, lower=0))

    def test_unknown_operation_does_not_preserve_stale_literal(self):
        self.assertIsNone(constant_before(code(0xd2803180, 0x9ac02000), 8, 0, lower=0))

    def test_slice_bounds_and_budget_are_enforced(self):
        data = code(0xd2803180, 0xf2a30660)
        self.assertIsNone(constant_before(data, 8, 0, lower=0, budget=1))
        for kwargs in ({'budget': True}, {'budget': 0}, {'lower': 1}):
            with self.assertRaises(ValueError):
                constant_before(data, 8, 0, **({'lower': 0} | kwargs))

    def test_inventory_proves_address_and_keeps_unknown_data(self):
        data = code(0xd2803180, 0xf2a30660, 0xb9000001)
        result = mmio_inventory(data, ((0, 12),))
        self.assertEqual(result[0]['address'], '0x1833018c')
        self.assertIsNone(result[0]['literal_write_value'])

    def test_zero_data_is_distinct_from_unknown_data(self):
        data = code(0xd2803180, 0xf2a30660, 0xb900001f)
        self.assertEqual(mmio_inventory(data, ((0, 12),))[0]['literal_write_value'], '0x0')

    def test_sp_is_not_treated_as_zero_mmio_address(self):
        self.assertEqual(mmio_inventory(code(0xb9000fff), ((0, 4),)), [])

    def test_branch_into_builder_cannot_reuse_bypassed_movz(self):
        data = code(0x14000002, 0xd2803180, 0xf2a30660, 0xb9000001)
        self.assertEqual(mmio_inventory(data, ((0, 16),)), [])

    def test_outside_mmio_window_is_not_classified_as_device(self):
        self.assertEqual(mmio_inventory(code(0xd2803180, 0xb9000001), ((0, 8),)), [])

    def test_upload_binds_frame_source_and_target_register(self):
        data = code(0xd2822000, 0xf2a30660, 0xb9408ba1, 0xb9000001)
        self.assertEqual(upload_words(data, 0, 1, 0x1100, 0x88)[0]['frame_offset'], '0x88')
        corrupt = bytearray(data); struct.pack_into('<I', corrupt, 12, 0xb9000002)
        with self.assertRaises(ValueError):
            upload_words(corrupt, 0, 1, 0x1100, 0x88)

    def test_download_does_not_invent_missing_output_words(self):
        data = code(0xd2823800, 0xf2a30660, 0xb9400000, 0xb9005ba0)
        self.assertEqual(len(download_words(data, 0, 1, 0x58)), 1)
        with self.assertRaises((ValueError, struct.error)):
            download_words(data, 0, 2, 0x58)

    def test_consumer_control_selectors_stay_distinct(self):
        self.assertEqual(request_control(32, 1, 1), 0xfab)
        self.assertEqual(request_control(16, 0, 0), 0xf88)
        self.assertEqual(request_control(24, 3, 1), 0xf9d)
        self.assertEqual(request_control(32, 1, 1), request_control(32, 2, 1))

    def test_dma_pair_does_not_confuse_low_address_with_size(self):
        self.assertEqual(join_dma_pair(0, 0x1fc00, 0x3fc), (0x1fc00, 0x1fffc))

    def test_dma_pair_preserves_high_word(self):
        self.assertEqual(join_dma_pair(8, 0x80000000, 512), (0x880000000, 0x880000200))

    def test_dma_pair_refuses_invalid_words_and_overflow(self):
        for args in ((True, 0, 0), (-1, 0, 0), (0, 1 << 32, 1), (0xffffffff, 0xffffffff, 2)):
            with self.assertRaises(ValueError):
                join_dma_pair(*args)

    def test_hash_counter_words_are_bound_to_the_correct_registers(self):
        data = code(0xd2820604, 0xf2a30664, 0xb9404428, 0xb9000088,
                    0xd2820684, 0xf2a30664, 0xb9404028, 0xb9000088)
        result = hash_counter_upload(data, 0)
        self.assertEqual([(r['context_offset'], r['mmio_offset']) for r in result],
                         [('0x44', '0x1030'), ('0x40', '0x1034')])

    def test_hash_counter_swapped_loads_are_rejected(self):
        data = code(0xd2820604, 0xf2a30664, 0xb9404028, 0xb9000088,
                    0xd2820684, 0xf2a30664, 0xb9404428, 0xb9000088)
        with self.assertRaises(ValueError):
            hash_counter_upload(data, 0)

    def test_selector_inputs_are_explicit_unsigned_values(self):
        for args in ((True, 1, 1), (15, 1, 1), (32, -1, 1), (32, 4, 1), (32, 1, True)):
            with self.assertRaises(ValueError):
                request_control(*args)

    def test_poll_limit_is_inclusive_not_elapsed_time(self):
        result = bounded_poll(code(0xd503201f, 0x7144001f, 0x54ffffc9), 4, 8, 'fixture', 'synthetic')
        self.assertEqual(result['unsuccessful_reads_before_limit_exit'], 0x100001)
        self.assertFalse(result['actual_status_observed'])
        self.assertFalse(result['elapsed_time_known'])

    def test_poll_rejects_different_branch_condition(self):
        with self.assertRaises(ValueError):
            bounded_poll(code(0x7144001f, 0x54ffffe8), 0, 4, 'fixture', 'synthetic')

    def test_wrong_firmware_cli_emits_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sboot.bin'; path.write_bytes(b'wrong firmware')
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('inspect_epbl_protocol.py')), str(path)], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(result.stdout)

    def test_gnu_parser_rejects_duplicate_addresses(self):
        with self.assertRaises(ValueError):
            parse_lines('0: d65f03c0 ret\n0: d65f03c0 ret\n')

    def test_gnu_target_handles_bit_and_condition_operands(self):
        self.assertEqual(direct_target('tbz', 'w0, #10, 0x312c'), 0x312c)
        self.assertEqual(direct_target('b.eq', '0x3a7c'), 0x3a7c)
        self.assertIsNone(direct_target('blr', 'x15'))

    def test_gnu_text_walk_resolves_mmio_without_binary_decoder(self):
        rows = parse_lines('0: d2803180 mov x0, #0x18c\n4: f2a30660 movk x0, #0x1833, lsl #16\n8: b9400000 ldr w0, [x0]\n')
        self.assertEqual(text_mmio(rows), [(8, 'read', 4, MMIO + 0x18c)])

    def test_gnu_text_does_not_reuse_mmio_read_as_pointer(self):
        rows = parse_lines('0: d2803180 mov x0, #0x18c\n4: f2a30660 movk x0, #0x1833, lsl #16\n8: b9400000 ldr w0, [x0]\nc: b9400000 ldr w0, [x0]\n')
        self.assertEqual(len(text_mmio(rows)), 1)

    def test_gnu_branch_target_discards_bypassed_builder(self):
        rows = parse_lines('0: 14000002 b 0x8\n4: d2803180 mov x0, #0x18c\n8: f2a30660 movk x0, #0x1833, lsl #16\nc: b9000001 str w1, [x0]\n')
        self.assertEqual(text_mmio(rows), [])


if __name__ == '__main__':
    unittest.main()
