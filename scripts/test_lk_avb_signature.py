#!/usr/bin/env python3
"""Exercise AVB table decoding and refusals using synthetic host-only inputs."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_avb_signature import adr, algorithm_table, inspect, relative_targets, table_locations, window


def fixture():
    """Build records independently from fixed DER bytes, with a synthetic VA base."""
    data = bytearray(4096)
    cursor = 256
    for index, (digest_size, width) in enumerate(
            ((32, 256), (32, 512), (32, 1024), (64, 256), (64, 512), (64, 1024)), 1):
        # DigestInfo = SEQUENCE { SEQUENCE { hash OID, NULL }, OCTET STRING }.
        oid = b'\x60\x86\x48\x01\x65\x03\x04\x02'+bytes([1 if digest_size == 32 else 3])
        info = b'\x30'+bytes([digest_size+17])+b'\x30\x0d\x06\x09'+oid+b'\x05\x00\x04'+bytes([digest_size])
        padding_size = width-digest_size
        padding = b'\x00\x01'+b'\xff'*(padding_size-len(info)-3)+b'\x00'+info
        struct.pack_into('<QQQ', data, index*24, 0x80000000+cursor, padding_size, digest_size)
        data[cursor:cursor+padding_size] = padding
        cursor += padding_size
    return data


class AlgorithmTests(unittest.TestCase):
    def test_all_six_algorithm_records_and_prefixes(self):
        rows = algorithm_table(fixture(), 0, 0x80000000)
        self.assertEqual([r['rsa_bits'] for r in rows], [2048, 4096, 8192]*2)
        self.assertEqual([r['digest_bytes'] for r in rows], [32]*3+[64]*3)
        self.assertEqual([r['padding_bytes'] for r in rows], [224, 480, 992, 192, 448, 960])
        self.assertEqual([r['hash'] for r in rows], ['SHA256']*3+['SHA512']*3)

    def test_none_record_cannot_advertise_key_or_hash(self):
        for offset in (0, 8, 16):
            data = fixture(); data[offset] = 1
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'NONE'):
                algorithm_table(data, 0, 0x80000000)

    def test_incorrect_digest_and_padding_sizes_are_refused(self):
        for index in range(1, 7):
            for field in (8, 16):
                data = fixture(); data[index*24+field] ^= 1
                with self.subTest(index=index, field=field), self.assertRaisesRegex(ValueError, 'sizes'):
                    algorithm_table(data, 0, 0x80000000)

    def test_zero_prefix_fill_separator_and_oid_mutations_are_refused(self):
        for index in range(1, 7):
            data = fixture()
            pointer, size, _ = struct.unpack_from('<QQQ', data, index*24)
            offset = pointer-0x80000000
            for relative in (0, 1, 2, size-20, size-1):
                changed = bytearray(data); changed[offset+relative] ^= 1
                with self.subTest(index=index, relative=relative), self.assertRaisesRegex(ValueError, 'padding'):
                    algorithm_table(changed, 0, 0x80000000)

    def test_padding_pointer_before_and_after_file_is_refused(self):
        for pointer in (0, 0x7fffffff, 0x80001000, 0xffffffffffffffff):
            data = fixture(); struct.pack_into('<Q', data, 24, pointer)
            with self.subTest(pointer=pointer), self.assertRaisesRegex(ValueError, 'extent'):
                algorithm_table(data, 0, 0x80000000)

    def test_truncated_table_and_padding_are_refused(self):
        data = fixture()
        for length in (0, 167, 300, 3551):
            with self.subTest(length=length), self.assertRaisesRegex(ValueError, 'extent'):
                algorithm_table(data[:length], 0, 0x80000000)

    def test_wrong_endian_records_are_refused(self):
        data = fixture()
        for index in range(1, 7):
            fields = struct.unpack_from('<QQQ', data, index*24)
            struct.pack_into('>QQQ', data, index*24, *fields)
        with self.assertRaisesRegex(ValueError, 'sizes'):
            algorithm_table(data, 0, 0x80000000)

    def test_delta_must_be_nonnegative_integer(self):
        for delta in (-1, True, 1.5):
            with self.subTest(delta=delta), self.assertRaisesRegex(ValueError, 'delta'):
                algorithm_table(fixture(), 0, delta)


class AddressTests(unittest.TestCase):
    def test_consumer_instructions_resolve_table_and_dispatch_bases(self):
        words = {0x120ce4: 0xb0000f22, 0x120cec: 0x912f8042,
                 0x1267fc: 0xd0000841, 0x126800: 0x911d0021,
                 0x122cf8: 0xd0000860, 0x122cfc: 0x911c2000,
                 0x126a00: 0xd0000841, 0x126a04: 0x911d2021,
                 0x126808: 0x10000061, 0x122d04: 0x10000061}
        self.assertEqual(table_locations(words), dict(algorithms=0x305be0,
            hash_switch=0x230740, slot_switch=0x230708, result_names=0x230748,
            hash_base=0x126814, slot_base=0x122d10))
        for pc in (0x126808, 0x122d04):
            changed = dict(words); changed[pc] = 0x10000060
            with self.subTest(pc=hex(pc)), self.assertRaisesRegex(ValueError, 'register'):
                table_locations(changed)

    def test_signed_rel8_offsets_are_scaled_by_four(self):
        data = bytes([0x80, 0xff, 0, 1, 0x7f])+bytes(1531)
        self.assertEqual(relative_targets(data, 0, 5, 512, 0, len(data)), [0, 508, 512, 516, 1020])

    def test_jump_target_must_be_within_half_open_code_window(self):
        data = bytes([0xff, 1])+bytes(30)
        for table in (0, 1):
            with self.subTest(table=table), self.assertRaisesRegex(ValueError, 'target'):
                relative_targets(data, table, 1, 16, 16, 20)

    def test_jump_table_bounds_and_empty_count_are_refused(self):
        for offset, count in ((-1, 1), (32, 1), (31, 2), (0, 0), (0, True)):
            with self.subTest(offset=offset, count=count), self.assertRaisesRegex(ValueError, 'extent'):
                relative_targets(bytes(32), offset, count, 16, 0, 32)

    def test_jump_code_window_alignment_and_base_are_checked(self):
        for base, low, high in ((17, 0, 32), (16, 1, 32), (16, 0, 31),
                                (32, 0, 32), (16, 0, 36), (True, 0, 32)):
            with self.subTest(base=base, low=low, high=high), self.assertRaisesRegex(ValueError, 'bounds'):
                relative_targets(bytes(32), 0, 1, base, low, high)

    def test_adr_handles_both_signed_extremes(self):
        self.assertEqual(adr(0x10000061, 0x126808), (1, 0x126814))
        self.assertEqual(adr(0x10800002, 0x200000), (2, 0x100000))
        self.assertEqual(adr(0x707fffe3, 0x200000), (3, 0x2fffff))

    def test_adr_rejects_adrp_and_other_instructions(self):
        for word in (0x90000000, 0x91000000, 0xd503201f):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, 'ADR'):
                adr(word, 0)

    def test_file_window_rejects_negative_empty_and_noninteger_lengths(self):
        for offset, size in ((-1, 1), (0, -1), (0, 0), (True, 1), (0, 1.5), (4, 1)):
            with self.subTest(offset=offset, size=size), self.assertRaisesRegex(ValueError, 'extent'):
                window(bytes(4), offset, size)
        self.assertEqual(window(b'abcd', 2, 2), b'cd')


class ImageRefusalTests(unittest.TestCase):
    def test_unidentified_image_is_refused_before_disassembly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'
            for content in (b'not firmware', bytes(IMAGES['sboot'][0])):
                path.write_bytes(content)
                with self.subTest(size=len(content)), patch('inspect_lk_avb_signature.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError, 'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_failure_does_not_emit_a_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.bin'; path.write_bytes(b'bad')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('inspect_lk_avb_signature.py')), str(path)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
