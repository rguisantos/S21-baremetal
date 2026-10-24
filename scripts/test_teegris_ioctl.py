#!/usr/bin/env python3
"""Synthetic ELF grammar/ABI controls; no device responses are supplied."""
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from inspect_teegris_ioctl import (VERSYM, VERDEF, VERNEED, dynamic_names, jump_slot,
    normalize_return, plt_slot, string, symbol_version_index, version_records)

STRINGS = b'\0libtzsl.so\0TEEGRIS_4\0PARENT\0'
LIB, VERSION, PARENT = [STRINGS.index(x) for x in (b'libtzsl.so', b'TEEGRIS_4', b'PARENT')]


def metadata(kind, raw, *, count=1, link=1, entsize=0):
    data = bytearray(0x300)
    data[:len(STRINGS)] = STRINGS
    data[0x80:0x80 + len(raw)] = raw
    section = (0, kind, 0, 0, 0x80, len(raw), link, count, 1, entsize)
    strings = (0, 3, 0, 0, 0, len(STRINGS), 0, 0, 1, 0)
    return dict(data=bytes(data), sections=[(0,) * 10, strings, section, (0,) * 10],
        dynsym_section_index=3, dynsym_count=2, symbols={'ioctl': dict(index=1)},
        loads=[dict(offset=0, address=0, size=len(data), flags=6)])


def needed():
    return struct.pack('<HHIII', 1, 1, LIB, 16, 0) + struct.pack('<IHHII', 0, 0, 4, VERSION, 0)


def defined():
    return struct.pack('<HHHHIII', 1, 0, 2, 1, 0, 20, 0) + struct.pack('<II', VERSION, 0)


