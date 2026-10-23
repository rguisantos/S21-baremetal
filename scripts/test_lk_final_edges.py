"""Static control-flow boundaries, not emulation of cache or secure firmware."""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from inspect_lk_final_edges import flow, walk, table_targets, TABLE

RET, NOP, BR_X3, BLR_X3 = 0xd65f03c0, 0xd503201f, 0xd61f0060, 0xd63f0060


def graph(words, roots=(0,), **kw):
    data = struct.pack('<' + 'I' * len(words), *words)
    return walk(data, roots, start=0, end=len(data), **kw)


class FinalEdges(unittest.TestCase):
    def test_signed_immediates_use_instruction_pc(self):
        self.assertEqual(flow(0x97ffffff, 0x100), ('bl', 0xfc))
        self.assertEqual(flow(0x14000002, 0x100), ('b', 0x108))
        self.assertEqual(flow(0x54ffffe0, 0x100), ('conditional', 0xfc))

    def test_all_conditional_families_explore_both_paths(self):
        for word in (0x54000040, 0x34000040, 0xb5000040, 0x36000040, 0xb7000040):
            with self.subTest(word=hex(word)):
                self.assertEqual(set(graph([word, RET, RET])['visited']), {0, 4, 8})

    def test_call_includes_callee_and_return_continuation(self):
        g = graph([0x94000002, RET, RET])
        self.assertEqual(set(g['visited']), {0, 4, 8})
        self.assertEqual(g['calls'], {0: 8})

    def test_tail_branch_does_not_fall_through(self):
        self.assertEqual(set(graph([0x14000002, 0, RET])['visited']), {0, 8})

    def test_loop_is_bounded_by_unique_pcs(self):
        self.assertEqual(set(graph([0x14000000])['visited']), {0})

    def test_unknown_indirect_branch_is_not_invented(self):
        g = graph([BR_X3, NOP, RET])
        self.assertEqual(set(g['visited']), {0})
        self.assertEqual(g['indirect'][0], {'kind': 'br', 'register': 3})

    def test_indirect_call_keeps_continuation_and_explicit_expansion(self):
        g = graph([BLR_X3, RET, RET], bindings={0: {'targets': [8], 'basis': 'supplied template'}})
        self.assertEqual(set(g['visited']), {0, 4, 8})
        self.assertEqual(g['indirect'][0]['targets'], [8])

    def test_handoff_boundary_stops_before_payload_and_requires_blr(self):
        g = graph([0xd63f0080, NOP, RET], terminal=[0])
        self.assertEqual(set(g['visited']), {0})
        self.assertEqual(g['exits'][0], {'kind': 'handoff_boundary', 'register': 4})
        with self.assertRaisesRegex(ValueError, 'BLR'):
            graph([BR_X3], terminal=[0])

    def test_escape_and_unaligned_expansion_rejected(self):
        for words, extra in (([0x17ffffff], {}), ([BR_X3], {'bindings': {0: {'targets': [2]}}})):
            with self.subTest(words=words), self.assertRaisesRegex(ValueError, 'aligned LK'):
                graph(words, **extra)

    def test_pc_budget_and_bad_code_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError, 'budget'):
            graph([NOP, RET], limit=1)
        for start, end in ((1, 4), (0, 3), (0, 8), (4, 4)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                walk(struct.pack('<I', RET), [0], start=start, end=end)

    def test_secure_calls_recorded_without_assigning_a_handler(self):
        for instruction in (0xd4000001, 0xd4000002, 0xd4000003):
            g = graph([instruction, RET])
            self.assertEqual(g['exits'][0]['kind'], 'exception_call')
            self.assertFalse(g['calls'])
        self.assertEqual(set(graph([0xd69f03e0, NOP])['visited']), {0})

    def test_unknown_control_fails_closed(self):
        for word in (0xd4200000, 0xd4400000, 0x54000050):
            with self.subTest(word=hex(word)), self.assertRaisesRegex(ValueError, 'unsupported A64'):
                flow(word, 0)

    def test_system_words_are_inventory_not_executed(self):
        g = graph([0xd5381003, 0xd50342df, 0xd50b7427, RET])
        self.assertEqual(g['systems'], {0: 0xd5381003, 4: 0xd50342df, 8: 0xd50b7427})

    def test_signed_table_and_invalid_targets(self):
        data = bytearray(TABLE + 182)
        struct.pack_into('<h', data, TABLE, -22)
        self.assertEqual(table_targets(data)[0], 0x1b06c0)
        self.assertEqual(len(table_targets(data)), 91)
        struct.pack_into('<h', data, TABLE, 32767)
        with self.assertRaisesRegex(ValueError, 'outside known'):
            table_targets(data)
        with self.assertRaises(ValueError):
            table_targets(data[:-1])
        with self.assertRaises(ValueError):
            table_targets(data, count=92)

    def test_wrong_firmware_does_not_produce_an_evidence_report(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'sboot.bin';p.write_bytes(b'not HZC2')
            proc = subprocess.run([sys.executable, str(Path(__file__).with_name('inspect_lk_final_edges.py')), str(p)], capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b'')
        self.assertIn(b'unsupported image', proc.stderr)


if __name__ == '__main__':
    unittest.main()
