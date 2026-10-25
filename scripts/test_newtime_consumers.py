"""Boundaries of the static search/parser and supplied column12 bit fields."""
import struct
import unittest

from inspect_newtime_consumers_hzc2 import (
    branch_candidates, column12_word, directory_entries, occurrences,
)


class ConsumerTests(unittest.TestCase):
    def test_column12_first_shared_word(self):
        result = column12_word(0x1390)
        self.assertEqual(result['selector_bits_16_12'], 1)
        self.assertEqual(result['helper_2cbec_w3_sequence'], [1, 1, 1])
        self.assertEqual(result['action_nibbles_11_8_7_4_3_0'], [3, 9, 0])
        self.assertEqual(result['helper_2cd1c_commands'],
                         [dict(w2=9,w3=8), dict(w2=57,w3=0), dict(w2=9,w3=1)])

    def test_column12_separates_selector_from_unused_high_bits(self):
        result = column12_word(0xfffe0000 | 0x1f000 | 0x789)
        self.assertEqual(result['selector_bits_16_12'], 31)
        self.assertEqual(result['helper_2cbec_w3_sequence'], [2, 4, 1])
        self.assertEqual(result['helper_2cd1c_commands'],
                         [dict(w2=9,w3=128), dict(w2=73,w3=0), dict(w2=57,w3=0)])

    def test_column12_actions_ten_and_unhandled_nibbles(self):
        self.assertEqual(column12_word(0x2abf)['helper_2cd1c_commands'],
                         [dict(w2=59,w3=0), None, None])

    def test_column12_unsigned_word_required(self):
        for value in (-1, 1 << 32, True, '0x1390', None):
            with self.assertRaises(ValueError):
                column12_word(value)

    def test_direct_branch_signed_offsets_and_call_class(self):
        # pc0 B +8, pc4 BL -4, pc8 RET, pc12 BR X0.
        data = struct.pack('<4I', 0x14000002, 0x97ffffff, 0xd65f03c0, 0xd61f0000)
        self.assertEqual(branch_candidates(data,8,0,16),
                         [dict(pc='0x0',opcode='14000002',kind='b')])
        self.assertEqual(branch_candidates(data,0,0,16),
                         [dict(pc='0x4',opcode='97ffffff',kind='bl')])
        self.assertEqual(branch_candidates(data,12,0,16), [])

    def test_branch_search_refuses_partial_or_unaligned_region(self):
        for first,last in ((-4,4),(1,4),(0,5),(8,4),(0,20)):
            with self.assertRaises(ValueError):
                branch_candidates(bytes(16),0,first,last)

    def test_occurrence_search_keeps_unaligned_and_overlap_matches(self):
        self.assertEqual(occurrences(b'!aaaa',b'aa'), [1,2,3])
        self.assertEqual(occurrences(b'!aaaa',b'zz'), [])
        with self.assertRaises(ValueError):
            occurrences(b'anything',b'')

    def test_directory_starts_eight_bytes_before_name(self):
        raw = struct.pack('<Q16sQQ', 0, b'NEWTIME', 7, 0xffff000000067630)
        record = directory_entries(raw,0,1)[0]
        self.assertEqual(record['record_file'],'0x0')
        self.assertEqual(record['name_file'],'0x8')
        self.assertEqual(record['name'],'NEWTIME')
        self.assertEqual(record['pointer_raw'],'0xffff000000067630')
        self.assertTrue(record['equals_name_length'])
        # A different numeric field remains raw; it is not silently a type or length.
        changed = bytearray(raw); struct.pack_into('<Q',changed,24,99)
        self.assertFalse(directory_entries(changed,0,1)[0]['equals_name_length'])

    def test_directory_bounds_and_name_termination(self):
        for first,count in ((-1,1),(0,1),(0,-1),(0,65),(0,True)):
            with self.assertRaises(ValueError):
                directory_entries(bytes(39),first,count)
        with self.assertRaises(ValueError):
            directory_entries(bytes(8)+b'x'*16+bytes(16),0,1)
        self.assertEqual(directory_entries(b'',0,0), [])


if __name__ == '__main__':
    unittest.main()