class IoctlTests(unittest.TestCase):
    def test_return_error_interval_and_excluded_boundary(self):
        for signed in (-1, -2, -4095):
            self.assertEqual(normalize_return(signed & ((1 << 64) - 1)),
                dict(return_w0=0xffffffff, errno_word=-signed))
        self.assertEqual(normalize_return((1 << 64) - 4096), dict(return_w0=0xfffff000, errno_word=None))
        self.assertEqual(normalize_return(0), dict(return_w0=0, errno_word=None))

    def test_return_truncation_and_explicit_input_requirement(self):
        self.assertEqual(normalize_return(0x100000001), dict(return_w0=1, errno_word=None))
        self.assertEqual(normalize_return(0xffffffff), dict(return_w0=0xffffffff, errno_word=None))
        for invalid in (True, -1, 1 << 64, None, 1.0):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                normalize_return(invalid)

    def test_string_offsets_termination_and_length_are_checked(self):
        self.assertEqual(string(STRINGS, VERSION), 'TEEGRIS_4')
        for table, index in ((STRINGS, len(STRINGS)), (STRINGS, -1), (b'bad', 0), (b'x' * 1024 + b'\0', 0)):
            with self.assertRaises(ValueError):
                string(table, index)

    def test_dynamic_needed_soname_and_NULL(self):
        raw = struct.pack('<6Q', 1, LIB, 14, LIB, 0, 0)
        self.assertEqual(dynamic_names(metadata(6, raw, entsize=16)), dict(needed=['libtzsl.so'], soname='libtzsl.so'))
        for raw in (struct.pack('<4Q', 1, LIB, 1, LIB), struct.pack('<4Q', 14, LIB, 14, LIB),
                    struct.pack('<2Q', 1, LIB), struct.pack('<4Q', 0, 0, 1, LIB), struct.pack('<2Q', 0, 1)):
            with self.assertRaises(ValueError):
                dynamic_names(metadata(6, raw, entsize=16))

    def test_dynamic_table_and_link_limits(self):
        for fake in (metadata(6, b'\0' * 15, entsize=16), metadata(6, b'\0' * 16, entsize=8),
                     metadata(6, b'\0' * 16, entsize=16, link=9), metadata(6, b'\0' * 16, entsize=16, link=0)):
            with self.assertRaises(ValueError):
                dynamic_names(fake)

    def test_version_symbol_index_and_hidden_flag(self):
        elf = metadata(VERSYM, struct.pack('<2H', 0, 0x8004), entsize=2, link=3)
        self.assertEqual(symbol_version_index(elf, 'ioctl'), (4, True))
        for raw, link in ((struct.pack('<H', 4), 3), (struct.pack('<2H', 0, 4), 1),
                          (struct.pack('<2H', 0, 0x8001), 3)):
            with self.assertRaises(ValueError):
                symbol_version_index(metadata(VERSYM, raw, entsize=2, link=link), 'ioctl')

    def test_need_and_definition_match_by_label_not_local_index(self):
        need = version_records(metadata(VERNEED, needed()), VERNEED)
        definition = version_records(metadata(VERDEF, defined()), VERDEF)
        self.assertEqual(need[4], dict(version='TEEGRIS_4', library='libtzsl.so'))
        self.assertEqual(definition[2], dict(version='TEEGRIS_4', library=None))

    def test_version_chain_malformed_headers_and_offsets(self):
        for offset, fmt, value in ((0, 'H', 2), (2, 'H', 0), (2, 'H', 65), (8, 'I', 0),
                                   (8, 'I', 31), (12, 'I', 16), (22, 'H', 1), (24, 'I', 999), (28, 'I', 16)):
            raw = bytearray(needed())
            struct.pack_into('<' + fmt, raw, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                version_records(metadata(VERNEED, raw), VERNEED)
        for count in (0, 2, 65):
            with self.assertRaises(ValueError):
                version_records(metadata(VERNEED, needed(), count=count), VERNEED)

    def test_version_need_duplicates_and_backwards_auxiliary_are_rejected(self):
        header = struct.pack('<HHIII', 1, 2, LIB, 16, 0)
        first = struct.pack('<IHHII', 0, 0, 4, VERSION, 16)
        last = struct.pack('<IHHII', 0, 0, 4, VERSION, 0)
        with self.assertRaises(ValueError):
            version_records(metadata(VERNEED, header + first + last), VERNEED)
        bad = bytearray(header + first + last)
        struct.pack_into('<I', bad, 28, 4)
        with self.assertRaises(ValueError):
            version_records(metadata(VERNEED, bad), VERNEED)

    def test_verdef_parent_auxiliary_does_not_create_another_definition(self):
        raw = struct.pack('<HHHHIII', 1, 0, 2, 2, 0, 20, 0) + struct.pack('<4I', VERSION, 8, PARENT, 0)
        self.assertEqual(version_records(metadata(VERDEF, raw), VERDEF), {2: dict(version='TEEGRIS_4', library=None)})

    def test_version_sections_and_string_links_are_unambiguous(self):
        elf = metadata(VERNEED, needed())
        elf['sections'].append(elf['sections'][2])
        with self.assertRaises(ValueError):
            version_records(elf, VERNEED)
        with self.assertRaises(ValueError):
            version_records(metadata(VERNEED, needed(), link=3), VERNEED)

    def test_jump_slot_unique_symbol_type_addend_and_bounds(self):
        raw = struct.pack('<QQq', 0x200, 1 << 32 | 1026, 0)
        self.assertEqual(jump_slot(metadata(4, raw, link=3, entsize=24), 'ioctl'), 0x200)
        for candidate in (raw + raw, struct.pack('<QQq', 0x200, 1 << 32 | 1026, 1),
                          struct.pack('<QQq', 0x200, 2 << 32 | 1026, 0),
                          struct.pack('<QQq', 0x300, 1 << 32 | 1026, 0),
                          struct.pack('<QQq', 0x200, 1 << 32 | 1025, 0), raw[:-1]):
            with self.subTest(raw=candidate.hex()), self.assertRaises(ValueError):
                jump_slot(metadata(4, candidate, link=3, entsize=24), 'ioctl')

    def test_PLT_registers_offsets_and_signed_ADRP(self):
        words = (0x900002d0, 0xf9434e11, 0x911a6210, 0xd61f0220)
        self.assertEqual(plt_slot(struct.pack('<4I', *words), 0x9760), 0x61698)
        negative = (0xf0fffff0, *words[1:])  # ADRP X16, previous page.
        self.assertEqual(plt_slot(struct.pack('<4I', *negative), 0x2000), 0x1698)
        for index, word in ((0, words[0] ^ 1), (1, words[1] ^ (1 << 30)),
                             (2, words[2] ^ (1 << 10)), (2, words[2] | (1 << 22)), (3, 0xd61f0200)):
            bad = list(words)
            bad[index] = word
            with self.assertRaises(ValueError):
                plt_slot(struct.pack('<4I', *bad), 0x9760)

    def test_PLT_bounds_are_explicit(self):
        for raw, pc in ((b'\0' * 15, 0), (b'\0' * 16, 1), (b'\0' * 16, -4), (b'\0' * 16, True)):
            with self.assertRaises(ValueError):
                plt_slot(raw, pc)

    def test_wrong_firmware_CLI_emits_no_partial_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'wrong.img'
            path.write_bytes(b'\0' * 4)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('inspect_teegris_ioctl.py')), str(path)],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
