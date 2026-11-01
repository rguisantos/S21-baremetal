#!/usr/bin/env python3
"""Test distinct query times, OR semantics, bounded inputs and image refusals."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_ufs_iocc import inspect,select_table,selected_writes
from emulate_lk_ufs_iocc_qemu import run


class SelectionTests(unittest.TestCase):
    def test_zero_skips_second_query_and_selects_primary(self):
        self.assertEqual(select_table(0),0x303198)
        with self.assertRaisesRegex(ValueError,'not executed'):select_table(0,1)

    def test_nonzero_requires_and_uses_a_distinct_second_query(self):
        self.assertEqual(select_table(2,1),0x3038d8)
        self.assertEqual(select_table(1,0),0x303198)
        self.assertEqual(select_table(1,2),0x303198)
        with self.assertRaises(ValueError):select_table(1)

    def test_table_and_mask_can_disagree_under_supplied_changes(self):
        self.assertEqual(select_table(1,0),0x303198)
        self.assertEqual(selected_writes(0,0,1)['iocc_or_mask'],0x300000)
        self.assertEqual(select_table(1,1),0x3038d8)
        self.assertEqual(selected_writes(0,0,0)['iocc_or_mask'],0xc00000)

    def test_invalid_query_types_and_width_refused(self):
        for value in (-1,1 << 32,True,1.0,'1'):
            with self.subTest(value=value),self.assertRaises(ValueError):select_table(value,1)
            with self.subTest(second=value),self.assertRaises(ValueError):select_table(1,value)


class WriteTests(unittest.TestCase):
    def test_phy_bypass_sets_only_bit_zero(self):
        for old in (0,1,0xfffffffe,0xffffffff):
            with self.subTest(old=old):self.assertEqual(selected_writes(old,0,1)['phy_after'],old|1)

    def test_only_exact_u32_one_selects_alternate_or_mask(self):
        for query in (0,1,2,0x10001,0xffffffff):
            with self.subTest(query=query):
                self.assertEqual(selected_writes(0,0,query)['iocc_after'],0x300000 if query==1 else 0xc00000)

    def test_or_preserves_old_bits_in_the_other_mask(self):
        self.assertEqual(selected_writes(0,0xc00000,1)['iocc_after'],0xf00000)
        self.assertEqual(selected_writes(0,0x300000,0)['iocc_after'],0xf00000)
        self.assertEqual(selected_writes(0,0xffffffff,1)['iocc_after'],0xffffffff)

    def test_synthetic_null_pointer_skips_iocc_but_not_phy(self):
        r=selected_writes(0,0x12345678,1,enabled=False)
        self.assertEqual((r['phy_after'],r['iocc_after'],r['iocc_or_mask']),(1,0x12345678,0))
        self.assertFalse(r['iocc_store_executed'])

    def test_inputs_are_u32_and_gate_is_boolean(self):
        for args in ((-1,0,1),(0,1 << 32,1),(0,0,True),(False,0,0)):
            with self.subTest(args=args),self.assertRaises(ValueError):selected_writes(*args)
        for enabled in (0,1,None):
            with self.subTest(enabled=enabled),self.assertRaises(ValueError):selected_writes(0,0,1,enabled=enabled)


class RefusalTests(unittest.TestCase):
    def test_wrong_size_and_hash_fail_before_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.bin'
            for data in (b'bad',bytes(IMAGES['sboot'][0])):
                p.write_bytes(data)
                with self.subTest(size=len(data)),patch('inspect_lk_ufs_iocc.subprocess.check_output') as tool:
                    with self.assertRaisesRegex(ValueError,'unsupported image'):inspect(p)
                    tool.assert_not_called()

    def test_wrong_image_does_not_start_qemu(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.bin';p.write_bytes(b'bad')
            with patch('emulate_lk_ufs_iocc_qemu.subprocess.Popen') as launch:
                with self.assertRaisesRegex(ValueError,'unsupported image'):run(p)
                launch.assert_not_called()

    def test_cli_refusals_have_no_partial_json(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.bin';p.write_bytes(b'bad')
            for name in ('inspect_lk_ufs_iocc.py','emulate_lk_ufs_iocc_qemu.py'):
                r=subprocess.run([sys.executable,str(Path(__file__).with_name(name)),str(p)],capture_output=True,text=True,check=False)
                with self.subTest(script=name):
                    self.assertEqual((r.returncode,r.stdout),(2,''));self.assertIn('unsupported image',r.stderr)


if __name__=='__main__':unittest.main()
