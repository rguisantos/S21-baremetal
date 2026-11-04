#!/usr/bin/env python3
"""Observation/parser controls without timing claims or private payloads."""
from pathlib import Path
import struct
import tempfile
import unittest

from capture_a0_copy_probe import decode_events,observe


class CopyProbeTests(unittest.TestCase):
    def observed(self,data,expected):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'payload.bin';path.write_bytes(data)
            return observe(path,expected)

    def test_full_observation_binds_same_open_object_and_bytes(self):
        row,data=self.observed(b'payload',b'payload')
        self.assertTrue(row['matches']);self.assertTrue(row['identity_stable_during_read'])
        self.assertEqual(data,b'payload');self.assertFalse(row['is_expected_prefix'])

    def test_truncated_prefix_is_distinguished_from_wrong_contents(self):
        prefix,_=self.observed(b'pay',b'payload');wrong,_=self.observed(b'bad',b'payload')
        self.assertTrue(prefix['is_expected_prefix']);self.assertFalse(wrong['is_expected_prefix'])
        self.assertFalse(prefix['matches']);self.assertFalse(wrong['matches'])

    def test_oversized_input_read_is_bounded_and_refused_as_match(self):
        row,data=self.observed(b'payload-extra',b'payload')
        self.assertEqual(len(data),8);self.assertFalse(row['matches']);self.assertFalse(row['is_expected_prefix'])

    def test_events_retain_watch_cookie_and_masks_without_invented_pid(self):
        raw=struct.pack('iIII',2,0x80,23,8)+b'name\0\0\0\0'
        row=decode_events(raw)[0]
        self.assertEqual(row,dict(watch=2,mask=0x80,cookie=23,name='name'))
        self.assertNotIn('pid',row)

    def test_multiple_coalesced_records_are_decoded(self):
        raw=struct.pack('iIII',1,2,0,0)+struct.pack('iIII',-1,0x4000,0,0)
        self.assertEqual(len(decode_events(raw)),2);self.assertEqual(decode_events(raw)[1]['mask'],0x4000)

    def test_short_headers_and_names_are_refused(self):
        for raw in (b'x',struct.pack('iIII',1,2,0,8)+b'x'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):decode_events(raw)


if __name__=='__main__':unittest.main()
