"""Common-dispatch arithmetic and explicit nominal mapping; no MMIO mocks."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_epbl_preparation import adrp_ldr_pointer, common_id, dispatcher_slot, file_offset


class EPBL(unittest.TestCase):
    def test_negative_legacy_ids_have_distinct_common_commands(self):
        for command in (0xe6,0xe7,0xe8,0xe9,0xed,0x3ff,0x500):
            r=common_id((1<<64)-command)
            with self.subTest(command=hex(command)):
                self.assertEqual(r['common_normalized_w0'],hex(0x82000000|command))
                self.assertEqual(r['owner_index'],66)
                self.assertTrue(r['legacy_prefix_matched'])
                self.assertFalse(r['handler_resolved'])

    def test_guarded_entry_would_reject_legacy_negative_values(self):
        self.assertTrue(common_id(0xffffffffffffff1a)['rejects_if_entered_at_0x43d8'])
        self.assertFalse(common_id(0x820000e6)['rejects_if_entered_at_0x43d8'])

    def test_prefix_test_is_not_a_general_signed_absolute_value(self):
        r=common_id(0xfffeffff)
        self.assertFalse(r['legacy_prefix_matched'])
        self.assertEqual(r['common_normalized_w0'],'0xfffeffff')

    def test_minus_one_and_prefix_boundary_wrap_in_w_registers(self):
        self.assertEqual(common_id(0xffffffff)['common_normalized_w0'],'0x82000001')
        self.assertEqual(common_id(0xffff0000)['common_normalized_w0'],'0x82010000')

    def test_native_32bit_id_is_not_rewritten(self):
        r=common_id(0x82002011)
        self.assertEqual(r['common_normalized_w0'],'0x82002011')
        self.assertFalse(r['legacy_prefix_matched'])

    def test_high_x0_half_does_not_change_common_w_id(self):
        self.assertEqual(common_id(0xdeadbeef82002011),common_id(0x82002011))

    def test_owner_index_includes_fast_bit_but_not_call_width_bit(self):
        self.assertEqual(common_id(0x02000000)['owner_index'],2)
        self.assertEqual(common_id(0x82000000)['owner_index'],66)
        self.assertEqual(common_id(0xc2000000)['owner_index'],66)
        self.assertEqual(common_id(0xbf000000)['owner_index'],127)

    def test_service_input_requires_unsigned_64bit_integer(self):
        for value in (True,-230,1<<64,'0xffffff1a',None):
            with self.subTest(value=value),self.assertRaises(ValueError):common_id(value)

    def test_classification_stride_and_maximum_slot(self):
        for byte,offset in ((0,0xe410),(1,0xe430),(127,0xf3f0)):
            r=dispatcher_slot(byte)
            self.assertFalse(r['rejected']);self.assertEqual(r['slot_file_offset'],hex(offset))
            self.assertFalse(r['runtime_pointer_known'])

    def test_classification_bit7_refuses_pointer_selection(self):
        for byte in (128,255):
            r=dispatcher_slot(byte)
            self.assertTrue(r['rejected']);self.assertIsNone(r['slot_file_offset'])

    def test_classification_does_not_implicitly_truncate(self):
        for value in (True,-1,256,'0x42'):
            with self.subTest(value=value),self.assertRaises(ValueError):dispatcher_slot(value)

    def test_nominal_translation_checks_whole_width(self):
        self.assertEqual(file_offset(0x2028700,0x2024000,16),0x4700)
        self.assertEqual(file_offset(0x2024000+0x15fff,0x2024000),0x15fff)
        with self.assertRaises(ValueError):file_offset(0x2024000+0x15fff,0x2024000,2)

    def test_translation_rejects_external_or_invalid_ranges(self):
        for args in ((0x2024000,0x2024000,1),(0x203a000,0x2024000,1),
                     (0,0x2024000,1),(0x2028700,-1,1),(0x2028700,0x2024000,0),
                     (True,0x2024000,1),(0x2028700,0x2024000,True)):
            with self.subTest(args=args),self.assertRaises(ValueError):file_offset(*args)

    def test_adrp_ldr_loads_u64_from_decoded_slot(self):
        data=bytearray(80);struct.pack_into('<2I',data,0,0x90000002,0xf9402040)
        struct.pack_into('<Q',data,64,0x2028700)
        self.assertEqual(adrp_ldr_pointer(data,0,4),(64,0x2028700))

    def test_adrp_negative_page_displacement(self):
        data=bytearray(4104);struct.pack_into('<2I',data,4096,0xf0ffffe2,0xf9402040)
        struct.pack_into('<Q',data,64,0x2028700)
        self.assertEqual(adrp_ldr_pointer(data,4096,4100),(64,0x2028700))

    def test_pointer_witness_rejects_wrong_width_base_or_outside_slot(self):
        for a,b in ((0x90000002,0xb9402040),(0x90000001,0xf9402040),
                    (0x90000002,0xf9404040),(0x10000002,0xf9402040)):
            data=bytearray(80);struct.pack_into('<2I',data,0,a,b)
            with self.subTest(a=hex(a),b=hex(b)),self.assertRaises(ValueError):adrp_ldr_pointer(data,0,4)

    def test_pointer_witness_requires_aligned_instruction_bytes(self):
        with self.assertRaises(ValueError):adrp_ldr_pointer(b'1234',1,4)

    def test_wrong_firmware_cli_emits_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sboot.bin';path.write_bytes(b'wrong image')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_epbl_preparation.py')),str(path)],capture_output=True)
        self.assertEqual(r.returncode,2);self.assertFalse(r.stdout)


if __name__=='__main__':unittest.main()
