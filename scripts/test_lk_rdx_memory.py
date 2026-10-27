#!/usr/bin/env python3
"""Independent boundary cases for the static RDX bank/pair model; no firmware needed."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_lk_rdx_memory_hzc2 import append_pairs, producer_banks, pointers


class Banks(unittest.TestCase):
    def test_zero_still_has_first_store(self):
        self.assertEqual(producer_banks(0), [(0x80000000, 0x20000000)])
        self.assertEqual(append_pairs(producer_banks(0), 0), [])

    def test_low_banks_and_high_discontinuity(self):
        self.assertEqual(producer_banks(5), [
            (0x80000000, 0x20000000), (0xa0000000, 0x20000000),
            (0xc0000000, 0x20000000), (0xe0000000, 0x20000000),
            (0x880000000, 0x20000000)])

    def test_explicit_24_unit_example(self):
        banks = producer_banks(24)
        self.assertEqual(len(banks), 24)
        self.assertEqual(banks[-1], (0xae0000000, 0x20000000))
        self.assertEqual(sum(size for _, size in banks), 12 * 1024**3)

    def test_count_types_and_host_budget(self):
        for count in (-1, 65, True, False, 2.0, '24', None, 0xffffffff):
            with self.subTest(count=count), self.assertRaises(ValueError):
                producer_banks(count)

    def test_one_unit_does_not_invent_second_size(self):
        row, = append_pairs(producer_banks(1), 1)
        self.assertFalse(row['second_size_known'])
        self.assertIsNone(row['size'])
        self.assertIsNone(row['inclusive_end'])
        self.assertIsNone(row['probe_envelope_contained'])

    def test_first_pair_contains_entire_candidate_envelope(self):
        row, = append_pairs(producer_banks(2), 2)
        self.assertEqual((row['start'], row['size'], row['inclusive_end']),
                         ('0x80000000', 0x40000000, '0xbfffffff'))
        self.assertTrue(row['source_pair_contiguous'])
        self.assertTrue(row['probe_envelope_contained'])

    def test_pair_after_low_four_is_high(self):
        rows = append_pairs(producer_banks(6), 6)
        self.assertEqual([r['start'] for r in rows], ['0x80000000', '0xc0000000', '0x880000000'])
        self.assertEqual([r['inclusive_end'] for r in rows], ['0xbfffffff', '0xffffffff', '0x8bfffffff'])
        self.assertEqual([r['probe_envelope_contained'] for r in rows], [True, False, False])

    def test_24_units_give_12_pairs(self):
        rows = append_pairs(producer_banks(24), 24)
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(r['size'] for r in rows), 12 * 1024**3)
        self.assertEqual(rows[-1]['inclusive_end'], '0xaffffffff')
        self.assertTrue(all(r['source_pair_contiguous'] for r in rows))

    def test_odd_last_pair_remains_unknown(self):
        rows = append_pairs(producer_banks(5), 5)
        self.assertEqual(len(rows), 3)
        self.assertIsNone(rows[-1]['size'])
        self.assertEqual(rows[-1]['start'], '0x880000000')

    def test_explicit_extra_size_can_resolve_odd_read(self):
        row, = append_pairs([(0x80000000, 0x20000000), (0xa0000000, 0x123)], 1)
        self.assertEqual(row['size'], 0x20000123)
        self.assertTrue(row['second_size_known'])

    def test_size_sum_does_not_imply_contiguity(self):
        row, = append_pairs([(0x80000000, 0x20000000), (0xe0000000, 0x20000000)], 2)
        self.assertEqual(row['inclusive_end'], '0xbfffffff')
        self.assertFalse(row['source_pair_contiguous'])

    def test_modular_size_sum_and_end_not_validated_as_span(self):
        row, = append_pairs([(0xfffffffffffffff0, 8), (0, 32)], 2)
        self.assertEqual(row['inclusive_end'], '0x17')
        self.assertIsNone(row['probe_envelope_contained'])
        row, = append_pairs([(0x80000000, 0xffffffffffffffff), (0, 1)], 2)
        self.assertEqual(row['size'], 0)
        self.assertEqual(row['inclusive_end'], '0x7fffffff')
        self.assertIsNone(row['probe_envelope_contained'])

    def test_incomplete_or_invalid_source(self):
        for source, count in (([], 2), ([(0, -1)], 1), ([(True, 1)], 1), ([(0, 1 << 64)], 1)):
            with self.subTest(source=source), self.assertRaises(ValueError):
                append_pairs(source, count)


class OperationSlots(unittest.TestCase):
    def fixture(self):
        data = bytearray(0x70)
        for slot, target in ((0, 0x116960), (0x38, 0x114fe0), (0x48, 0x114c18), (0x68, 0x113958)):
            struct.pack_into('<Q', data, slot, 0xe7f14000+target)
        return data

    def test_independent_slot_layout(self):
        rows = pointers(self.fixture(), table=0)
        self.assertEqual([r['nominal_file_target'] for r in rows],
                         ['0x116960', '0x114fe0', '0x114c18', '0x113958'])

    def test_wrong_and_truncated_pointer_table(self):
        bad = self.fixture(); bad[0x38] ^= 1
        for data in (bad, self.fixture()[:-1]):
            with self.assertRaises(ValueError):
                pointers(data, table=0)


class Identity(unittest.TestCase):
    def test_cli_refuses_before_objdump(self):
        script = Path(__file__).with_name('inspect_lk_rdx_memory_hzc2.py')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'wrong.bin'
            for payload in (b'', bytes(4194304)):
                path.write_bytes(payload)
                result = subprocess.run([sys.executable, str(script), str(path)], capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'inspect_lk_rdx_memory_hzc2:', result.stderr)
                self.assertEqual(path.read_bytes(), payload)


if __name__ == '__main__':
    unittest.main()
