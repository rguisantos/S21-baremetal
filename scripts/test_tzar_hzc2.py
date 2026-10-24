#!/usr/bin/env python3
"""Structural refusal controls; synthetic buffers are not firmware evidence."""
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from inspect_tzar_hzc2 import archive_entries, at_address, elf64, inner_archive, span, witnesses


def archive(records):
    body = b''.join(struct.pack('<II', len(name) + 1, len(data)) + name + b'\0' + data
                    for name, data in records)
    return b'\x7f\xa5TA\0\0\0\1' + struct.pack('<II', 16 + len(body), len(records)) + body


def elf():
    data = bytearray(0x300)
    data[:7] = b'\x7fELF\2\1\1'
    struct.pack_into('<HHIQQQIHHHHHH', data, 16, 3, 183, 1, 0x100, 64, 0x180, 0, 64, 56, 1, 64, 3, 0)
    struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0, 0, 0, len(data), len(data), 0x1000)
    struct.pack_into('<I', data, 0x100, 0xd65f03c0)
    data[0x110:0x117] = b'\0entry\0'
    struct.pack_into('<IBBHQQ', data, 0x138, 1, 0x12, 0, 1, 0x100, 4)
    struct.pack_into('<IIQQQQIIQQ', data, 0x1c0, 0, 3, 0, 0, 0x110, 7, 0, 0, 1, 0)
    struct.pack_into('<IIQQQQIIQQ', data, 0x200, 0, 11, 0, 0, 0x120, 48, 1, 1, 8, 24)
    return data


class TzarTests(unittest.TestCase):
    def test_span_refuses_negative_and_truncated_ranges(self):
        for off, size in ((-1, 1), (0, -1), (2, 2), (True, 1)):
            with self.assertRaises(ValueError):
                span(b'abc', off, size)

    def test_unaligned_archive_entry_and_empty_file_are_preserved(self):
        parsed = archive_entries(archive([(b'/a', b'hello'), (b'/empty', b'')]))
        self.assertEqual(parsed['/a']['data_offset'], 27)
        self.assertEqual(parsed['/a']['data'], b'hello')
        self.assertEqual(parsed['/empty']['data'], b'')

    def test_duplicate_and_noncanonical_names_refused(self):
        for name in (b'a', b'/', b'//a', b'/a/../b', b'/a/./b', b'/a//b', b'/a/', b'/bad\0name', b'/bad\nname'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                archive_entries(archive([(name, b'')]))
        with self.assertRaises(ValueError):
            archive_entries(archive([(b'/a', b''), (b'/a', b'')]))

    def test_archive_size_count_and_magic_are_checked(self):
        for offset, value in ((0, 0), (8, 1), (12, 0), (12, 129), (16, 1), (16, 257), (20, 0xffffffff)):
            data = bytearray(archive([(b'/a', b'x')]))
            struct.pack_into('<I', data, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                archive_entries(data)

    def test_truncated_and_trailing_records_refused(self):
        valid = archive([(b'/a', b'hello')])
        for data in (valid[:-1], valid + b'x'):
            data = bytearray(data)
            struct.pack_into('<I', data, 8, len(data))
            with self.assertRaises(ValueError):
                archive_entries(data)

    def test_name_terminator_required(self):
        data = bytearray(archive([(b'/a', b'')]))
        data[26] = ord('x')
        with self.assertRaises(ValueError):
            archive_entries(data)

    def test_legacy_literal_block_and_tail_boundary(self):
        # A literal-only valid LZ4 block (16 bytes, zero matches).
        raw = bytes(range(16))
        block = b'\xf0\x01' + raw
        data = struct.pack('<III', 16, 0x184c2102, len(block)) + block + b'tail'
        decoded, end = inner_archive(data)
        self.assertEqual(decoded, raw)
        self.assertEqual(data[end:], b'tail')

    def test_legacy_limits_and_invalid_block_refused(self):
        for header in ((15, 0x184c2102, 1), (0xffffffff, 0x184c2102, 1), (16, 0, 1),
                       (16, 0x184c2102, 0), (16, 0x184c2102, 0xffffffff), (16, 0x184c2102, 1)):
            with self.subTest(header=header), self.assertRaises(ValueError):
                inner_archive(struct.pack('<III', *header) + b'\0')

    def test_ELF_symbol_and_executable_mapping(self):
        parsed = elf64(elf())
        self.assertEqual(parsed['symbols']['entry']['address'], 0x100)
        self.assertEqual(at_address(parsed, 0x100, 4, executable=True), (0x100, b'\xc0\x03\x5f\xd6'))
        self.assertEqual(witnesses(parsed, ((0x100, 0x104),))[0]['word'], 'd65f03c0')

    def test_ELF_rejects_wrong_class_machine_and_table_bounds(self):
        for offset, fmt, value in ((4, 'B', 1), (18, 'H', 40), (32, 'Q', 0x1000),
                                   (56, 'H', 129), (58, 'H', 0), (60, 'H', 4097)):
            data = elf()
            struct.pack_into('<' + fmt, data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                elf64(data)

    def test_ELF_rejects_load_past_file_and_memory_overflow(self):
        for offset, value in ((64 + 32, 0x301), (64 + 40, 1), (64 + 16, (1 << 64) - 1)):
            data = elf()
            struct.pack_into('<Q', data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                elf64(data)

    def test_ELF_rejects_bad_symbol_link_size_and_name(self):
        for offset, fmt, value in ((0x200 + 40, 'I', 4), (0x200 + 56, 'Q', 16),
                                   (0x200 + 32, 'Q', 47), (0x138, 'I', 99), (0x116, 'B', ord('x'))):
            data = elf()
            struct.pack_into('<' + fmt, data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                elf64(data)

    def test_ELF_mapping_refuses_BSS_nonexecutables_and_overlap(self):
        parsed = elf64(elf())
        for address, size in ((0x300, 4), (0x2ff, 4), (0x100, 0)):
            with self.assertRaises(ValueError):
                at_address(parsed, address, size)
        parsed['loads'][0]['flags'] = 4
        with self.assertRaises(ValueError):
            at_address(parsed, 0x100, 4, executable=True)
        parsed['loads'].append(dict(parsed['loads'][0]))
        with self.assertRaises(ValueError):
            at_address(parsed, 0x100, 4)
        parsed['loads'][1]['flags'] = 5
        with self.assertRaises(ValueError):
            at_address(parsed, 0x100, 4, executable=True)

    def test_witness_ranges_refuse_unaligned_or_empty(self):
        for bounds in ((1, 4), (4, 4), (8, 4)):
            with self.assertRaises(ValueError):
                witnesses(elf64(elf()), (bounds,))

    def test_wrong_firmware_CLI_emits_no_JSON(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'wrong.img'
            path.write_bytes(b'\0' * 4)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('inspect_tzar_hzc2.py')), str(path)],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
