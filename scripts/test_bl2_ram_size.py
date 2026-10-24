#!/usr/bin/env python3
"""Host controls for explicit geometry; no physical RAM values are assumed."""
from pathlib import Path
import tempfile
import unittest

from inspect_bl2_ram_size import geometry, inspect, load_geometry, normalize_slots

TABLE = (256, 384, 512, 768, 1024, 1536, 2048)


class GeometryTests(unittest.TestCase):
    def test_disabled_gate_ignores_density_and_factor(self):
        self.assertEqual(geometry([0x61610030] * 4, TABLE)['total_bytes'], 0)

    def test_slot_zero_controls_term_count_for_all_slots(self):
        self.assertEqual(geometry([0x60000100, 0x61610130, 0, 0], TABLE)['total_mib'], 6144)
        self.assertEqual(geometry([0x60000130, 0x61610100, 0, 0], TABLE)['total_mib'], 10496)

    def test_only_factor_one_doubles(self):
        self.assertEqual(geometry([0x61000100, 0x62000100, 0, 0], TABLE)['total_mib'], 6144)

    def test_all_seven_table_entries_and_invalid_nibbles(self):
        for index in range(16):
            with self.subTest(index=index):
                expected = TABLE[index] if index < 7 else 0
                self.assertEqual(geometry([(index << 28) | 0x100, 0, 0, 0], TABLE)['total_mib'], expected)

    def test_high_bits_do_not_change_low_field_arithmetic(self):
        low = [0x61610130] * 4
        high = [v | 0xffffffff00000000 for v in low]
        self.assertEqual(geometry(low, TABLE)['total_bytes'], 32 << 30)
        self.assertEqual(geometry(high, TABLE)['total_bytes'], 32 << 30)
        self.assertFalse(geometry(high, TABLE)['free_memory_verified'])

    def test_gate_uses_all_eight_bits(self):
        self.assertEqual(geometry([0x60008000, 0, 0, 0], TABLE)['total_mib'], 2048)

    def test_four_explicit_unsigned_words_required(self):
        self.assertEqual(normalize_slots(['0xffffffffffffffff', '0', 1, 2]), ((1 << 64)-1, 0, 1, 2))
        for value in (None, {}, [], [0]*3, [0]*5, [True, 0, 0, 0],
                      [1.0, 0, 0, 0], [-1, 0, 0, 0], [1 << 64, 0, 0, 0],
                      ['bogus', 0, 0, 0], ['0'*33, 0, 0, 0], [[0], 0, 0, 0]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_slots(value)

    def test_table_width_count_and_types_refused(self):
        for table in (TABLE[:6], TABLE + (0,), (True,)*7, (65536,)*7, (-1,)*7):
            with self.subTest(table=table), self.assertRaises(ValueError):
                geometry([0]*4, table)

    def test_json_is_bounded_and_nested_values_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'geometry.json'
            path.write_text('["0x100", 0, 0, 0]')
            self.assertEqual(load_geometry(path), (0x100, 0, 0, 0))
            for raw in (' '*4097, '[[] ,0,0,0]', '['*1100 + '0' + ']'*1100,
                        '{"words":[0,0,0,0]}', '[0,0,0,0,]'):
                path.write_text(raw)
                with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                    load_geometry(path)

    def test_unsupported_sboot_refused_before_reporting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sboot.bin'
            for data in (b'', bytes(4194304), bytes(4194305)):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    inspect(path)


if __name__ == '__main__':
    unittest.main()
