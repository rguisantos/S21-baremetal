#!/usr/bin/env python3
"""Test bounded LK heap arithmetic, page/context bindings and input refusals."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_heap import DELTA, heap_bindings, init_record, inspect, pool_contract, request_layout


def fixture():
    return {
        0x18d8e8: 0x90005be2,
        0x18d8ec: 0xb0005bc4,
        0x18d8f0: 0x91000042,
        0x18d8f4: 0xd2bd3003,
        0x18d8fc: 0xd0005bc0,
        0x18d900: 0xd2830005,
        0x18d904: 0x91044084,
        0x18d910: 0x91244000,
        0x20c0d8: 0x900057fa,
        0x20c0e0: 0x9126e35a,
        0x20c41c: 0x900057f5,
        0x20c428: 0x9126e2b3,
        0x20bf68: 0xb00057f4,
        0x20bf70: 0x9126e295,
        0x18da28: 0xd0005bc1,
        0x18da2c: 0x91244021,
        0x18da08: 0xd0005bc0,
        0x18da10: 0x91244000,
        0x147ea8: 0x90005c60,
        0x147eac: 0xb941c800,
    }


class RequestTests(unittest.TestCase):
    def test_metadata_rounding_for_zero_and_small_requests(self):
        for size,wanted in ((0,24),(1,24),(8,24),(9,32),(8176,8192)):
            with self.subTest(size=size):
                self.assertEqual(request_layout(size,0)['requested_chunk_bytes'],wanted)

    def test_nonzero_small_alignment_promoted_to_sixteen(self):
        for alignment in (1,2,4,8,16):
            with self.subTest(alignment=alignment):
                r=request_layout(1,alignment)
                self.assertEqual(r['effective_alignment'],16)
                self.assertEqual(r['requested_chunk_bytes'],40)

    def test_ufs_aligned_buffer_charges(self):
        for size,wanted in ((8192,12304),(64,4176),(160,4272)):
            self.assertEqual(request_layout(size,4096)['requested_chunk_bytes'],wanted)

    def test_bad_alignment_is_rejected_before_allocation(self):
        for alignment in (3,7,4095,0xffffffff):
            self.assertFalse(request_layout(64,alignment)['accepted'])

    def test_a64_addition_wrap_is_retained_without_extent_claim(self):
        r=request_layout(0xfffffffffffffff0,0)
        self.assertEqual(r['requested_chunk_bytes'],24)
        self.assertTrue(r['size_addition_wrapped'])
        self.assertFalse(r['dma_mapping_or_extent_established'])

    def test_exact_u64_u32_input_types(self):
        for size,alignment in ((-1,0),(1<<64,0),(True,0),(1.0,0),(1,-1),(1,1<<32),(1,False)):
            with self.subTest(size=size,alignment=alignment),self.assertRaises(ValueError):
                request_layout(size,alignment)


class BindingTests(unittest.TestCase):
    def test_nominal_pool_has_3043_pages_and_no_dma_identity(self):
        r=pool_contract(fixture())
        self.assertEqual((r['nominal_base'],r['end_exclusive'],r['bytes'],r['pages']),
                         ('0xe8c1d000','0xe9800000',0xbe3000,3043))
        self.assertEqual(r['bitmap_bytes_used'],3043)
        self.assertEqual(r['bitmap_capacity_bytes'],6144)
        self.assertFalse(r['physical_or_dma_identity_established'])

    def test_pool_argument_register_mutations_refused(self):
        for pc in (0x18d8f0,0x18d904,0x18d910,0x18d8f4,0x18d900):
            words=fixture();words[pc]^=1
            with self.subTest(pc=pc),self.assertRaises(ValueError):pool_contract(words)

    def test_pool_add_source_mutation_refused(self):
        words=fixture();words[0x18d8f0]^=1<<5
        with self.assertRaises(ValueError):pool_contract(words)

    def test_zero_bitmap_capacity_refused(self):
        words=fixture();words[0x18d900]=0xd2800005
        with self.assertRaisesRegex(ValueError,'bitmap'):pool_contract(words)

    def test_heap_constructor_allocator_free_and_page_context_match(self):
        r=heap_bindings(fixture())
        self.assertEqual(r['heap_context_relative'],'0xd089b8')
        self.assertEqual(r['page_context_relative'],'0xd07910')
        self.assertEqual(r['configuration_word_relative'],'0xcd31c8')
        self.assertFalse(r['configuration_word_runtime_value_acquired'])

    def test_heap_or_page_context_displacement_mutations_refused(self):
        for pc in (0x20c0e0,0x20c428,0x20bf70,0x18da2c,0x18da10):
            words=fixture();words[pc]^=1<<10
            with self.subTest(pc=pc),self.assertRaisesRegex(ValueError,'context'):heap_bindings(words)

    def test_configuration_getter_destination_mutation_refused(self):
        words=fixture();words[0x147eac]^=1
        with self.assertRaisesRegex(ValueError,'getter'):heap_bindings(words)

    def test_init_record_level_flags_target_and_name(self):
        b=bytearray(0x29b1a8)
        struct.pack_into('<IIQQ',b,0x29b190,0x1ffff,1,DELTA+0x18d8e8,DELTA+0x25f210)
        self.assertTrue(init_record(b)['selected_dispatch_precedes_heap_init'])
        self.assertFalse(init_record(b)['active_invocation_observed'])
        for offset in (0x29b190,0x29b194,0x29b198,0x29b1a0):
            changed=bytearray(b);changed[offset]^=1
            with self.subTest(offset=offset),self.assertRaises(ValueError):init_record(changed)

    def test_truncated_init_record_refused(self):
        with self.assertRaisesRegex(ValueError,'truncated'):init_record(bytes(64))


class RefusalTests(unittest.TestCase):
    def test_wrong_image_refused_before_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.bin'
            for data in (b'bad',bytes(IMAGES['sboot'][0])):
                p.write_bytes(data)
                with self.subTest(size=len(data)),patch('inspect_lk_heap.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError,'unsupported image'):inspect(p)
                    gnu.assert_not_called()

    def test_cli_refusal_has_no_partial_json(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.bin';p.write_bytes(b'bad')
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_lk_heap.py')),str(p)],capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,'')
            self.assertIn('unsupported image',result.stderr)


if __name__=='__main__':unittest.main()
