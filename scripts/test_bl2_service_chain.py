"""Tests for explicit-response selection and partial BL2 descriptor writes."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_bl2_service_chain import address_candidates, descriptor_request, select_mode

TABLE = bytes((32,20,0,64,0,0,0,0,0,0,64))


def fixture():
    # Relocate the small constructor. Only the final secure BL needs relocation.
    words = (0xd29c0002,0x52a00503,0xa9bf7bfd,0xf2bcffe2,0x52bd0001,
             0x910003fd,0x29000c41,0x52898003,0xb9000c5f,0x72a04043,
             0xb9000843,0x350000a0,0x5280ec23,0xb9001043,0x52828003,
             0x1400000b,0x7100501f,0x54000081,0x52828003,0x29020443,
             0x14000007,0x7100801f,0x540000a1,0x52801d83,0xb9001043,
             0x52805003,0x29028443,0xd29c0002,0x2a0003e3,0x2a0003e1,
             0xf2bcffe2,0x92801ca0,0x94000020)
    data=bytearray(264)
    struct.pack_into('<33I',data,0,*words)
    struct.pack_into('<2I',data,256,0xd4000003,0xd65f03c0)
    return data


def run(mode,data=None):
    return descriptor_request(fixture() if data is None else data,mode,start=0,veneer=256)


class ServiceChain(unittest.TestCase):
    def test_selected_nibbles_and_unsigned_table_bound(self):
        for response,mode in ((0,0),(0x11,32),(0x21,20),(0x41,64),(0xb1,64),(0xc1,0),(0xf1,0)):
            with self.subTest(response=hex(response)):
                self.assertEqual(select_mode(response,TABLE)['mode_w19'],hex(mode))

    def test_w_variable_shift_wraps_at_32_instead_of_64(self):
        r=select_mode(0x100000008,TABLE)
        self.assertEqual((r['w0'],r['shift'],r['nibble'],r['mode_w19']),('0x8',0,8,'0x0'))

    def test_high_x2_half_does_not_change_selector(self):
        self.assertEqual(select_mode(0xdeadbeef00000021,TABLE)['mode_w19'],'0x14')

    def test_selector_low_nibble_sets_its_own_index_when_shift_zero(self):
        for value in (0,8):
            self.assertEqual(select_mode(value,TABLE)['nibble'],value)

    def test_response_requires_explicit_unsigned_x_value(self):
        for value in (True,-1,1<<64,'0x21',None):
            with self.subTest(value=value),self.assertRaises(ValueError):select_mode(value,TABLE)

    def test_table_requires_exact_eleven_bytes(self):
        for table in (b'',b'1234567890',b'123456789012',list(TABLE)):
            with self.subTest(table=table),self.assertRaises(ValueError):select_mode(0,table)

    def test_common_descriptor_words_and_secure_arguments(self):
        for mode in (0,20,32,64):
            r=run(mode)
            self.assertEqual([r['fields'][hex(i)] for i in (0,4,8,12)],
                             ['0xe8000000','0x280000','0x2024c00','0x0'])
            self.assertEqual(r['registers'],{'x0':'0xffffffffffffff1a','x1':hex(mode),
                                             'x2':'0xe7ffe000','x3':hex(mode)})
            self.assertTrue(r['stopped_before_smc'])

    def test_mode_zero_writes_all_three_conditional_fields(self):
        r=run(0)
        self.assertEqual([r['fields'][hex(i)] for i in (16,20,24)],['0x761','0x1400','0xe8000000'])

    def test_mode_32_uses_different_source_and_length(self):
        r=run(32)
        self.assertEqual([r['fields'][hex(i)] for i in (16,20,24)],['0xec','0x280','0xe8000000'])

    def test_mode_20_leaves_last_word_unknown(self):
        r=run(20)
        self.assertEqual([r['fields'][hex(i)] for i in (16,20,24)],['0x1400','0xe8000000',None])
        self.assertNotIn('0x18',[w['offset'] for w in r['writes']])

    def test_mode_64_and_other_modes_leave_three_words_unknown(self):
        for mode in (64,1,0xffffffff):
            r=run(mode)
            self.assertEqual([r['fields'][hex(i)] for i in (16,20,24)],[None,None,None])
            self.assertEqual(len(r['writes']),4)

    def test_mode_input_rejects_implicit_truncation(self):
        for mode in (True,-1,1<<32,None):
            with self.subTest(mode=mode),self.assertRaises(ValueError):run(mode)

    def test_unknown_initial_register_is_not_invented_for_movk(self):
        data=fixture();struct.pack_into('<I',data,0,0xf29c0002)
        with self.assertRaisesRegex(ValueError,'unknown register'):run(0,data)

    def test_store_outside_descriptor_is_rejected(self):
        data=fixture();struct.pack_into('<I',data,24,0x29040c41)
        with self.assertRaisesRegex(ValueError,'outside descriptor'):run(0,data)

    def test_changed_stack_prologue_or_unsupported_instruction_is_rejected(self):
        for offset in (8,20,0):
            data=fixture();struct.pack_into('<I',data,offset,0xd503201f)
            with self.subTest(offset=offset),self.assertRaises(ValueError):run(0,data)

    def test_unknown_condition_flags_are_rejected(self):
        data=fixture();struct.pack_into('<I',data,0,0x54000081)
        with self.assertRaisesRegex(ValueError,'unknown condition'):run(0,data)

    def test_constructor_cannot_loop_or_escape(self):
        for value in (0x14000000,0x14000400):
            data=fixture();struct.pack_into('<I',data,0,value)
            with self.subTest(value=hex(value)),self.assertRaisesRegex(ValueError,'escaped bounds or looped'):run(0,data)

    def test_unsupported_w_move_wide_shift_is_rejected(self):
        data=fixture();struct.pack_into('<I',data,4,0x52c00503)
        with self.assertRaisesRegex(ValueError,'move-wide shift'):run(0,data)

    def test_secure_boundary_cannot_be_redirected_or_changed_to_hvc(self):
        for at,value in ((128,0x9400001f),(256,0xd4000002),(260,0xd503201f)):
            data=fixture();struct.pack_into('<I',data,at,value)
            with self.subTest(at=at),self.assertRaisesRegex(ValueError,'secure boundary'):run(0,data)

    def test_wrong_image_cli_refuses_output(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'sboot.bin';p.write_bytes(b'not HZC2')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_bl2_service_chain.py')),str(p)],capture_output=True)
        self.assertEqual(r.returncode,2);self.assertFalse(r.stdout)

    def test_adjacent_address_pair_and_safe_intervening_move(self):
        for words,gap in (((0x90000000,0x91048001),4),
                          ((0x90000000,0xaa0203e3,0x91048001),8)):
            data=struct.pack('<'+'I'*len(words),*words)
            self.assertEqual(address_candidates(data,{0x120},0,len(data)),
                             [{'adrp':'0x0','add':hex(gap),'address_file_offset':'0x120'}])

    def test_address_scan_rejects_clobbered_base_or_unsupported_gap(self):
        for middle in (0xaa0203e0,0xd503201f,0xaa0203ff):
            data=struct.pack('<3I',0x90000000,middle,0x91048001)
            self.assertEqual(address_candidates(data,{0x120},0,len(data)),[])

    def test_adrp_sign_extension_reaches_previous_page(self):
        data=bytearray(4104);struct.pack_into('<2I',data,4096,0xf0ffffe0,0x91048001)
        self.assertEqual(address_candidates(data,{0x120},4096,len(data))[0]['address_file_offset'],'0x120')

    def test_address_scan_respects_bounds_and_excludes_shifted_add(self):
        data=struct.pack('<2I',0x90000000,0x91448001)
        self.assertEqual(address_candidates(data,{0x120},0,len(data)),[])
        for a,b in ((-4,8),(1,8),(0,9),(8,8)):
            with self.subTest(bounds=(a,b)),self.assertRaises(ValueError):address_candidates(data,{0x120},a,b)


if __name__=='__main__':unittest.main()
