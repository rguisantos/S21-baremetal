"""Host tests for the offline inspector's fail-closed input boundaries."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from inspect_el2_hzc2 import (constant_return, instruction, jump_table_target,
                             pointer_offset, read_exact)


class ImageBoundaryTests(unittest.TestCase):
    def test_exact_identity_and_corruption(self):
        data = b'fixture-image'
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.bin'
            path.write_bytes(data)
            self.assertEqual(read_exact(path, len(data), digest), data)
            for damaged in (data[:-1], data + b'X', b'F' + data[1:]):
                path.write_bytes(damaged)
                with self.subTest(damaged=damaged), self.assertRaises(ValueError):
                    read_exact(path, len(data), digest)

    def test_read_is_bounded(self):
        class Stream:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, count):
                self.count = count
                return b'x' * count

        from unittest.mock import patch
        stream = Stream()
        with patch.object(Path, 'open', return_value=stream):
            with self.assertRaises(ValueError):
                read_exact('untrusted', 16, 'unused')
        self.assertEqual(stream.count, 17)

    def test_pointer_must_have_file_backing(self):
        base, length = 0xc1400000, 0x100
        self.assertEqual(pointer_offset(base, base, length), 0)
        self.assertEqual(pointer_offset(base + 0xfc, base, length), 0xfc)
        for pointer, width in ((base - 4, 4), (base + 2, 4),
                               (base + 0x100, 4), (base + 0xfc, 8),
                               (base, 0)):
            with self.subTest(pointer=pointer, width=width), self.assertRaises(ValueError):
                pointer_offset(pointer, base, length, width)


class ConstantPathTests(unittest.TestCase):
    def test_wide_immediates_and_expected_exit(self):
        # MOVZ X28,#0x1234; MOVK #0x5678,LSL#16; MOVK #0x9abc,LSL#32; B +12.
        data = struct.pack('<4I', 0xd282469c, 0xf2aacf1c, 0xf2d3579c, 0x14000003) + bytes(12)
        self.assertEqual(constant_return(data, 0, 24),
                         dict(value=0x9abc56781234, branch_offset=12))
        # A backward branch must be sign extended, independently of the table.
        data = bytes(16) + struct.pack('<2I', 0xd280003c, 0x17fffffb)
        self.assertEqual(constant_return(data, 16, 0)['value'], 1)

    def test_unresolved_or_unexpected_paths_are_rejected(self):
        cases = [
            [0xf2aacf1c, 0x14000001],  # MOVK before MOVZ
            [0xd280003b, 0x14000001],  # wrong register
            [0xd280003c, 0x94000001],  # BL instead of B
            [0xd280003c, 0x14000002],  # wrong exit
            [0xf940001c, 0x14000001],  # dynamic load into X28
            [0xd280003c, 0xd280003c],  # second MOVZ
            [0xd280003c],              # missing branch / truncated path
        ]
        for case in cases:
            data = struct.pack('<' + 'I' * len(case), *case) + bytes(16)
            with self.subTest(case=case), self.assertRaises(ValueError):
                constant_return(data, 0, 8)
        with self.assertRaises(ValueError):
            constant_return(struct.pack('<7I', 0xd280003c, *([0xf280001c] * 5), 0), 0, 24)
        with self.assertRaises(ValueError):
            constant_return(struct.pack('<I', 0xd280003c), 0, 0)

    def test_signed_halfword_jump_table_and_bounds(self):
        data = bytearray(64)
        struct.pack_into('<3h', data, 0, 0, 1, -2)
        self.assertEqual([jump_table_target(data, 0, i, 32) for i in range(3)],
                         [32, 36, 24])
        for table, index, base in ((0, -1, 32), (64, 0, 32), (0, 0, 64),
                                   (0, 0, -4), (0, 0, 33)):
            with self.subTest(table=table, index=index, base=base), self.assertRaises(ValueError):
                jump_table_target(data, table, index, base)
        for offset in (-4, 2, 64):
            with self.assertRaises(ValueError):
                instruction(data, offset)


if __name__ == '__main__':
    unittest.main()
