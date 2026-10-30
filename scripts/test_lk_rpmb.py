#!/usr/bin/env python3
"""Test bounded RPMB dispatch decoding and secure-request bindings on the host."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_rpmb import gate_locations, halfword_targets, inspect, mac_fields


def table_fixture(values):
    data = bytearray(1024)
    struct.pack_into('<'+'h'*len(values), data, 800, *values)
    return data


class HalfwordTests(unittest.TestCase):
    def test_signed_offsets_scale_by_four_from_code_base(self):
        rows = halfword_targets(table_fixture([0, 1, -1]), 800, 3, 256, 0, 768)
        self.assertEqual([r['target'] for r in rows], ['0x100', '0x104', '0xfc'])
        self.assertEqual([r['signed_halfword'] for r in rows], [0, 1, -1])

    def test_little_endian_halfwords_are_not_signed_bytes(self):
        data = bytearray(0x40000); data[0:4] = b'\x00\x01\x00\xff'
        rows = halfword_targets(data, 0, 2, 0x20000, 0, len(data))
        self.assertEqual([r['target'] for r in rows], ['0x20400', '0x1fc00'])

    def test_extreme_signed_values(self):
        data = bytearray(0x40000); struct.pack_into('<hh', data, 0, -32768, 32767)
        self.assertEqual([r['target'] for r in halfword_targets(data, 0, 2, 0x20000, 0, len(data))],
                         ['0x0', '0x3fffc'])

    def test_target_bounds_are_half_open(self):
        self.assertEqual(halfword_targets(table_fixture([-64]), 800, 1, 256, 0, 768)[0]['target'], '0x0')
        for value in (-65, 128):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'outside code'):
                halfword_targets(table_fixture([value]), 800, 1, 256, 0, 768)

    def test_duplicates_and_order_are_preserved(self):
        rows = halfword_targets(table_fixture([2, -1, 2]), 800, 3, 256, 0, 768)
        self.assertEqual([r['index'] for r in rows], [0, 1, 2])
        self.assertEqual([r['target'] for r in rows], ['0x108', '0xfc', '0x108'])

    def test_invalid_types_alignment_and_counts_are_refused(self):
        for table, count, base, low, high in ((-2, 1, 256, 0, 768), (801, 1, 256, 0, 768),
                (800, 0, 256, 0, 768), (800, 257, 256, 0, 768),
                (800, 1, 257, 0, 768), (800, 1, 256, 1, 768),
                (800, 1, 256, 0, 767), (800, 1, 256, 0, 1028),
                (800, 1, 768, 0, 768), (800, True, 256, 0, 768),
                (800, 1.0, 256, 0, 768)):
            with self.subTest(table=table, count=count, base=base, low=low, high=high), self.assertRaisesRegex(ValueError, 'bounds'):
                halfword_targets(table_fixture([0]), table, count, base, low, high)

    def test_truncated_table_is_refused(self):
        for table, count in ((1024, 1), (1022, 2), (1026, 1)):
            with self.subTest(table=table, count=count), self.assertRaisesRegex(ValueError, 'bounds'):
                halfword_targets(bytes(1024), table, count, 256, 0, 768)

    def test_maximum_allowed_count_and_exact_table_end(self):
        rows = halfword_targets(bytes(1024), 512, 256, 256, 0, 512)
        self.assertEqual(len(rows), 256)
        self.assertEqual(rows[-1]['index'], 255)


class BindingTests(unittest.TestCase):
    def test_mac_descriptor_fields_are_input_length_output(self):
        fields = mac_fields({0x109df8: 0xa9005eb3, 0x109df4: 0xf9000aa2})
        self.assertEqual(list(fields), ['0', '8', '16'])
        self.assertIn('input pointer', fields['0'])
        self.assertIn('input length', fields['8'])
        self.assertIn('output MAC pointer', fields['16'])

    def test_pair_source_base_offset_mutations_are_refused(self):
        for bit in (1, 1 << 10, 1 << 5, 1 << 15):
            with self.subTest(bit=bit), self.assertRaisesRegex(ValueError, 'binding'):
                mac_fields({0x109df8: 0xa9005eb3^bit, 0x109df4: 0xf9000aa2})

    def test_single_source_base_offset_mutations_are_refused(self):
        for bit in (1, 1 << 5, 1 << 10):
            with self.subTest(bit=bit), self.assertRaisesRegex(ValueError, 'binding'):
                mac_fields({0x109df8: 0xa9005eb3, 0x109df4: 0xf9000aa2^bit})

    def test_wrong_store_width_and_address_form_are_refused(self):
        for pair, single in ((0x29005eb3, 0xf9000aa2), (0xa9005eb3, 0xb9000aa2),
                             (0xa9005eb3, 0xf9400aa2)):
            with self.subTest(pair=pair, single=single), self.assertRaises(ValueError):
                mac_fields({0x109df8: pair, 0x109df4: single})

    def test_both_frontends_use_same_gate_distinct_from_provisioning(self):
        locations = gate_locations({0x10ada0: 0x90003ce4, 0x10ada4: 0xb9436884,
                                    0x10ade0: 0x90003ce4, 0x10ade4: 0xb9436884})
        self.assertEqual(locations, {'read': '0x8a6368', 'write': '0x8a6368'})
        self.assertNotEqual(locations['read'], '0x8a6370')

    def test_gate_width_or_base_mutation_is_refused(self):
        for load in (0xb9436884^32, 0xf9436884):
            with self.subTest(load=load), self.assertRaises(ValueError):
                gate_locations({0x10ada0: 0x90003ce4, 0x10ada4: load,
                                0x10ade0: 0x90003ce4, 0x10ade4: 0xb9436884})


class RefusalTests(unittest.TestCase):
    def test_bad_size_and_bad_digest_refused_before_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'
            for content in (b'bad', bytes(IMAGES['sboot'][0])):
                path.write_bytes(content)
                with self.subTest(size=len(content)), patch('inspect_lk_rpmb.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError, 'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_failure_emits_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'; path.write_bytes(b'bad')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('inspect_lk_rpmb.py')), str(path)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
