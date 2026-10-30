#!/usr/bin/env python3
"""Exercise refusals of the static witness checker without Samsung firmware."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from check_epbl_protocol_gnu import parse_lines
from inspect_lk_precopy_measurement import inspect, verify_disassembly


class WitnessTests(unittest.TestCase):
    def setUp(self):
        # B +8; NOP; RET. The graph must preserve an out-of-slice branch.
        self.data = struct.pack('<3I', 0x14000002, 0xd503201f, 0xd65f03c0)
        self.lines = parse_lines('0: 14000002 b 0x8\n4: d503201f nop\n8: d65f03c0 ret\n')
        self.blocks = {'fragment': (0, 8)}
        self.fragment = {pc: row for pc, row in self.lines.items() if pc < 8}

    def check_fragment(self, **kwargs):
        return verify_disassembly(kwargs.get('data', self.data),
            kwargs.get('lines', self.fragment), kwargs.get('blocks', self.blocks),
            kwargs.get('selected'))

    def test_branch_to_frontier_is_preserved(self):
        self.assertEqual(self.check_fragment(), {'0x0': {'kind': 'b', 'target': '0x8'}})

    def test_missing_word_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'coverage'):
            self.check_fragment(lines={0: self.lines[0]})

    def test_extra_word_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'coverage'):
            self.check_fragment(lines=self.lines)

    def test_overlapping_blocks_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            self.check_fragment(blocks={'one': (0, 8), 'two': (4, 8)})

    def test_invalid_bounds_are_rejected(self):
        for bounds in ((-4, 4), (1, 8), (0, 6), (4, 4), (0, 16), (False, 4)):
            with self.subTest(bounds=bounds), self.assertRaisesRegex(ValueError, 'block'):
                self.check_fragment(blocks={'bad': bounds})
        with self.assertRaisesRegex(ValueError, 'coverage'):
            self.check_fragment(blocks={})

    def test_changed_raw_bytes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'word/instruction'):
            self.check_fragment(data=struct.pack('<3I', 0x14000003, 0xd503201f, 0xd65f03c0))

    def test_misdecoded_target_is_rejected(self):
        changed = dict(self.fragment)
        changed[0] = (0x14000002, 'b', '0xc')
        with self.assertRaisesRegex(ValueError, 'target'):
            self.check_fragment(lines=changed)

    def test_unclassified_gnu_branch_is_rejected(self):
        changed = dict(self.fragment)
        changed[4] = (0xd503201f, 'b', '0x8')
        with self.assertRaisesRegex(ValueError, 'unclassified'):
            self.check_fragment(lines=changed)

    def test_undefined_or_undecoded_instruction_is_rejected(self):
        for mnemonic in ('udf', '.inst'):
            changed = dict(self.fragment)
            changed[4] = (0xd503201f, mnemonic, '')
            with self.subTest(mnemonic=mnemonic), self.assertRaisesRegex(ValueError, 'instruction'):
                self.check_fragment(lines=changed)

    def test_selected_operands_and_absence_are_checked(self):
        self.check_fragment(selected={0: ('b', '0x8')})
        for selected in ({0: ('b', '0xc')}, {8: ('ret', '')}):
            with self.subTest(selected=selected), self.assertRaisesRegex(ValueError, 'operands'):
                self.check_fragment(selected=selected)

    def test_duplicate_gnu_pc_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            parse_lines('0: 14000002 b 0x8\n0: 14000002 b 0x8\n')

    def test_wrong_image_refused_before_objdump(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'not-sboot.bin'
            path.write_bytes(b'not Samsung firmware')
            with self.assertRaisesRegex(ValueError, 'unsupported image'):
                inspect(path)
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('inspect_lk_precopy_measurement.py')), str(path)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
