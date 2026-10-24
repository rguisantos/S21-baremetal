#!/usr/bin/env python3
"""Structural controls for record provenance, without supplied geometry bytes."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from check_bl2_geometry_record_gnu import text_wide
from inspect_bl2_geometry_record import PREFIX, RELOAD, copied_span, field_copy, reloads, wide64


def fixture():
    data = bytearray(0x2d800)
    for start, values in ((0x2d364, PREFIX), (0x2d7d0, RELOAD)):
        values = [int(v, 16) for v in values.split()]
        struct.pack_into('<'+'I'*len(values), data, start, *values)
    struct.pack_into('<I', data, 0x2d5ac, 0x90000026)
    struct.pack_into('<I', data, 0x2d6d0, 0x911a20d3)
    return data


class GeometryRecordTests(unittest.TestCase):
    def test_two_reloads_have_one_unknown_source_and_matching_state_cells(self):
        r = reloads(fixture())
        self.assertEqual([v['source_address'] for v in r], ['0x2073600']*2)
        self.assertEqual([v['geometry_cell'] for v in r], ['0x31978']*2)
        self.assertEqual([v['mode_cell'] for v in r], ['0x31939']*2)
        self.assertTrue(all(v['geometry_value'] == 'unknown_record_u64' for v in r))
        self.assertTrue(all(v['source_width_bits'] == 64 and v['mode_source_bits'] == [4, 7] for v in r))

    def test_reload_refuses_changed_load_width_store_register_or_field(self):
        for pc, value in ((0x2d378, 0xb9400021), (0x2d37c, 0xf9017840),
                          (0x2d384, 0xd3451c63), (0x2d7e0, 0xb9400000),
                          (0x2d7fc, 0xb902ae60), (0x2d6d0, 0x911a20b3)):
            data = fixture()
            struct.pack_into('<I', data, pc, value)
            with self.subTest(pc=hex(pc)), self.assertRaises(ValueError):
                reloads(data)

    def test_reload_refuses_truncated_prefix_or_context(self):
        for data in (fixture()[:0x2d364], fixture()[:0x2d5ac], fixture()[:-1]):
            with self.assertRaises(ValueError):
                reloads(data)

    def test_selected_move_wide_producers_include_high_halves(self):
        data = struct.pack('<4I', 0xd2802202, 0xf2ac0002, 0xf2c00102, 0xf2e00022)
        self.assertEqual(wide64(data, (0, 4, 8, 12), 2), 0x0001000860000110)
        self.assertEqual(wide64(struct.pack('<I', 0xd2995fc0), (0,), 0), 0xcafe)

    def test_move_wide_requires_x_width_initial_movz_and_one_register(self):
        for values in ((0x5286c000,), (0xf2a040e0,), (0xd286c000, 0xf2a040e1)):
            data = struct.pack('<'+'I'*len(values), *values)
            with self.assertRaises(ValueError):
                wide64(data, tuple(range(0, len(data), 4)), 0)
        for offsets, register in (((), 0), ((0, 0), 0), ((4, 0), 0), ((0,), 31), ((0,), True)):
            with self.assertRaises(ValueError):
                wide64(struct.pack('<2I', 0xd286c000, 0xf2a040e0), offsets, register)

    def test_gnu_text_requires_an_initial_move_and_matching_x_register(self):
        lines = {0: (0, 'mov', 'x0, #0x3600'), 4: (0, 'movk', 'x0, #0x207, lsl #16')}
        self.assertEqual(text_wide(lines, (0, 4), 0), 0x2073600)
        for offsets, register in (((), 0), ((4,), 0), ((0, 4), 1)):
            with self.assertRaises(ValueError):
                text_wide(lines, offsets, register)

    def test_field_copy_preserves_source_and_destination_without_values(self):
        data = struct.pack('<6I', 0xd296c500, 0xf2a04340, 0xb9400001,
                           0xd286c500, 0xf2a040e0, 0xb9000001)
        r = field_copy(data, 0)
        self.assertEqual((r['source'], r['destination'], r['width_bits']), ('0x21ab628', '0x2073628', 32))
        self.assertFalse(r['touches_first_record_u64'])
        self.assertNotIn('value', r)

    def test_field_copy_checks_overlap_at_the_first_word_boundary(self):
        for low, overlaps in ((0x3600, True), (0x3604, True), (0x3608, False)):
            data = struct.pack('<6I', 0xd296c500, 0xf2a04340, 0xb9400001,
                               0xd2800000 | (low << 5), 0xf2a040e0, 0xb9000001)
            self.assertEqual(field_copy(data, 0)['touches_first_record_u64'], overlaps)

    def test_field_copy_refuses_x_or_byte_transfers_and_changed_base(self):
        for index, value in ((2, 0xf9400001), (2, 0xb9400021), (5, 0x39000001)):
            values = [0xd296c500, 0xf2a04340, 0xb9400001, 0xd286c500, 0xf2a040e0, 0xb9000001]
            values[index] = value
            with self.assertRaises(ValueError):
                field_copy(struct.pack('<6I', *values), 0)

    def test_conditional_copy_span_is_not_a_file_mapping_or_observed_bytes(self):
        copy = dict(source=['0x203d000', '0x207a000'], destination=['0x2175000', '0x21b2000'])
        r = copied_span(copy, 0x2073600, 8)
        self.assertEqual(r['destination'], '0x21ab600')
        self.assertFalse(r['execution_observed'])
        self.assertFalse(r['source_bytes_observed'])
        self.assertNotIn('file_offset', r)

    def test_copy_span_refuses_crossing_end_zero_size_and_unsigned_errors(self):
        copy = dict(source=['0x1000', '0x2000'], destination=['0x4000', '0x5000'])
        for address, size in ((0x1ffc, 8), (0x2000, 1), (0x1000, 0), (-1, 8), (True, 8), (0x1000, 1 << 64)):
            with self.subTest(address=address, size=size), self.assertRaises(ValueError):
                copied_span(copy, address, size)

    def test_cli_rejects_wrong_firmware_without_partial_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'bad.bin'
            for raw in (b'bad', bytes(4194305)):
                p.write_bytes(raw)
                r = subprocess.run([sys.executable, str(Path(__file__).with_name('inspect_bl2_geometry_record.py')), str(p)],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 2)
                self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()
