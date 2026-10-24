"""Host boundary tests for the NEWTIME wire reader and input matching."""
import struct
import unittest

from inspect_newtime_hzc2 import parse_newtime, selection


def fixture():
    # Two bodies with different cell widths; the extended tail exceeds u32.
    return (struct.pack('<I4sI', 1, b'0.81', 2)
            +struct.pack('<QI', 0x11111111, 36)+struct.pack('<QI', 0x108, 80)
            +struct.pack('<III4Q', 2, 2, 2, 0xcafe, 0x100000001, 0x1234, 7)
            +struct.pack('<III2I', 1, 2, 1, 0x11223344, 0xaabbccdd))


class NewtimeTests(unittest.TestCase):
    def test_cell_widths_keep_extended_high_word(self):
        tables = parse_newtime(fixture())['entries']
        self.assertEqual(tables[0]['cells'], (0xcafe, 0x100000001, 0x1234, 7))
        self.assertEqual(tables[1]['cells'], (0x11223344, 0xaabbccdd))

    def test_every_truncated_prefix_is_refused(self):
        raw = fixture()
        for length in range(len(raw)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parse_newtime(raw[:length])

    def test_version_count_and_host_size_bounds(self):
        for offset, values in ((0, (0, 2)), (8, (0, 257, 0xffffffff))):
            for value in values:
                raw = bytearray(fixture()); struct.pack_into('<I', raw, offset, value)
                with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                    parse_newtime(raw)
        with self.assertRaises(ValueError):
            parse_newtime(fixture()+bytes(0x14000))

    def test_body_must_follow_directory_and_be_aligned(self):
        for offset in (8, 35, 37, 100, 0xfffffffc):
            raw = bytearray(fixture()); struct.pack_into('<I', raw, 20, offset)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                parse_newtime(raw)

    def test_duplicate_keys_and_overlapping_bodies_are_refused(self):
        raw = bytearray(fixture()); struct.pack_into('<Q', raw, 24, 0x11111111)
        with self.assertRaises(ValueError):
            parse_newtime(raw)
        raw = bytearray(fixture()); struct.pack_into('<I', raw, 32, 36)
        with self.assertRaises(ValueError):
            parse_newtime(raw)

    def test_modes_and_signed_or_zero_dimensions_are_refused(self):
        for offset, values in ((36, (0, 3)), (40, (0, 513, 0xffffffff)), (44, (0, 513, 0xffffffff))):
            for value in values:
                raw = bytearray(fixture()); struct.pack_into('<I', raw, offset, value)
                with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                    parse_newtime(raw)

    def test_cells_cannot_exceed_body_even_with_bounded_dimensions(self):
        raw = bytearray(fixture()); struct.pack_into('<II', raw, 40, 512, 512)
        with self.assertRaises(ValueError):
            parse_newtime(raw)

    def test_input_must_be_an_unsigned_u64(self):
        table = parse_newtime(fixture())['entries'][0]
        for value in (True, -1, 1 << 64, '0xcafe', 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                selection(table, value)

    def test_signed_match_normalizes_key_but_keeps_store_input(self):
        table = parse_newtime(fixture())['entries'][0]
        value = 0x800000000000cafe
        match = selection(table, value)
        self.assertEqual((match['row'], match['comparison_key'], match['stored_input']), (0, 0xcafe, value))
        self.assertEqual(match['tail'], (0x100000001,))

    def test_nonnegative_high_bits_are_not_truncated_and_miss_stays_unknown(self):
        table = parse_newtime(fixture())['entries'][0]
        self.assertIsNone(selection(table, 0x100000000cafe))
        self.assertIsNone(selection(table, 0xdeadbeef))
        self.assertEqual(selection(table, 0x1234)['row'], 1)


if __name__ == '__main__':
    unittest.main()
