#!/usr/bin/env python3
"""Test UFS host allocation/config bindings, table bounds and address truncation."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_ufs_host import (address_projection, allocation_fields,
    config_bindings, host_binding, inspect, store_unsigned_w, u64_table)


def fixture():
    return {
        0x10ecb4: 0xb0003cc1,
        0x10ecb8: 0xf9038c20,
        0x10e834: 0xb0003cd5,
        0x10e844: 0xf9438eb3,
        0x10e770: 0xb0003cd4,
        0x10e778: 0x911c6294,
        0x10ec9c: 0xb0003cc1,
        0x10ecac: 0xb907103f,
        0x10eb7c: 0xb0003cc0,
        0x10eb88: 0xb907101f,
        0x10e768: 0xb0003cd5,
        0x10e780: 0xb94712a1,
        0x10ecd0: 0xd2800400,
        0x10ecd4: 0x9402041f,
        0x10ecd8: 0xf90fda60,
        0x10ece0: 0xd2840001,
        0x10ece4: 0xd2820000,
        0x10ece8: 0x9402042a,
        0x10ecec: 0xf9004a60,
        0x10ecfc: 0xd2800801,
        0x10ed00: 0xd2820000,
        0x10ed04: 0x94020423,
        0x10ed08: 0xf9004e60,
        0x10ed18: 0xd2801401,
        0x10ed1c: 0xd2820000,
        0x10ed20: 0x9402041c,
        0x10ed24: 0xf9005260,
        0x10e870: 0xb0000fb4,
        0x10e874: 0x91066294,
        0x10ebb4: 0xb0000fb4,
        0x10ebb8: 0x91236294,
        0x10e878: 0xf9400280,
        0x10e880: 0xf9000e60,
        0x10e884: 0xf9400680,
        0x10e888: 0xf9001260,
        0x10e88c: 0xf9400a80,
        0x10e890: 0xf9001660,
        0x10e894: 0xf9400e80,
        0x10e898: 0xf9001a60,
        0x10e89c: 0xf9401280,
        0x10e8a0: 0xf9002260,
    }


class HostTests(unittest.TestCase):
    def test_slot_zero_publication_matches_initializer_and_gateway(self):
        result=host_binding(fixture())
        self.assertEqual(result['host_table_relative_address'],'0x8a7718')
        self.assertEqual(result['host_index_relative_address'],'0x8a7710')
        self.assertEqual(result['initialized_slot'],0)
        self.assertTrue(result['allocator_publication_precedes_null_check'])
        self.assertFalse(result['active_host_established'])

    def test_host_pointer_source_base_or_offset_mutations_refused(self):
        for pc in (0x10ecb8,0x10e844):
            for bit in (1,1<<5,1<<10):
                words=fixture();words[pc]^=bit
                with self.subTest(pc=pc,bit=bit),self.assertRaises(ValueError):
                    host_binding(words)

    def test_index_resets_must_store_zero_to_same_slot(self):
        for pc in (0x10ecac,0x10eb88):
            for bit in (1,1<<5,1<<10):
                words=fixture();words[pc]^=bit
                with self.subTest(pc=pc,bit=bit),self.assertRaisesRegex(ValueError,'index'):
                    host_binding(words)

    def test_index_consumer_and_gateway_table_mismatch_refused(self):
        for pc in (0x10e780,0x10e778):
            words=fixture();words[pc]^=1<<10
            with self.subTest(pc=pc),self.assertRaises(ValueError):
                host_binding(words)


class AllocationTests(unittest.TestCase):
    def test_sizes_alignment_and_result_slots_match(self):
        rows=allocation_fields(fixture())
        self.assertEqual([(r['name'],r['bytes'],r['alignment_argument'],r['host_pointer_offset']) for r in rows],
            [('metadata',32,None,8112),('command',8192,4096,144),
             ('transfer',64,4096,152),('task',160,4096,160)])

    def test_result_register_base_and_slot_mutations_refused(self):
        for pc in (0x10ecd8,0x10ecec,0x10ed08,0x10ed24):
            for bit in (1,1<<5,1<<10):
                words=fixture();words[pc]^=bit
                with self.subTest(pc=pc,bit=bit),self.assertRaisesRegex(ValueError,'result/call'):
                    allocation_fields(words)

    def test_allocator_branch_target_mutation_refused(self):
        for pc in (0x10ecd4,0x10ece8,0x10ed04,0x10ed20):
            words=fixture();words[pc]^=1
            with self.subTest(pc=pc),self.assertRaisesRegex(ValueError,'result/call'):
                allocation_fields(words)

    def test_size_argument_register_or_width_mutation_refused(self):
        for pc in (0x10ecd0,0x10ece0,0x10ecfc,0x10ed18):
            for bit in (1,1<<31):
                words=fixture();words[pc]^=bit
                with self.subTest(pc=pc,bit=bit),self.assertRaises(ValueError):
                    allocation_fields(words)

    def test_alignment_argument_register_mutation_refused(self):
        words=fixture();words[0x10ece4]^=1
        with self.assertRaisesRegex(ValueError,'alignment'):
            allocation_fields(words)


class ConfigTests(unittest.TestCase):
    def test_tables_and_five_selected_field_copies(self):
        primary,alternate,copies=config_bindings(fixture())
        self.assertEqual((primary,alternate),(0x303198,0x3038d8))
        self.assertEqual([(r['table_offset'],r['host_offset']) for r in copies],[(0,24),(8,32),(16,40),(24,48),(32,64)])

    def test_copy_base_or_slot_mutations_refused(self):
        for pc in (0x10e878,0x10e880,0x10e898,0x10e8a0):
            for bit in (1,1<<5,1<<10):
                words=fixture();words[pc]^=bit
                with self.subTest(pc=pc,bit=bit),self.assertRaisesRegex(ValueError,'field copy'):
                    config_bindings(words)

    def test_table_add_source_mutation_refused(self):
        words=fixture();words[0x10e874]^=1<<5
        with self.assertRaisesRegex(ValueError,'source'):
            config_bindings(words)


class DecoderTests(unittest.TestCase):
    def test_u64_little_endian_order_duplicates_and_exact_extent(self):
        values=[0x13100000,0x100000000,0xffffffffffffffff,0x13100000]
        data=bytes(8)+struct.pack('<4Q',*values)
        self.assertEqual(u64_table(data,8,4),values)

    def test_table_type_count_alignment_and_truncation_refused(self):
        for offset,count in ((-8,1),(1,1),(0,0),(0,65),(64,1),(56,2),(True,1),(0,1.0)):
            with self.subTest(offset=offset,count=count),self.assertRaisesRegex(ValueError,'bounds'):
                u64_table(bytes(64),offset,count)

    def test_w_store_scales_displacement_and_refuses_other_forms(self):
        self.assertEqual(store_unsigned_w(0xb907101f),(31,0,1808))
        self.assertEqual(store_unsigned_w(0xb93ffc20),(0,1,16380))
        for word in (0xf907101f,0xb947101f,0xb8008420,True,-1,0x1b907101f):
            with self.subTest(word=word),self.assertRaisesRegex(ValueError,'STR W'):
                store_unsigned_w(word)

    def test_low32_projection_preserves_only_low_pointer_bits(self):
        self.assertTrue(address_projection(0xfffff000)['pointer_bits_preserved'])
        result=address_projection(0x100001000)
        self.assertEqual(result['programmed_low32'],'0x1000')
        self.assertEqual(result['programmed_high32'],0)
        self.assertFalse(result['pointer_bits_preserved'])
        self.assertFalse(result['dma_mapping_or_extent_established'])

    def test_invalid_pointer_bit_inputs_refused(self):
        for value in (-1,0x10000000000000000,True,1.0):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'u64'):
                address_projection(value)


class RefusalTests(unittest.TestCase):
    def test_wrong_image_refused_before_disassembly(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.bin'
            for data in (b'bad',bytes(IMAGES['sboot'][0])):
                path.write_bytes(data)
                with self.subTest(size=len(data)),patch('inspect_lk_ufs_host.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError,'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_failure_produces_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.bin';path.write_bytes(b'bad')
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_lk_ufs_host.py')),str(path)],capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,2)
            self.assertEqual(result.stdout,'')
            self.assertIn('unsupported image',result.stderr)


if __name__=='__main__':
    unittest.main()
