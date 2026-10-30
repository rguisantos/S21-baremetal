#!/usr/bin/env python3
"""Test literal parsing, bounded C declarations and host ABI agreement."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from inspect_flop_reference import host_layout, inspect, numeric_define, packet_declaration


DECLARATION = '''struct rpmb_packet {
u16 request; u16 result; u16 count; u16 address; u32 write_counter;
u8 nonce[16]; u8 data[256]; u8 Key_MAC[32]; u8 stuff[196];
};'''


class LiteralTests(unittest.TestCase):
    def test_decimal_hex_parentheses_and_identical_duplicates(self):
        self.assertEqual(numeric_define('#define N 512\n', 'N'), 512)
        self.assertEqual(numeric_define('#define N (0X200)\n#define N 512\n', 'N'), 512)

    def test_names_are_matched_exactly(self):
        self.assertEqual(numeric_define('#define NX 1\n#define N 2\n', 'N'), 2)
        with self.assertRaisesRegex(ValueError, 'missing'):
            numeric_define('#define NX 1\n', 'N')

    def test_conflicting_duplicates_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            numeric_define('#define N 1\n#define N 2\n', 'N')

    def test_expressions_aliases_octal_and_comments_are_not_evaluated(self):
        for value in ('1 << 7', '(1 + 2)', 'OTHER', '010', '512 /* x */', '__import__("os")'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'nonliteral'):
                numeric_define('#define N '+value+'\n', 'N')


class DeclarationTests(unittest.TestCase):
    def test_fixed_width_fields_preserve_order_and_dimensions(self):
        declaration, fields = packet_declaration(DECLARATION)
        self.assertEqual(declaration, DECLARATION)
        self.assertEqual(fields[:2], [('request', 'u16', 1), ('result', 'u16', 1)])
        self.assertEqual(fields[-1], ('stuff', 'u8', 196))

    def test_missing_or_duplicate_struct_is_refused(self):
        for text in ('', DECLARATION+DECLARATION):
            with self.subTest(text=text[:20]), self.assertRaisesRegex(ValueError, 'one RPMB'):
                packet_declaration(text)

    def test_pointers_unions_attributes_and_array_expressions_are_refused(self):
        for field in ('u8 *data;', 'union { u8 x; };', 'u8 data[16*2];',
                      'u64 data;', 'u8 data[0];', 'u8 x __attribute__((aligned(8)));'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                packet_declaration('struct rpmb_packet {'+field+'};')

    def test_duplicate_and_empty_fields_are_refused(self):
        for fields in ('', 'u8 data;u8 data;'):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'duplicate'):
                packet_declaration('struct rpmb_packet {'+fields+'};')

    def test_host_c_compiler_confirms_layout_and_total_size(self):
        declaration, fields = packet_declaration(DECLARATION)
        result = host_layout(declaration, fields)
        self.assertEqual(result['bytes'], 512)
        self.assertEqual(result['fields']['write_counter'], {'offset': 8, 'bytes': 4})
        self.assertEqual(result['fields']['Key_MAC'], {'offset': 284, 'bytes': 32})

    def test_changed_field_width_is_rejected_by_host_layout_comparison(self):
        declaration, fields = packet_declaration(DECLARATION.replace('u32 write_counter', 'u16 write_counter'))
        with self.assertRaisesRegex(ValueError, 'layout differs'):
            host_layout(declaration, fields)


class SourceRefusalTests(unittest.TestCase):
    def test_wrong_source_bytes_refused_before_host_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = json.loads(Path(__file__).resolve().parents[1].joinpath(
                'docs/references/flop-kernel-source-4553117.json').read_text())
            path = Path(directory)/manifest['files'][0]['path']
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'wrong')
            with patch('inspect_flop_reference.host_layout') as compiled:
                with self.assertRaisesRegex(ValueError, 'source bytes differ'):
                    inspect(directory)
                compiled.assert_not_called()

    def test_missing_sources_refused_before_host_compiler(self):
        with tempfile.TemporaryDirectory() as directory, patch('inspect_flop_reference.host_layout') as compiled:
            with self.assertRaises(FileNotFoundError):
                inspect(directory)
            compiled.assert_not_called()


if __name__ == '__main__':
    unittest.main()
