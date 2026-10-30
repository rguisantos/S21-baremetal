#!/usr/bin/env python3
"""Test offline wire decoding without keys, capture claims or device access."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_rpmb_frame import decode_frame, inspect_file, wire_interval


def wire_fixture():
    frame = bytearray(512)
    frame[196:228] = bytes(range(32))
    frame[228:484] = bytes(range(256))
    frame[484:500] = bytes(range(0xa0, 0xb0))
    struct.pack_into('>IHHHH', frame, 500, 0x12345678, 0x2345, 0x3456, 0x4567, 0x5678)
    return bytes(frame)


class FrameTests(unittest.TestCase):
    def test_wire_scalars_have_network_endianness_and_distinct_fields(self):
        result = decode_frame(wire_fixture())
        self.assertEqual(result['scalars'], dict(request=0x5678, result=0x4567,
            count=0x3456, address=0x2345, write_counter=0x12345678))

    def test_zero_result_and_response_code_do_not_assert_authentication(self):
        frame = bytearray(512); struct.pack_into('>H', frame, 510, 0x400)
        result = decode_frame(bytes(frame))
        self.assertEqual(result['scalars']['result'], 0)
        self.assertEqual(result['scalars']['request'], 0x400)
        for key in ('authentication_verified', 'capture_provenance_verified',
                    'device_io_established', 'counter_persistence_established'):
            self.assertIs(result[key], False)

    def test_arrays_hash_wire_order_not_reversed_local_order(self):
        frame = wire_fixture(); result = decode_frame(frame)
        for name, start, size in (('Key_MAC', 196, 32), ('data', 228, 256), ('nonce', 484, 16)):
            row = result['arrays'][name]
            self.assertEqual(row['wire_sha256'], hashlib.sha256(frame[start:start+size]).hexdigest())
            self.assertNotEqual(row['wire_sha256'], hashlib.sha256(frame[start:start+size][::-1]).hexdigest())

    def test_mac_input_excludes_mac_and_stuff_and_includes_scalar_tail(self):
        original = wire_fixture()
        for index in (0, 195, 196, 227, 228, 483, 484, 511):
            frame = bytearray(original); frame[index] ^= 1
            changed = decode_frame(bytes(frame))['authenticated_region']['sha256']
            same = changed == decode_frame(original)['authenticated_region']['sha256']
            self.assertEqual(same, index < 228)

    def test_explicit_materialized_local_form_decodes_same_wire_fields(self):
        wire = wire_fixture(); a = decode_frame(wire)
        b = decode_frame(wire[::-1], input_order='local-materialized')
        for key in ('wire_sha256', 'scalars', 'arrays', 'authenticated_region'):
            self.assertEqual(a[key], b[key])
        self.assertNotEqual(a['input_sha256'], b['input_sha256'])
        self.assertFalse(b['capture_provenance_verified'])

    def test_wrong_order_is_not_auto_detected_or_repaired(self):
        wire = wire_fixture()
        self.assertNotEqual(decode_frame(wire)['scalars'], decode_frame(wire[::-1])['scalars'])

    def test_short_long_and_non_byte_input_are_refused(self):
        for frame in (bytes(511), bytes(513), b'', bytearray(512), None, '0'*512):
            with self.subTest(kind=type(frame)), self.assertRaisesRegex(ValueError, '512'):
                decode_frame(frame)

    def test_unknown_order_is_refused(self):
        for order in ('auto', 'local', '', None):
            with self.subTest(order=order), self.assertRaisesRegex(ValueError, 'order'):
                decode_frame(bytes(512), input_order=order)

    def test_field_reversal_maps_both_edges_and_exact_full_frame(self):
        for offset, size, start in ((0, 2, 510), (2, 2, 508), (8, 4, 500),
                                   (284, 32, 196), (316, 196, 0), (0, 512, 0)):
            self.assertEqual(wire_interval(offset, size), (start, size))

    def test_invalid_field_bounds_and_types_are_refused(self):
        for offset, size in ((-1, 1), (0, 0), (512, 1), (511, 2), (0, 513),
                             (True, 1), (0, 1.0)):
            with self.subTest(offset=offset, size=size), self.assertRaisesRegex(ValueError, 'outside'):
                wire_interval(offset, size)

    def test_regular_file_requires_exact_frame_without_trailing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'frame.bin'
            path.write_bytes(wire_fixture())
            self.assertEqual(inspect_file(path), decode_frame(wire_fixture()))
            path.write_bytes(wire_fixture()+b'\0')
            with self.assertRaisesRegex(ValueError, '512'):
                inspect_file(path)

    def test_directory_and_fifo_are_refused_before_open(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory)/'fifo'; os.mkfifo(fifo)
            for path in (Path(directory), fifo):
                with self.subTest(path=path.name), patch.object(Path, 'open') as opened:
                    with self.assertRaisesRegex(ValueError, 'regular file'):
                        inspect_file(path)
                    opened.assert_not_called()

    def test_cli_emits_metadata_and_no_array_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'frame.bin'; path.write_bytes(wire_fixture())
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('inspect_rpmb_frame.py')), str(path)],
                capture_output=True, text=True, check=True)
            output = json.loads(result.stdout)
            self.assertEqual(output['scalars']['write_counter'], 0x12345678)
            self.assertNotIn('hex', output['arrays']['Key_MAC'])

    def test_cli_failure_has_no_partial_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'short.bin'; path.write_bytes(bytes(511))
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('inspect_rpmb_frame.py')), str(path)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('512', result.stderr)


if __name__ == '__main__':
    unittest.main()
