#!/usr/bin/env python3
"""Static continuation summaries keep calls, return registers and frontiers separate."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_lk_payload_return import summarize_local

RET, NOP = 0xd65f03c0, 0xd503201f


def graph(words, **kwargs):
    data = struct.pack('<'+'I'*len(words), *words)
    return summarize_local(data, 0, 0, len(data), **kwargs)


class LocalControl(unittest.TestCase):
    def test_call_records_conditional_return_without_exploring_callee(self):
        result = graph([0x94000002, RET, NOP])
        self.assertEqual(result['visited_pcs'], ['0x0','0x4'])
        self.assertEqual(result['calls']['0x0'],
                         {'kind':'bl','target':'0x8','conditional_normal_return':'0x4'})

    def test_call_to_external_address_stays_opaque(self):
        result = graph([0x94000010, RET])
        self.assertEqual(result['calls']['0x0']['target'], '0x40')
        self.assertFalse(result['feasibility_and_runtime_context_established'])

    def test_call_at_block_end_records_return_frontier(self):
        result = graph([0x94000010])
        self.assertEqual(result['frontiers'], [{'pc':'0x0','target':'0x4','kind':'conditional_call_return'}])

    def test_conditional_families_keep_both_paths(self):
        for word in (0x54000040, 0x34000040, 0xb5000040, 0x36000040, 0xb7000040):
            with self.subTest(word=hex(word)):
                self.assertEqual(graph([word,RET,RET])['visited_pcs'], ['0x0','0x4','0x8'])

    def test_outside_conditional_target_does_not_remove_fallthrough(self):
        result = graph([0x54000080, RET])
        self.assertEqual(result['visited_pcs'], ['0x0','0x4'])
        self.assertEqual(result['frontiers'], [{'pc':'0x0','target':'0x10','kind':'conditional'}])

    def test_tail_transfer_has_no_fallthrough(self):
        result = graph([0x14000004, NOP, RET])
        self.assertEqual(result['visited_pcs'], ['0x0'])
        self.assertEqual(result['frontiers'], [{'pc':'0x0','target':'0x10','kind':'b'}])

    def test_loop_and_budget(self):
        self.assertEqual(graph([0x14000000])['instruction_count'], 1)
        with self.assertRaisesRegex(ValueError,'budget'):
            graph([NOP,RET],limit=1)

    def test_indirect_branch_stops_with_unknown_target(self):
        result = graph([0xd61f0060, RET])
        self.assertEqual(result['visited_pcs'], ['0x0'])
        self.assertEqual(result['frontiers'], [{'pc':'0x0','kind':'br','register':3}])

    def test_indirect_call_preserves_only_conditional_continuation(self):
        result = graph([0xd63f0060, RET])
        self.assertEqual(result['calls']['0x0'],
                         {'kind':'blr','register':3,'conditional_normal_return':'0x4'})
        self.assertNotIn('target',result['calls']['0x0'])

    def test_ret_register_is_not_a_resolved_address(self):
        self.assertEqual(graph([RET])['return_registers'], {'0x0':30})
        self.assertEqual(graph([0xd65f0060])['return_registers'], {'0x0':3})

    def test_secure_transfers_terminate_without_assigning_handler(self):
        for word, kind in ((0xd4000001,'exception_call'), (0xd4000002,'exception_call'),
                           (0xd4000003,'exception_call'), (0xd69f03e0,'eret'), (0,'udf')):
            with self.subTest(word=hex(word)):
                result=graph([word,RET])
                self.assertEqual(result['visited_pcs'],['0x0'])
                self.assertEqual(result['frontiers'][0]['kind'],kind)

    def test_system_inventory_and_unknown_control(self):
        self.assertEqual(graph([0xd5381003,NOP,RET])['system_sites'],['0x0','0x4'])
        for word in (0xd4200000,0xd4400000,0x54000050):
            with self.subTest(word=hex(word)),self.assertRaisesRegex(ValueError,'unsupported A64'):
                graph([word])

    def test_invalid_bounds_and_types(self):
        data=struct.pack('<I',RET)
        for root,low,high in ((0,0,3),(0,0,8),(1,0,4),(0,4,4),(0,-4,4),(0,False,4)):
            with self.subTest(bounds=(root,low,high)),self.assertRaises(ValueError):
                summarize_local(data,root,low,high)
        for budget in (0,-1,True,1.0):
            with self.subTest(budget=budget),self.assertRaises(ValueError):graph([RET],limit=budget)

    def test_wrong_firmware_refused_without_json(self):
        script=Path(__file__).with_name('inspect_lk_payload_return.py')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'wrong.bin'
            for payload in (b'not HZC2',bytes(4194304)):
                path.write_bytes(payload)
                result=subprocess.run([sys.executable,str(script),str(path)],capture_output=True)
                self.assertEqual(result.returncode,2)
                self.assertEqual(result.stdout,b'')
                self.assertIn(b'inspect_lk_payload_return:',result.stderr)
                self.assertEqual(path.read_bytes(),payload)


if __name__=='__main__':
    unittest.main()
