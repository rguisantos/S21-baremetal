#!/usr/bin/env python3
"""Independent table/FDT fixtures for the HZC2 selector; no firmware binaries."""
import struct
import unittest

from check_lk_dtb_selection import audit, parse_table, select
from test_fdt import encode, node, text, u32


def table(ranges, blob=None, encoding='big'):
    blob = blob or encode(node('', {'marker': u32(123)}))
    start = 32+32*len(ranges)
    total = start+len(blob)*len(ranges)
    data = bytearray(struct.pack('>8I', 0xd7b7ab1e, total, 32, 32,
                                 len(ranges), 32, 2048, 0))
    for index, (lo, hi) in enumerate(ranges):
        data.extend(struct.pack('>4I', len(blob), start+index*len(blob), 0, 0))
        data.extend(lo.to_bytes(4, encoding)+hi.to_bytes(4, encoding)+bytes(8))
    data.extend(blob*len(ranges))
    return data


class SelectionTest(unittest.TestCase):
    def test_inclusive_ranges_first_match_and_gaps(self):
        parsed = parse_table(table([(2, 15), (16, 16), (22, 32)]))
        for revision, expected in ((2, 0), (15, 0), (16, 1), (22, 2), (32, 2)):
            self.assertEqual(select(parsed, revision)['index'], expected)
        for revision in (0, 1, 17, 33, -1, 0x100000000):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                select(parsed, revision)
        overlap = parse_table(table([(0, 255), (16, 16)]))
        self.assertEqual(select(overlap, 16)['index'], 0)

    def test_little_endian_range_branch(self):
        parsed = parse_table(table([(2, 32)], encoding='little'))
        entry = select(parsed, 16)
        self.assertEqual((entry['revision_min'], entry['revision_max'], entry['range_encoding']),
                         (2, 32, 'little'))

    def test_threshold_follows_instruction_branch_not_desired_endianness(self):
        small = parse_table(table([(0, 255)]))['entries'][0]
        large = parse_table(table([(0, 256)]))['entries'][0]
        self.assertEqual((small['range_encoding'], small['revision_max']), ('big', 255))
        self.assertEqual((large['range_encoding'], large['revision_max']), ('little', 65536))

    def test_unsigned_range_and_inverted_effective_range(self):
        parsed = parse_table(table([(0x80000000, 0xffffffff)], encoding='little'))
        self.assertEqual(select(parsed, 0xfffffffe)['index'], 0)
        with self.assertRaisesRegex(ValueError, 'inverted'):
            parse_table(table([(10, 2)]))

    def test_bad_headers_entries_and_payloads(self):
        changes = [(0, 0), (4, 0xffffffff), (8, 0), (12, 64), (16, 0),
                   (16, 129), (20, 64), (28, 1), (32, 0xffffffff), (36, 0)]
        for off, value in changes:
            data = table([(0, 255)])
            struct.pack_into('>I', data, off, value)
            with self.subTest(offset=off, value=value), self.assertRaises(ValueError):
                parse_table(data)
        data = table([(0, 255)])
        for end in (0, 31, 63, len(data)-1):
            with self.subTest(end=end), self.assertRaises(ValueError):
                parse_table(data[:end])
        data[64] = 0
        with self.assertRaises(ValueError):
            parse_table(data)

    def test_vendor_region_and_dpm_symbol_resolution(self):
        base = encode(node('', children=[node('dpm'),
                      node('__symbols__', {'dpm': text('/dpm')})]))
        region = table([(0, 255)], base)
        vendor = bytearray(4096)+region
        vendor[:8] = b'VNDRBOOT'
        struct.pack_into('<II', vendor, 8, 3, 4096)
        struct.pack_into('<II', vendor, 2096, 2112, len(region))
        dpm = encode(node('', children=[node('__fixups__', {'dpm': text('/fragment@0:target:0')})]))
        report = audit(vendor, table([(2, 32)]), dpm, 16)
        self.assertEqual(report['dpm']['target_symbols']['dpm']['base_target'], '/dpm')
        self.assertFalse(report['overlay_merge_performed'])
        self.assertFalse(report['is_final_fdt'])
        self.assertEqual(report['vendor_region_offset'], '0x1000')
        with self.assertRaises(ValueError):
            audit(vendor[:-1], table([(2, 32)]), dpm, 16)
        missing = encode(node('', children=[node('__fixups__', {'absent': text('/fragment@0:target:0')})]))
        with self.assertRaisesRegex(ValueError, 'symbol'):
            audit(vendor, table([(2, 32)]), missing, 16)


if __name__ == '__main__':
    unittest.main()
