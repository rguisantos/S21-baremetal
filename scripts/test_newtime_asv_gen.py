import struct
import unittest

from inspect_newtime_asv_gen_hzc2 import (
    gen_table, named_directory, parser_reservation, position_survey, request_tag, selected_gen, w19,
)


def block(name, columns, rows, cells):
    raw = name.encode() + b'\0'
    raw += b'\0' * ((-len(raw)) % 4)
    offset = 12 + 4 + len(raw) + 4
    return (struct.pack('<I4sII', 1, b'0.1 ', 1, len(name)) + raw
            + struct.pack('<III', offset, columns, rows)
            + struct.pack('<' + 'I'*len(cells), *cells))


class GenFormatTests(unittest.TestCase):
    def test_two_word_header_preserves_key_zero_and_enable2730(self):
        b = block('VMIF', 3, 2, [0, 2730, 421, 1, 3172, 421])
        _, _, entries = named_directory(b)
        t = gen_table(b, entries['VMIF'])
        self.assertEqual(t['data_offset'], entries['VMIF'] + 8)
        self.assertEqual(t['cells'], [[0, 2730, 421], [1, 3172, 421]])

    def test_directory_length_does_not_drop_final_character(self):
        _, _, entries = named_directory(block('MIF', 1, 1, [7]))
        self.assertIn('MIF', entries)
        self.assertNotIn('MI', entries)

    def test_four_character_name_includes_NUL_padding(self):
        _, _, entries = named_directory(block('MMIF', 1, 1, [7]))
        self.assertEqual(entries['MMIF'], 28)

    def test_truncated_cells_are_refused_by_host(self):
        b = block('X', 2, 2, [1, 2, 3])
        with self.assertRaises(ValueError):
            gen_table(b, named_directory(b)[2]['X'])

    def test_offset_into_directory_is_refused(self):
        b = bytearray(block('X', 1, 1, [7]))
        struct.pack_into('<I', b, 20, 12)
        with self.assertRaises(ValueError):
            named_directory(b)


class SelectionTests(unittest.TestCase):
    M = [[0, 0, 421, 2730, 2730, 421], [1, 0, 421, 2730, 2730, 421],
         [2, 0, 421, 2730, 2730, 421], [3, 0, 421, 3172, 3172, 421],
         [4, 4, 421, 3172, 3172, 421]]
    V = [[0, 2730], [1, 2730], [2, 2730], [3, 3172], [4, 3172]]

    def test_VMIF_key0_is_enabled(self):
        self.assertTrue(selected_gen(self.M, self.V, 0)['enabled'])

    def test_VINTSCI_zero_flags_do_not_disable_other_keys(self):
        v = [[0, 0], [1, 0], [2, 800]]
        self.assertFalse(selected_gen(self.M, v, 0)['enabled'])
        self.assertFalse(selected_gen(self.M, v, 1)['enabled'])
        self.assertTrue(selected_gen(self.M, v, 2)['enabled'])

    def test_F152_is_subkey_not_level421(self):
        self.assertEqual(selected_gen(self.M, self.V, 0)['F152'], 0)
        self.assertEqual(selected_gen(self.M, self.V, 4)['F152'], 4)

    def test_output_X4_is_column4_not_column5(self):
        self.assertEqual(selected_gen(self.M, self.V, 0)['out_X4'], 2730)

    def test_no_M_match_uses_last_row(self):
        out = selected_gen(self.M, self.V, 255)
        self.assertEqual(out['F152'], 4)
        self.assertFalse(out['enabled'])

    def test_zero_enable_first_match_does_not_search_duplicate(self):
        self.assertFalse(selected_gen(self.M, [[0, 0], [0, 3172]], 0)['enabled'])

    def test_compaction_keeps_keys_but_updates_first_row_fields(self):
        out = selected_gen(self.M, self.V, 0, compact=True)
        self.assertEqual(out['selected_M'][0], 0)
        self.assertEqual(out['F152'], 0)
        self.assertEqual(out['out_X4'], 3172)
        self.assertEqual(out['selected_V'], [0, 3172])

    def test_compaction_is_not_assumed_for_arbitrary_byte(self):
        with self.assertRaises(ValueError):
            selected_gen(self.M, self.V, 1, compact=True)


class NibbleAndPositionTests(unittest.TestCase):
    def test_signed_nibble_and_W_wrap(self):
        self.assertEqual(w19(0, 8), 0xfffffff8)
        self.assertEqual(w19(15, 7), 22)

    def test_range_is31_patterns_not_runtime_measurement(self):
        values = {w19(a, b) for a in range(16) for b in range(16)}
        signed = {v - (1 << 32) if v & 0x80000000 else v for v in values}
        self.assertEqual(signed, set(range(-8, 23)))

    def test_fixed_W19_reads13_but_union_covers156(self):
        r = position_survey(13, 12, 0, bytes(512), 156)
        self.assertEqual(r['per_fixed_W19_reads'], 13)
        self.assertEqual(r['union_distinct_inside_bytes'], 156)
        self.assertEqual(r['pair_counts'], dict(in_matrix=384, past_matrix=11, far_unsigned_offset=8))

    def test_adjacent_range_is11_addresses_inclusive(self):
        r = position_survey(13, 12, 0, bytes(512), 156)
        self.assertEqual([v['index'] for v in r['adjacent']], list(range(156, 167)))
        self.assertTrue(all(v['i'] == 12 for v in r['adjacent']))

    def test_header_plus4_boundary_is_not_the_full_bump_reservation(self):
        r = position_survey(13, 12, 0, bytes(512), 156)
        self.assertEqual(sum(v['within_header_total_plus4'] for v in r['adjacent']), 4)

    def test_header_is_allocated_before_the_total_plus4_increment(self):
        p = parser_reservation(0x69000, 0x110c4)
        self.assertEqual(p, dict(after_header=0x69010, after_total_plus4=0x7a0d8, end=0x7a0d8))

    def test_all11_adjacent_bytes_fit_selected_bump_but_not_matrix(self):
        r = position_survey(13, 12, 0, bytes(512), 156, bump_end=parser_reservation(0, 156)['end'])
        self.assertEqual(sum(v['within_parser_bump_reservation'] for v in r['adjacent']), 11)
        self.assertEqual(r['pair_counts']['past_matrix'], 11)

    def test_total_ffffffff_is_added_in_X_after_LDR_W(self):
        self.assertEqual(parser_reservation(0, 0xffffffff)['end'], 0x100000018)

    def test_nibble_host_bounds_do_not_silently_mask_bad_inputs(self):
        for v in (-1, 16, True):
            with self.assertRaises(ValueError):
                w19(v, 0)


class RequestTests(unittest.TestCase):
    def test_MOVK_replaces_low16_of_MOVN(self):
        self.assertEqual(request_tag(0x92a77fe1, 0xf2848001), 0xffffffffc4002400)
        self.assertEqual(request_tag(0x92a77fe1, 0xf2848041), 0xffffffffc4002402)

    def test_wrong_width_or_register_is_refused(self):
        for a, b in ((0x12a77fe1, 0xf2848001), (0x92a77fe2, 0xf2848001)):
            with self.assertRaises(ValueError):
                request_tag(a, b)


if __name__ == '__main__':
    unittest.main()
