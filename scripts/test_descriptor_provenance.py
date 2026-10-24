"""Bounded copy/address witnesses: no firmware or secure response execution."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_descriptor_provenance import DESCRIPTOR, LIMIT, copy_loop, overlap, wide_candidates


def fixture(stride=16,src=0x1000,end=0x1040,dst=0x2000,code=0,literals=64):
    data=bytearray(max(code+40,literals+24))
    for reg in range(3):
        pc=code+4*reg;target=literals+8*reg
        struct.pack_into('<I',data,pc,0x58000000|(((target-pc)//4&0x7ffff)<<5)|reg)
    pair=(0xa8c11003,0xa8811043) if stride==16 else (0xb8404403,0xb8004443)
    struct.pack_into('<7I',data,code+12,*pair,0xeb01001f,0x54ffffab,0xd5033f9f,0xd5033fdf,0xd65f03c0)
    struct.pack_into('<3Q',data,literals,src,end,dst)
    return data


def words(*values):
    return struct.pack('<'+'I'*len(values),*values)


class Provenance(unittest.TestCase):
    def test_fixed_pair_copy_extent_and_iterations(self):
        r=copy_loop(fixture(),0,16)
        self.assertEqual((r['source'],r['destination'],r['bytes'],r['iterations']),
                         (['0x1000','0x1040'],['0x2000','0x2040'],64,4))
        self.assertFalse(r['destination_overlaps_descriptor'])

    def test_w_copy_uses_four_byte_iteration(self):
        r=copy_loop(fixture(4),0,4)
        self.assertEqual((r['stride'],r['iterations']), (4,16))

    def test_negative_literal_displacement_resolves_correctly(self):
        r=copy_loop(fixture(code=128,literals=0),128,16)
        self.assertEqual(r['literal_offsets'],['0x0','0x8','0x10'])

    def test_zero_reversed_or_partial_extent_is_rejected(self):
        for end in (0x1000,0xff0,0x1041):
            with self.subTest(end=end),self.assertRaises(ValueError):copy_loop(fixture(end=end),0,16)

    def test_signed_bound_or_destination_outside_supported_domain_rejected(self):
        for kwargs in ({'src':1<<63,'end':(1<<63)+64},{'dst':1<<63}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):copy_loop(fixture(**kwargs),0,16)

    def test_wrong_literal_width_register_or_alignment_is_rejected(self):
        for value in (0x18000800,0x58000801,0x58000820,0x587fff00):
            data=fixture();struct.pack_into('<I',data,0,value)
            with self.subTest(value=hex(value)),self.assertRaises(ValueError):copy_loop(data,0,16)

    def test_changed_copy_body_branch_barrier_or_return_is_rejected(self):
        for pc in (12,16,20,24,28,32,36):
            data=fixture();struct.pack_into('<I',data,pc,0xd503201f)
            with self.subTest(pc=pc),self.assertRaises(ValueError):copy_loop(data,0,16)

    def test_unsupported_stride_or_truncated_copy_rejected(self):
        with self.assertRaises(ValueError):copy_loop(fixture(),0,8)
        with self.assertRaises(ValueError):copy_loop(fixture()[:32],0,16)

    def test_copy_overlap_is_not_mistaken_for_initialization(self):
        r=copy_loop(fixture(dst=DESCRIPTOR),0,16)
        self.assertTrue(r['destination_overlaps_descriptor'])
        self.assertFalse(r['loop_execution_observed'])

    def test_half_open_touching_and_one_byte_overlap(self):
        self.assertFalse(overlap(0,10,10,20))
        self.assertTrue(overlap(0,11,10,20))
        for args in ((0,0,1,2),(2,1,1,2),(-1,0,1,2),(0,1,2,(1<<64)+1)):
            with self.subTest(args=args),self.assertRaises(ValueError):overlap(*args)

    def test_adjacent_wide_address_distinguishes_descriptor_from_lk_limit(self):
        for low,target in ((0xe000,DESCRIPTOR),(0xfe00,LIMIT)):
            data=words(0xd2800002|(low<<5),0xf2bcffe2)
            r=wide_candidates(data,{DESCRIPTOR,LIMIT})
            self.assertEqual(r[0]['address'],hex(target))

    def test_safe_intervening_prologue_and_other_register_move(self):
        data=words(0xd29c0002,0x52a00503,0xa9bf7bfd,0xf2bcffe2)
        self.assertEqual(wide_candidates(data,{DESCRIPTOR})[0]['movk'],'0xc')
        data=words(0xd29c0002,0x2a0003e3,0x2a0003e1,0xf2bcffe2)
        self.assertEqual(len(wide_candidates(data,{DESCRIPTOR})),1)

    def test_clobbered_base_call_or_unknown_gap_is_not_a_witness(self):
        for middle in (0x2a0003e2,0xd2800002,0x94000001,0xd503201f,0x910003fd):
            reg=29 if middle==0x910003fd else 2
            data=words(0xd29c0000|reg,middle,0xf2bcffe0|reg)
            with self.subTest(middle=hex(middle)):
                self.assertEqual(wide_candidates(data,{DESCRIPTOR}),[])

    def test_span_width_and_final_register_are_limited(self):
        for data in (words(0xd29c0002,0x52800003,0x52800004,0x52800005,0xf2bcffe2),
                     words(0x529c0002,0xf2bcffe2),words(0xd29c0002,0xf2bcffe1),
                     words(0xd29c0002,0xf2dcffe2)):
            self.assertEqual(wide_candidates(data,{DESCRIPTOR}),[])

    def test_scan_bounds_exclude_unaligned_or_partial_words(self):
        data=words(0xd29c0002,0xf2bcffe2)
        for a,b in ((-4,8),(1,8),(0,9),(8,8)):
            with self.subTest(bounds=(a,b)),self.assertRaises(ValueError):wide_candidates(data,{DESCRIPTOR},a,b)

    def test_wrong_firmware_cli_emits_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sboot.bin';path.write_bytes(b'not the pinned HZC2 image')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_descriptor_provenance.py')),str(path)],capture_output=True)
        self.assertEqual(r.returncode,2);self.assertFalse(r.stdout)


if __name__=='__main__':unittest.main()
