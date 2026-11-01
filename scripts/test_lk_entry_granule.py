#!/usr/bin/env python3
"""Check inherited-TCR semantics, census boundaries and fail-before-tool contracts."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_entry_granule import granule_from_tcr, inspect, tcr_writers
from emulate_lk_entry_granule_qemu import run


class GranuleTests(unittest.TestCase):
    def test_three_encodings_have_non_monotonic_sizes(self):
        self.assertEqual([granule_from_tcr(tg << 14) for tg in range(3)],
                         [4096,65536,16384])

    def test_installer_constant_does_not_define_earlier_inherited_tg0(self):
        later=0x11b51c351c
        self.assertEqual(granule_from_tcr(later),4096)
        self.assertEqual(granule_from_tcr(later | (1 << 14)),65536)
        self.assertEqual(granule_from_tcr(later | (2 << 14)),16384)

    def test_other_tcr_bits_do_not_select_size(self):
        for value in (0,0xffffffffffff3fff):
            for tg,size in ((0,4096),(1,65536),(2,16384)):
                with self.subTest(value=value,tg=tg):
                    self.assertEqual(granule_from_tcr(value | (tg << 14)),size)

    def test_reserved_encoding_is_an_assertion_frontier(self):
        with self.assertRaisesRegex(ValueError,'assertion'):
            granule_from_tcr(3 << 14)

    def test_other_el_argument_refused_instead_of_returning_a_size(self):
        for el in (0,2,3,True,1.0,'1'):
            with self.subTest(el=el),self.assertRaisesRegex(ValueError,'EL argument'):
                granule_from_tcr(0,el)

    def test_tcr_must_be_u64_without_coercion(self):
        for value in (-1,1 << 64,True,0.0,'0',None):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'u64'):
                granule_from_tcr(value)


class CensusTests(unittest.TestCase):
    def test_all_source_registers_are_retained_including_xzr(self):
        data=b''.join(struct.pack('<I',0xd5182040 | r) for r in range(32))
        rows=tcr_writers(data)
        self.assertEqual([r['source_register'] for r in rows],list(range(32)))
        self.assertEqual(rows[-1]['file_offset'],'0x7c')

    def test_reads_other_levels_and_other_registers_are_excluded(self):
        words=(0xd5382040,0xd51c2040,0xd51e2040,0xd5182000,0xd5182020,0xd518a200)
        self.assertEqual(tcr_writers(struct.pack('<6I',*words)),[])

    def test_unaligned_match_is_outside_declared_census(self):
        data=b'X'+struct.pack('<I',0xd5182044)+bytes(3)
        self.assertEqual(tcr_writers(data),[])

    def test_selected_bounds_do_not_scan_neighbors(self):
        data=struct.pack('<3I',0xd5182040,0xd503201f,0xd5182044)
        self.assertEqual(tcr_writers(data,4,8),[])
        self.assertEqual(tcr_writers(data,8,12)[0]['source_register'],4)
        self.assertEqual(tcr_writers(data,8,8),[])

    def test_bad_bounds_or_truncated_word_refused(self):
        for start,end in ((-4,4),(1,4),(0,3),(4,0),(0,12),(True,4),(0,4.0)):
            with self.subTest(start=start,end=end),self.assertRaisesRegex(ValueError,'bounds'):
                tcr_writers(bytes(8),start,end)
        with self.assertRaisesRegex(ValueError,'bounds'):tcr_writers(bytes(7))


class RefusalTests(unittest.TestCase):
    def test_wrong_size_and_hash_fail_before_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.bin'
            for data in (b'bad',bytes(IMAGES['sboot'][0])):
                p.write_bytes(data)
                with self.subTest(size=len(data)),patch('inspect_lk_entry_granule.subprocess.check_output') as tool:
                    with self.assertRaisesRegex(ValueError,'unsupported image'):inspect(p)
                    tool.assert_not_called()

    def test_qemu_is_not_started_for_wrong_image(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.bin';p.write_bytes(b'bad')
            with patch('emulate_lk_entry_granule_qemu.subprocess.Popen') as launch:
                with self.assertRaisesRegex(ValueError,'unsupported image'):run(p)
                launch.assert_not_called()

    def test_cli_refusals_have_no_partial_json(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.bin';p.write_bytes(b'bad')
            for name in ('inspect_lk_entry_granule.py','emulate_lk_entry_granule_qemu.py'):
                r=subprocess.run([sys.executable,str(Path(__file__).with_name(name)),str(p)],capture_output=True,text=True,check=False)
                with self.subTest(script=name):
                    self.assertEqual((r.returncode,r.stdout),(2,''))
                    self.assertIn('unsupported image',r.stderr)


if __name__=='__main__':unittest.main()
