#!/usr/bin/env python3
"""Symbolic controls for the query path; no device response is supplied."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from check_bl2_geometry_query_gnu import dump_bytes
from inspect_bl2_geometry_query import (QUERY, PREPARE, QUERY_TEMPLATE, PREPARE_TEMPLATE,
                                      adrp_add, bfi32, decode, query_plan, table5)


def fixture():
    data = bytearray(0x31000)
    for start, template in ((QUERY, QUERY_TEMPLATE), (PREPARE, PREPARE_TEMPLATE)):
        values = [int(v, 16) for v in template.split()]
        struct.pack_into('<'+'I'*len(values), data, start, *values)
    # Deliberately different synthetic addresses for reads/writes and tables.
    struct.pack_into('<5Q', data, 0x30f98, 0x1000, 0x2000, 0x3000, 0x4000, 0x5000)
    struct.pack_into('<5Q', data, 0x30fc0, 0x6000, 0x7000, 0x8000, 0x9000, 0xa000)
    return data


class QueryTests(unittest.TestCase):
    def test_two_tables_are_derived_from_address_instructions(self):
        d = decode(fixture())
        self.assertEqual(d['query_table_offset'], 0x30f98)
        self.assertEqual(d['prepare_table_offset'], 0x30fc0)
        self.assertEqual(d['query_bases'], [0x1000, 0x2000, 0x3000, 0x4000, 0x5000])
        self.assertEqual(d['prepare_bases'], [0x6000, 0x7000, 0x8000, 0x9000, 0xa000])

    def test_bfi_fields_preserve_unrelated_control_bits(self):
        self.assertEqual(bfi32(0x33040423), dict(destination=3, source=1, lsb=28, width=2, mask=0x30000000))
        self.assertEqual(bfi32(0x330c1843), dict(destination=3, source=2, lsb=20, width=7, mask=0x07f00000))

    def test_four_slots_use_their_own_control_trigger_and_response(self):
        d = decode(fixture())
        for slot in range(4):
            with self.subTest(slot=slot):
                p = query_plan(d, slot, 0xfffffffe, 0xfffff085)
                self.assertEqual([int(v['address'], 16) for v in p['operations']],
                                 [(slot+1)*0x1000+v for v in (0, 0, 4, 12)])
                self.assertEqual([v['operation'] for v in p['operations']], ['read32', 'write32', 'write32', 'read32'])
                self.assertEqual(p['operations'][1]['value'],
                                 dict(unknown_source='old_control', preserve_mask='0xc80fffff', insert_bits='0x20500000'))
                self.assertEqual(p['operations'][2]['value'], 1)

    def test_slot_four_reads_zero_then_writes_and_reads_four(self):
        p = query_plan(decode(fixture()), 4, 1, 8)
        self.assertEqual([int(v['address'], 16) for v in p['operations']], [0x1000, 0x5000, 0x5004, 0x500c])
        self.assertEqual(p['operations'][0]['pc'], '0x284b4')

    def test_invalid_unsigned_slot_has_no_mmio_and_zero_extended_error(self):
        for slot in (5, 0x80000000, 0xffffffff):
            p = query_plan(decode(fixture()), slot, 2, 8)
            self.assertEqual(p['operations'], [])
            self.assertEqual(p['returned_x0'], '0xffffffff')

    def test_old_word_and_response_remain_unknown(self):
        p = query_plan(decode(fixture()), 0, 1, 8)
        self.assertEqual(p['returned_x0'], 'zero_extend32(unknown_response)')
        self.assertFalse(p['response_observed'])
        self.assertFalse(p['hardware_executed'])
        self.assertFalse(p['memory_map_verified'])
        self.assertNotIn('total_bytes', p)

    def test_term_two_bits_and_selector_seven_bits_only(self):
        d = decode(fixture())
        a = query_plan(d, 0, 0xfffffffd, 0xffffff85)['operations'][1]['value']
        b = query_plan(d, 0, 1, 5)['operations'][1]['value']
        self.assertEqual(a, b)
        self.assertEqual(a['insert_bits'], '0x10500000')

    def test_all_three_inputs_require_unsigned_w_values(self):
        for index in range(3):
            for value in (True, None, -1, 1 << 32, 1.0, '1'):
                args = [0, 1, 8]
                args[index] = value
                with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                    query_plan(decode(fixture()), *args)

    def test_whole_body_changes_are_refused(self):
        # Include branches, field widths, trigger value/access, response and RET.
        for offset in (0x28488, 0x284a8, 0x284b8, 0x284cc, 0x284d4, 0x284d8, 0x284e0, 0x2a284, 0x2a298):
            data = fixture()
            struct.pack_into('<I', data, offset, 0xd503201f)
            with self.subTest(offset=hex(offset)), self.assertRaises(ValueError):
                decode(data)

    def test_bfi_rejects_wrong_width_reserved_fields_and_extract_alias(self):
        for value in (0xb3040423, 0x33000423, 0x33200423, 0x3304fc23, -1, 1 << 32, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bfi32(value)

    def test_adrp_add_refuses_wrong_register_and_shifted_add(self):
        for value in (0x913e6043, 0x917e6063):
            data = fixture()
            struct.pack_into('<I', data, 0x28490, value)
            with self.assertRaises(ValueError):
                adrp_add(data, 0x2848c, 0x28490)

    def test_truncated_code_or_table_and_unaligned_table_refused(self):
        data = fixture()
        for raw in (data[:QUERY], data[:0x30fe7]):
            with self.assertRaises(ValueError):
                decode(raw)
        with self.assertRaises(ValueError):
            table5(data, 0x30f99)

    def test_cli_refuses_wrong_image_or_partial_plan_without_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'unsupported.bin'
            path.write_bytes(b'bad')
            script = str(Path(__file__).with_name('inspect_bl2_geometry_query.py'))
            for args in ([], ['--slot', '0']):
                p = subprocess.run([sys.executable, script, str(path), *args], capture_output=True, text=True)
                self.assertEqual(p.returncode, 2)
                self.assertEqual(p.stdout, '')

    def test_gnu_pointer_dump_requires_exact_unique_byte_coverage(self):
        line = ' 30f20 80241102 00000000  .$......\n'
        self.assertEqual(dump_bytes(line, 0x30f20, 8), bytes.fromhex('8024110200000000'))
        for text in ('', line + line, line.replace('00000000', '0000000'),
                     line + ' 30f28 01000000\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                dump_bytes(text, 0x30f20, 8)


if __name__ == '__main__':
    unittest.main()
