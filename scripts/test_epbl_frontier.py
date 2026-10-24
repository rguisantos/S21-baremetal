"""Static prefix frontier semantics, with explicit opaque and indirect cuts."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_epbl_frontier import adr_target, prefix_graph


def fixture(*words):
    data=bytearray(128);struct.pack_into('<'+'I'*len(words),data,0,*words)
    return data


def graph(data,roots=(0,),**kwargs):
    return prefix_graph(data,roots,start=0,end=32,pending_range=(64,128),**kwargs)


class Frontier(unittest.TestCase):
    def test_linear_nodes_stop_at_ret_including_ret_x29(self):
        for ret in (0xd65f03c0,0xd65f03a0):
            r=graph(fixture(0xd503201f,ret,0))
            self.assertEqual(r['instruction_count'],2)
            self.assertEqual(r['exits'],{'0x4':'ret'})

    def test_call_to_pending_region_records_edge_and_assumes_return(self):
        r=graph(fixture(0x94000010,0xd65f03c0))
        self.assertEqual(r['instruction_count'],2)
        self.assertEqual(r['pending_edges']['0x0']['target'],'0x40')
        self.assertFalse(r['pending_edges']['0x0']['target_executed'])
        self.assertTrue(r['call_fallthrough_assumes_normal_return'])

    def test_tail_branch_to_pending_region_does_not_fall_through(self):
        r=graph(fixture(0x14000010,0))
        self.assertEqual(r['instruction_count'],1)
        self.assertEqual(r['pending_edges']['0x0']['kind'],'b')

    def test_conditional_explores_both_paths_without_feasibility_claim(self):
        r=graph(fixture(0x54000040,0xd65f03c0,0xd65f03c0))
        self.assertEqual(r['instruction_count'],3)
        self.assertFalse(r['path_feasibility_proven'])

    def test_loops_have_finite_unique_pc_inventory(self):
        r=graph(fixture(0x14000000))
        self.assertEqual(r['instruction_count'],1)
        self.assertEqual(r['instruction_index_sha256'],graph(fixture(0x14000000))['instruction_index_sha256'])

    def test_unresolved_br_is_a_frontier_without_fallthrough(self):
        r=graph(fixture(0xd61f0000,0))
        self.assertEqual(r['instruction_count'],1)
        self.assertEqual(r['indirect_edges']['0x0']['declared_targets'],[])

    def test_declared_br_table_expands_only_explicit_targets(self):
        r=graph(fixture(0xd61f0120,0,0xd65f03c0,0,0xd65f03c0),bindings={0:[8,16]})
        self.assertEqual(r['instruction_count'],3)
        self.assertEqual(r['indirect_edges']['0x0']['register'],9)

    def test_binding_does_not_silently_override_a_direct_branch(self):
        with self.assertRaises(ValueError):graph(fixture(0x14000000),bindings={0:[0]})

    def test_binding_cannot_cross_into_pending_or_unaligned_bytes(self):
        for targets in ([64],[1],[],[True]):
            with self.subTest(targets=targets),self.assertRaises(ValueError):graph(fixture(0xd61f0000),bindings={0:targets})

    def test_root_must_be_nonempty_aligned_and_inside_prefix(self):
        for roots in ((),(1,),(32,),(True,),(-4,)):
            with self.subTest(roots=roots),self.assertRaises(ValueError):graph(fixture(0xd65f03c0),roots)

    def test_branch_to_unclassified_gap_is_refused(self):
        with self.assertRaisesRegex(ValueError,'unclassified'):graph(fixture(0x1400000c))

    def test_udf_or_unsupported_branch_encoding_is_refused(self):
        for word in (0,0xd65f0fff):
            with self.subTest(word=hex(word)),self.assertRaises(ValueError):graph(fixture(word))

    def test_pc_budget_is_enforced(self):
        with self.assertRaisesRegex(ValueError,'budget'):graph(fixture(0xd503201f,0xd65f03c0),limit=1)

    def test_invalid_ranges_or_budget_are_refused(self):
        for bounds in ((0,32,(24,128)),(1,32,(64,128)),(0,32,(64,132))):
            with self.subTest(bounds=bounds),self.assertRaises(ValueError):
                prefix_graph(fixture(0xd65f03c0),[0],start=bounds[0],end=bounds[1],pending_range=bounds[2])
        for limit in (0,True):
            with self.subTest(limit=limit),self.assertRaises(ValueError):graph(fixture(0xd65f03c0),limit=limit)

    def test_exception_and_eret_are_terminal_not_executed(self):
        for word,kind in ((0xd4000003,'exception_call'),(0xd69f03e0,'eret')):
            r=graph(fixture(word,0))
            self.assertEqual(r['instruction_count'],1);self.assertEqual(r['exits']['0x0'],kind)
            self.assertFalse(r['exception_edges_modelled'])

    def test_adr_targets_are_signed_and_register_bound(self):
        self.assertEqual(adr_target(fixture(0x10000040),0,0),8)
        self.assertEqual(adr_target(fixture(0xd503201f,0x10ffffe0),4,0),0)
        with self.assertRaises(ValueError):adr_target(fixture(0x10000040),0,1)

    def test_adrp_or_unaligned_instruction_is_not_accepted_as_adr(self):
        with self.assertRaises(ValueError):adr_target(fixture(0x90000000),0,0)
        with self.assertRaises(ValueError):adr_target(fixture(0x10000040),1,0)

    def test_wrong_firmware_cli_emits_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'sboot.bin';p.write_bytes(b'wrong firmware')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_epbl_frontier.py')),str(p)],capture_output=True)
        self.assertEqual(r.returncode,2);self.assertFalse(r.stdout)


if __name__=='__main__':unittest.main()
