#!/usr/bin/env python3
"""Test synthetic UFS polling/response summaries and raw producer bindings."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_ufs_completion import (descriptor_shape, inspect, load_pair_x,
    load_unsigned_b, poll_data_snapshot, response_publication, status_binding)


def binding_words():
    return {
        0x10c808: 0xf9003001,
        0x10c8b4: 0xf9403274,
        0x10c8b8: 0xa9490275,
        0x10c8c0: 0x39501ea1,
        0x10c8c4: 0x39018281,
        0x10c034: 0xf0003cd5,
        0x10c03c: 0x910e02b3,
        0x10bea8: 0x90003ce0,
        0x10beac: 0x394f8000,
        0x10c8c8: 0x39402402,
        0x10c8cc: 0x39402004,
        0x10c8d0: 0x39402803,
        0x10c8d4: 0x39402c01,
    }


class PollTests(unittest.TestCase):
    def test_completion_requires_interrupt_and_clear_doorbell(self):
        self.assertEqual(poll_data_snapshot(1,0,7),dict(result=0,budget_after=7,delay_helper_called=False))
        self.assertEqual(poll_data_snapshot(0,0,7)['result'],3)
        self.assertEqual(poll_data_snapshot(1,1,7)['result'],3)

    def test_each_mask_bit_overrides_completion_without_consuming_budget(self):
        for bit in (0x80,0x800,0x10000,0x20000):
            with self.subTest(bit=bit):
                self.assertEqual(poll_data_snapshot(bit|1,0,0),dict(result=2,budget_after=0,delay_helper_called=False))

    def test_unmasked_status_bits_are_not_silently_added_to_error_mask(self):
        for bit in (4,0x40000,0x80000000):
            with self.subTest(bit=bit):
                self.assertEqual(poll_data_snapshot(bit|1,0,7)['result'],0)
                self.assertEqual(poll_data_snapshot(bit,0,7)['result'],3)

    def test_zero_budget_is_decremented_before_expiration_and_wraps(self):
        self.assertEqual(poll_data_snapshot(0,0,0),dict(result=1,budget_after=0xffffffff,delay_helper_called=False))
        self.assertEqual(poll_data_snapshot(0,1,1),dict(result=3,budget_after=0,delay_helper_called=True))
        self.assertEqual(poll_data_snapshot(1,0,0)['result'],0)

    def test_upper_doorbell_bits_do_not_block_selected_slot_zero(self):
        self.assertEqual(poll_data_snapshot(1,2,7)['result'],0)
        self.assertEqual(poll_data_snapshot(1,3,7)['result'],3)

    def test_invalid_u32_inputs_and_bool_are_refused(self):
        for position in range(3):
            for value in (-1,0x100000000,True,1.0):
                args=[1,0,7];args[position]=value
                with self.subTest(position=position,value=value),self.assertRaisesRegex(ValueError,'u32'):
                    poll_data_snapshot(*args)


class DescriptorTests(unittest.TestCase):
    def test_one_frame_has_one_full_size_prd_entry(self):
        result=descriptor_shape(512)
        self.assertEqual(result['prd_entries_written'],1)
        self.assertEqual(result['prd_length_field_u16'],16)
        self.assertEqual(result['prd_segment_bytes'],4096)
        self.assertFalse(result['last_segment_reduced_to_payload_remainder'])

    def test_page_boundary_and_zero_payload(self):
        self.assertEqual(descriptor_shape(0)['prd_entries_written'],0)
        self.assertIsNone(descriptor_shape(0)['prd_segment_bytes'])
        self.assertEqual(descriptor_shape(4096)['prd_entries_written'],1)
        self.assertEqual(descriptor_shape(4097)['prd_entries_written'],2)

    def test_u32_rounding_wrap_is_not_python_unbounded_rounding(self):
        self.assertEqual(descriptor_shape(0xfffff000)['prd_entries_written'],0xfffff)
        for length in (0xfffff001,0xffffffff):
            with self.subTest(length=length):
                self.assertEqual(descriptor_shape(length)['prd_entries_written'],0)
                self.assertIsNone(descriptor_shape(length)['prd_segment_bytes'])

    def test_encoded_field_truncates_separately_from_written_entry_count(self):
        result=descriptor_shape(4096*4096)
        self.assertEqual(result['prd_entries_written'],4096)
        self.assertEqual(result['prd_length_field_u16'],0)


class ResponseTests(unittest.TestCase):
    def test_successful_ocs_does_not_require_scsi_status_zero_here(self):
        for status in (0,2,255):
            result=response_publication(0,status)
            self.assertEqual(result['response_return'],0)
            self.assertEqual(result['published_scsi_status'],status)
            self.assertFalse(result['authenticated'])
            self.assertFalse(result['hardware_observed'])

    def test_status_is_published_even_when_ocs_is_nonzero(self):
        for ocs in (1,15,0x100,0xffffffff):
            with self.subTest(ocs=ocs):
                result=response_publication(ocs,2)
                self.assertEqual(result['response_return'],0xffffffff)
                self.assertEqual(result['published_scsi_status'],2)

    def test_invalid_status_widths_refused(self):
        for status in (-1,256,True,2.0):
            with self.subTest(status=status),self.assertRaisesRegex(ValueError,'u8'):
                response_publication(0,status)


class BindingTests(unittest.TestCase):
    def test_response_byte_reaches_selected_rpmb_status_consumer(self):
        result=status_binding(binding_words())
        self.assertEqual(result['status_source_command_descriptor_offset'],0x407)
        self.assertEqual(result['status_destination_request_offset'],96)
        self.assertEqual(result['consumer_relative_address'],'0x8a73e0')
        self.assertEqual(result['ocs_checked_bytes'],4)
        self.assertTrue(result['status_store_precedes_ocs_test'])
        self.assertFalse(result['live_freshness_established'])

    def test_producer_register_base_offset_and_width_changes_refused(self):
        for pc in (0x10c8b4,0x10c8c0,0x10c8c4):
            for bit in (1,1<<5,1<<10,1<<30):
                words=binding_words();words[pc]^=bit
                with self.subTest(pc=pc,bit=bit),self.assertRaises(ValueError):
                    status_binding(words)

    def test_consumer_moved_away_from_published_byte_is_refused(self):
        words=binding_words();words[0x10beac]^=1<<10
        with self.assertRaisesRegex(ValueError,'consumer'):
            status_binding(words)

    def test_ocs_loads_must_read_four_expected_bytes_and_registers(self):
        for pc in (0x10c8c8,0x10c8cc,0x10c8d0,0x10c8d4):
            for bit in (1,1<<5,1<<10):
                words=binding_words();words[pc]^=bit
                with self.subTest(pc=pc,bit=bit),self.assertRaisesRegex(ValueError,'OCS'):
                    status_binding(words)

    def test_ldp_offset_form_and_signed_scaled_offset(self):
        self.assertEqual(load_pair_x(0xa9490275),(21,0,19,144))
        self.assertEqual(load_pair_x(0xa97f8620),(0,1,17,-8))

    def test_wrong_load_width_store_indexed_and_non_words_refused(self):
        for word in (0xa9090275,0x29490275,0xa8c153f3,True,-1,0x1a9490275):
            with self.subTest(word=word),self.assertRaisesRegex(ValueError,'LDP X'):
                load_pair_x(word)
        for word in (0x39001c01,0x79401c01,0x38401422,True,-1):
            with self.subTest(word=word),self.assertRaisesRegex(ValueError,'LDRB'):
                load_unsigned_b(word)


class RefusalTests(unittest.TestCase):
    def test_wrong_image_refused_before_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.bin'
            for data in (b'bad',bytes(IMAGES['sboot'][0])):
                path.write_bytes(data)
                with self.subTest(size=len(data)),patch('inspect_lk_ufs_completion.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError,'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_failure_emits_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.bin';path.write_bytes(b'bad')
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_lk_ufs_completion.py')),str(path)],capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,2)
            self.assertEqual(result.stdout,'')
            self.assertIn('unsupported image',result.stderr)


if __name__=='__main__':
    unittest.main()
