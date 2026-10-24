#!/usr/bin/env python3
"""Conditional base-table controls; no live register values are assumed."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_bl2_query_base_rewrite import constructor, scenario, WRITE_START, WRITE_END


def fixture():
    values = [int(v, 16) for v in (
        'f0000001 d29e0002 913e6020 f2a38062 f907cc22 d29e0001 f2a38261 '
        'f9000401 91440021 f9000801 91440021 f9000c01 d29e0001 f2a34681 f9001001').split()]
    data = bytearray(WRITE_END)
    struct.pack_into('<15I', data, WRITE_START, *values)
    return data


class BaseRewriteTests(unittest.TestCase):
    def test_five_u64_writes_include_shifted_adds(self):
        stores = constructor(fixture())
        self.assertEqual([int(s['destination'], 16) for s in stores], list(range(0x30f98, 0x30fc0, 8)))
        self.assertEqual([int(s['value'], 16) for s in stores],
                         [0x1c03f000, 0x1c13f000, 0x1c23f000, 0x1c33f000, 0x1a34f000])
        self.assertTrue(all(s['width_bits'] == 64 for s in stores))

    def test_only_nibble_one_selects_the_writes(self):
        prior, stores = [1, 2, 3, 4, 5], constructor(fixture())
        for nibble in range(16):
            with self.subTest(nibble=nibble):
                s = scenario(prior, stores, nibble << 20)
                self.assertEqual(s['selected_body_writes'], nibble == 1)
                expected = [v['value'] for v in stores] if nibble == 1 else [hex(v) for v in prior]
                self.assertEqual(s['after'], expected)
                self.assertFalse(s['register_runtime_observed'])

    def test_skip_preserves_prior_rewrite_instead_of_restoring_file_values(self):
        stores = constructor(fixture())
        before = [0x1000]*5
        changed = scenario(before, stores, 1 << 20)['after']
        skipped = scenario([int(v, 16) for v in changed], stores, 0)
        self.assertEqual(skipped['after'], changed)
        self.assertEqual(before, [0x1000]*5)

    def test_other_register_bits_do_not_change_the_selected_nibble(self):
        stores = constructor(fixture())
        a = scenario([0]*5, stores, 0x00100000)
        b = scenario([0]*5, stores, 0xff1fffff)
        self.assertEqual(a['after'], b['after'])
        self.assertEqual(b['nibble_20_23'], 1)

    def test_register_word_requires_explicit_unsigned_w_value(self):
        for value in (True, None, -1, 1 << 32, '1', 1.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scenario([0]*5, constructor(fixture()), value)

    def test_prior_table_requires_five_explicit_u64_values(self):
        for prior in (None, [], [0]*4, [0]*6, [True]*5, [-1]*5, [1 << 64]*5):
            with self.subTest(prior=prior), self.assertRaises(ValueError):
                scenario(prior, constructor(fixture()), 0)

    def test_reads_calls_stack_and_32bit_stores_are_not_interpreted(self):
        for value in (0xf9400020, 0x94000000, 0xd4000003, 0xf81f0ffe, 0xb907cc22):
            data = fixture()
            struct.pack_into('<I', data, WRITE_START+16, value)
            with self.subTest(value=hex(value)), self.assertRaises(ValueError):
                constructor(data)

    def test_unknown_register_and_outside_table_store_refused(self):
        for offset, value in ((0, 0xf2a38061), (16, 0xf907c822)):
            data = fixture()
            struct.pack_into('<I', data, WRITE_START+offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                constructor(data)

    def test_duplicate_cell_truncation_alignment_and_budget_refused(self):
        data = fixture()
        struct.pack_into('<I', data, WRITE_END-4, 0xf9000c01)
        with self.assertRaises(ValueError):
            constructor(data)
        for raw, start, end in ((fixture()[:-1], WRITE_START, WRITE_END),
                                (fixture(), WRITE_START+1, WRITE_END),
                                (fixture(), WRITE_START-8, WRITE_END),
                                (fixture(), WRITE_START, WRITE_START)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                constructor(raw, start, end)

    def test_cli_refuses_wrong_image_or_partial_plan_without_json(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'bad.bin'
            p.write_bytes(b'unsupported')
            script = str(Path(__file__).with_name('inspect_bl2_query_base_rewrite.py'))
            for args in ([], ['--slot', '0'], ['--register-word', '0', '--slot', '0', '--term', '1']):
                r = subprocess.run([sys.executable, script, str(p), *args], capture_output=True, text=True)
                self.assertEqual(r.returncode, 2)
                self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()
