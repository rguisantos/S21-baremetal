#!/usr/bin/env python3
"""Independent wire fixtures and mutations for the offline entry-record reader."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_entry_record import inspect_record

ROOT = Path(__file__).resolve().parent.parent


def fixture(el=4, base=0x40080000):
    image = bytearray(384)
    struct.pack_into('<3Q', image, 8, 0x80000, len(image), 8)
    image[56:60] = b'ARM\x64'
    image[64:256] = b'\x55'*192
    record = bytearray(b'S21ENTRY'+struct.pack('<II', 1, 128)+bytes(112))
    struct.pack_into('<14Q', record, 16, 0x1122334455667788, 2, 3, 4,
                     el, 0x3c0, 0x1000, 0x80000100, 1, 0x12345678,
                     base, base+256, 0, 0)
    return bytes(record), bytes(image)


class EntryRecordTests(unittest.TestCase):
    def setUp(self):
        self.record, self.image = fixture()

    def change(self, offset, fmt, value, **kwargs):
        record = bytearray(self.record)
        struct.pack_into('<'+fmt, record, offset, value)
        with self.assertRaises(ValueError):
            inspect_record(record, self.image, 0x40080000, **kwargs)

    def test_el1_and_el2_capture_layout(self):
        for raw in (4, 8):
            record, image = fixture(el=raw)
            result = inspect_record(record, image, 0x40080000)
            self.assertEqual(result['recorded_el'], raw >> 2)
            self.assertEqual(result['record_offset'], 256)
            self.assertEqual(result['arguments'][0], '0x1122334455667788')
            self.assertEqual(result['freshness'], 'not_verified')
            self.assertEqual(result['binding'], 'record_fields_only')
            self.assertEqual(result['x0_is_valid_fdt'], 'not_established')

    def test_full_image_capture(self):
        snapshot = self.image[:256]+self.record
        result = inspect_record(self.record, self.image, 0x40080000, snapshot)
        self.assertEqual(result['binding'], 'full_image_bytes')
        self.assertEqual(len(result['snapshot_sha256']), 64)

    def test_wrong_record_length(self):
        for data in (b'', self.record[:-1], self.record+b'\0'):
            with self.assertRaises(ValueError): inspect_record(data, self.image, 0x40080000)

    def test_absent_or_partial_marker(self):
        for data in (bytes(128), b'\xa5'*128, b'S21ENTR\0'+self.record[8:]):
            with self.assertRaises(ValueError): inspect_record(data, self.image, 0x40080000)

    def test_wrong_version(self): self.change(8, 'I', 2)
    def test_wrong_size(self): self.change(12, 'I', 120)
    def test_unsupported_el(self): self.change(48, 'Q', 12)
    def test_enabled_translation_or_cache(self):
        for bits in (1, 4, 5): self.change(64, 'Q', bits)
    def test_reserved_fields(self):
        for offset in (112, 120): self.change(offset, 'Q', 1)
    def test_invalid_daif(self): self.change(56, 'Q', 1)
    def test_invalid_spsel(self): self.change(80, 'Q', 2)
    def test_wrong_image_address(self): self.change(96, 'Q', 0x40088000)
    def test_wrong_record_address(self): self.change(104, 'Q', 0x40080101)

    def test_wrong_expected_address(self):
        for address in (-1, 1, (1 << 64)-64, 0x40088000):
            with self.assertRaises(ValueError): inspect_record(self.record, self.image, address)

    def test_invalid_reference_image(self):
        for offset, fmt, value in ((8,'Q',0), (16,'Q',1), (24,'Q',0),
                                   (32,'Q',1), (56,'I',0), (60,'I',1), (256,'Q',1)):
            image = bytearray(self.image);struct.pack_into('<'+fmt, image, offset, value)
            with self.assertRaises(ValueError): inspect_record(self.record, image, 0x40080000)
        for image in (b'', self.image[:-1], self.image+bytes(64)):
            with self.assertRaises(ValueError): inspect_record(self.record, image, 0x40080000)

    def test_different_snapshot(self):
        snapshot = bytearray(self.image[:256]+self.record)
        snapshot[64] ^= 1
        for data in (snapshot, snapshot[:-1], self.image):
            with self.assertRaises(ValueError): inspect_record(self.record, self.image, 0x40080000, data)

    def test_cli_success_and_oversized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory);record=d/'record';image=d/'Image';snapshot=d/'snapshot'
            record.write_bytes(self.record);image.write_bytes(self.image)
            snapshot.write_bytes(self.image[:256]+self.record)
            command=[sys.executable,str(ROOT/'scripts/inspect_entry_record.py'),str(record),
                     '--image',str(image),'--load-address','0x40080000','--snapshot',str(snapshot)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['binding'],'full_image_bytes')
            record.write_bytes(self.record+b'private trailer must not be printed')
            result=subprocess.run(command,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,2)
            self.assertNotIn('private trailer',result.stdout+result.stderr)
            self.assertEqual(image.read_bytes(),self.image)


if __name__ == '__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EntryRecordTests))
    if result.wasSuccessful(): print(f'ENTRY RECORD HOST PASS: {result.testsRun} tests')
    sys.exit(not result.wasSuccessful())
