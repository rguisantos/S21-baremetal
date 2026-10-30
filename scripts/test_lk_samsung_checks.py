#!/usr/bin/env python3
"""Test exact pointer-table decoding and request field binding on the host."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_samsung_checks import inspect, pointer_names, request_fields, store_unsigned_x


def fixture():
    data = bytearray(256)
    for index, (offset, name) in enumerate(((64, b'BOOT'), (80, b'INIT_BOOT'),
                                          (112, b'VDDCAL_FWINIT_BOOT'))):
        struct.pack_into('<Q', data, index*8, 0x80000000+offset)
        data[offset:offset+len(name)+1] = name+b'\0'
    return data


class NameTableTests(unittest.TestCase):
    def test_exact_names_and_pointer_order_are_preserved(self):
        rows = pointer_names(fixture(), 0, 3, 0x80000000)
        self.assertEqual([r['name'] for r in rows], ['BOOT', 'INIT_BOOT', 'VDDCAL_FWINIT_BOOT'])
        self.assertEqual([r['file_offset'] for r in rows], ['0x40', '0x50', '0x70'])
        self.assertEqual([r['index'] for r in rows], [0, 1, 2])

    def test_concatenated_literal_is_not_split_or_normalized(self):
        row = pointer_names(fixture(), 16, 1, 0x80000000)[0]
        self.assertEqual(row['name'], 'VDDCAL_FWINIT_BOOT')
        self.assertNotEqual(row['name'], 'INIT_BOOT')

    def test_duplicate_pointers_are_not_silently_deduplicated(self):
        data = fixture(); data[8:16] = data[:8]
        self.assertEqual([r['name'] for r in pointer_names(data, 0, 2, 0x80000000)], ['BOOT', 'BOOT'])

    def test_case_is_preserved(self):
        data = fixture(); data[64:68] = b'boot'
        self.assertEqual(pointer_names(data, 0, 1, 0x80000000)[0]['name'], 'boot')

    def test_invalid_table_types_counts_and_extents_are_refused(self):
        for table, count, delta, cap in ((-1, 1, 0, 127), (0, 0, 0, 127),
                (0, 257, 0, 127), (250, 1, 0, 127), (0, 1, -1, 127),
                (0, 1, 0, 0), (False, 1, 0, 127), (0, 1.5, 0, 127)):
            with self.subTest(table=table, count=count, delta=delta, cap=cap), self.assertRaisesRegex(ValueError, 'bounds'):
                pointer_names(fixture(), table, count, delta, cap)

    def test_pointers_outside_file_are_refused(self):
        for pointer in (0x7fffffff, 0x80000100, 0xffffffffffffffff):
            data = fixture(); struct.pack_into('<Q', data, 0, pointer)
            with self.subTest(pointer=pointer), self.assertRaisesRegex(ValueError, 'outside file'):
                pointer_names(data, 0, 1, 0x80000000)

    def test_empty_unterminated_and_non_ascii_names_are_refused(self):
        for content in (b'\0', b'X'*192, b'\xff\0'):
            data = fixture(); data[64:64+len(content)] = content
            with self.subTest(content=content[:4]), self.assertRaises(ValueError):
                pointer_names(data, 0, 1, 0x80000000)

    def test_length_bound_is_inclusive_and_requires_nul(self):
        data = fixture(); data[64:70] = b'ABCDE\0'
        self.assertEqual(pointer_names(data, 0, 1, 0x80000000, 5)[0]['name'], 'ABCDE')
        with self.assertRaisesRegex(ValueError, 'terminated'):
            pointer_names(data, 0, 1, 0x80000000, 4)

    def test_truncated_pointer_record_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'bounds'):
            pointer_names(bytes(7), 0, 1, 0)


class RequestTests(unittest.TestCase):
    def test_three_request_fields_are_bound_to_expected_registers(self):
        fields = request_fields({0x17dbfc: 0xa902da75, 0x17dbf8: 0xf9001e62})
        self.assertEqual(list(fields), ['40', '48', '56'])
        self.assertIn('image pointer', fields['40'])
        self.assertIn('length', fields['48'])
        self.assertIn('trailer pointer', fields['56'])

    def test_pair_register_base_and_offset_mutations_are_refused(self):
        for bit in (1, 1 << 10, 1 << 5, 1 << 15):
            with self.subTest(bit=bit), self.assertRaisesRegex(ValueError, 'binding'):
                request_fields({0x17dbfc: 0xa902da75^bit, 0x17dbf8: 0xf9001e62})

    def test_single_store_register_base_and_offset_mutations_are_refused(self):
        for bit in (1, 1 << 5, 1 << 10):
            with self.subTest(bit=bit), self.assertRaisesRegex(ValueError, 'binding'):
                request_fields({0x17dbfc: 0xa902da75, 0x17dbf8: 0xf9001e62^bit})

    def test_x_store_immediates_are_scaled_by_eight(self):
        self.assertEqual(store_unsigned_x(0xf9001e62), (2, 19, 56))
        self.assertEqual(store_unsigned_x(0xf93ffc20), (0, 1, 32760))

    def test_other_store_forms_width_load_and_non_word_are_refused(self):
        for word in (0xb9001e62, 0xf9401e62, 0xf8008462, -1, 0x1f9001e62, True):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, 'STR X'):
                store_unsigned_x(word)


class RefusalTests(unittest.TestCase):
    def test_bad_image_is_refused_before_disassembly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'
            for content in (b'not firmware', bytes(IMAGES['sboot'][0])):
                path.write_bytes(content)
                with self.subTest(size=len(content)), patch('inspect_lk_samsung_checks.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError, 'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_failure_produces_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'; path.write_bytes(b'bad')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('inspect_lk_samsung_checks.py')), str(path)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
