"""Request-construction and constant-gate witnesses, without secure execution."""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from inspect_monitor_preparation import immediate, request, word, zero_gate, branch_candidates


def wrapper():
    # Relocated short instruction fixture; the BL points to a synthetic veneer.
    words = (0xa9bf7bfd, 0xd2836c21, 0x910003fd, 0x34000080, 0x7100801f,
             0xd2806d81, 0x9a8113e1, 0xd2bd0003, 0xd2a00082, 0x92801cc0,
             0x94000016, 0xa8c17bfd, 0xd65f03c0)
    data = bytearray(136)
    struct.pack_into('<13I',data,0,*words)
    struct.pack_into('<2I',data,128,0xd4000003,0xd65f03c0)
    return data


def gate_fixture(nonzero_branch=True):
    data = bytearray(40)
    struct.pack_into('<3I',data,0,0x94000008,0x53001c00,
                     0x35000080 if nonzero_branch else 0x34000080)
    struct.pack_into('<2I',data,32,0x52800000,0xd65f03c0)
    return data


class Preparation(unittest.TestCase):
    def test_mode_zero_reconstructs_sector_like_argument_without_assigning_units(self):
        r=request(wrapper(),0,0,128)
        self.assertEqual((r['x0'],r['x1'],r['x2'],r['x3']),
                         ('0xffffffffffffff19','0x1b61','0x40000','0xe8000000'))
        self.assertTrue(r['stopped_before_smc'])

    def test_mode_32_uses_alternative_and_other_w_modes_zero_x1(self):
        for mode,expected in ((32,'0x36c'),(1,'0x0'),(20,'0x0'),(64,'0x0'),(0xffffffff,'0x0')):
            with self.subTest(mode=mode):
                self.assertEqual(request(wrapper(),mode,0,128)['x1'],expected)

    def test_modes_require_explicit_unsigned_w_values(self):
        for mode in (True,-1,1<<32,'0x20',None):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                request(wrapper(),mode,0,128)

    def test_request_rejects_changed_selection_or_prologue(self):
        for at,new in ((0,0xd503201f),(8,0xd503201f),(12,0x34000060),
                       (16,0xf100801f),(24,0x9a8103e1)):
            data=wrapper();struct.pack_into('<I',data,at,new)
            with self.subTest(at=at),self.assertRaises(ValueError):request(data,32,0,128)

    def test_request_cannot_skip_or_redirect_secure_veneer(self):
        for at,new in ((40,0x14000016),(40,0x94000015),(128,0xd4000002),(132,0xd503201f)):
            data=wrapper();struct.pack_into('<I',data,at,new)
            with self.subTest(at=at),self.assertRaises(ValueError):request(data,0,0,128)

    def test_immediates_decode_movz_shift_and_movn_64bit(self):
        data=wrapper()
        self.assertEqual(immediate(data,28,3),0xe8000000)
        self.assertEqual(immediate(data,36,0),0xffffffffffffff19)
        self.assertEqual(immediate(data,4,1),0x1b61)

    def test_immediate_rejects_wrong_register_width_and_movk(self):
        for value,register in ((0x52800000,0),(0xf2800000,0),(0xd2800001,0)):
            with self.subTest(value=hex(value)),self.assertRaises(ValueError):
                immediate(struct.pack('<I',value),0,register)

    def test_instruction_access_is_bounded_and_aligned(self):
        for pc in (-4,1,4):
            with self.subTest(pc=pc),self.assertRaises(ValueError):word(b'1234',pc)

    def test_zero_gate_skips_conditional_insert_and_remove_branches(self):
        r=zero_gate(gate_fixture(),0,32)
        self.assertFalse(r['branch_taken']);self.assertEqual(r['next_pc'],'0xc')

    def test_zero_gate_takes_cbz_path_in_callback_body(self):
        r=zero_gate(gate_fixture(False),0,32)
        self.assertTrue(r['branch_taken']);self.assertEqual(r['next_pc'],'0x18')

    def test_gate_proof_rejects_nonzero_gate_or_unknown_condition(self):
        for at,new in ((32,0x52800020),(36,0xd503201f),(0,0x94000007),
                       (4,0x53001c21),(8,0xb5000080),(8,0x35000081)):
            data=gate_fixture();struct.pack_into('<I',data,at,new)
            with self.subTest(at=at),self.assertRaises(ValueError):zero_gate(data,0,32)

    def test_census_includes_tail_branches_and_negative_relative_calls(self):
        data=struct.pack('<5I',0x14000002,0x94000001,0xd65f03c0,0x17ffffff,0x90000008)
        self.assertEqual(branch_candidates(data,8,0,len(data)),
                         [{'offset':'0x0','kind':'b'},{'offset':'0x4','kind':'bl'},
                          {'offset':'0xc','kind':'b'}])

    def test_census_rejects_invalid_file_bounds(self):
        for start,end in ((-4,4),(1,4),(0,5),(4,4),(0,8)):
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):
                branch_candidates(b'1234',0,start,end)

    def test_wrong_firmware_cli_does_not_emit_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'sboot.bin';p.write_bytes(b'wrong image')
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_monitor_preparation.py')),str(p)],capture_output=True)
        self.assertEqual(result.returncode,2);self.assertFalse(result.stdout)
        self.assertIn(b'unsupported image',result.stderr)


if __name__=='__main__':unittest.main()
