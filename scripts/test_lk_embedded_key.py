#!/usr/bin/env python3
"""AVB serialization arithmetic and bounded consumer decoding, without firmware."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_embedded_key import adrp, input_locations, inspect, inspect_avb_rsa_key


def synthetic_key(bits=2048):
    # n = 2^(bits-1)+3: n[0]=3, -1/3 mod 2^32 = 0x55555555,
    # and 2^(2*bits) mod n = 36. No claim that this n is an RSA semiprime.
    width = bits//8
    n = b'\x80' + bytes(width-2) + b'\x03'
    return struct.pack('>2I', bits, 0x55555555) + n + (36).to_bytes(width, 'big')


class KeyFormatTests(unittest.TestCase):
    def test_supported_widths_and_independent_arithmetic_fixture(self):
        for bits in (2048, 4096, 8192):
            with self.subTest(bits=bits):
                result = inspect_avb_rsa_key(synthetic_key(bits))
                self.assertEqual(result['key_num_bits'], bits)
                self.assertEqual(result['serialized_bytes'], 8+bits//4)
                self.assertEqual(result['n_times_n0inv_mod_2_to_32'], '0xffffffff')
                self.assertTrue(result['rr_matches_r_squared_mod_n'])
                self.assertEqual(result['implicit_exponent_from_format'], 65537)
                for flag in ('exponent_stored_in_blob', 'modulus_factorization_verified',
                             'signature_verified', 'key_trust_established', 'runtime_bytes_observed'):
                    self.assertFalse(result[flag])

    def test_truncated_header(self):
        for size in (0, 1, 7):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'header'):
                inspect_avb_rsa_key(bytes(size))

    def test_unsupported_size_and_little_endian_header(self):
        for header in (struct.pack('>2I', 1024, 0), struct.pack('<2I', 2048, 0x55555555)):
            with self.subTest(header=header), self.assertRaisesRegex(ValueError, 'bit count'):
                inspect_avb_rsa_key(header+bytes(512))

    def test_truncated_or_extra_payload(self):
        good = synthetic_key()
        for blob in (good[:-1], good+b'\x00'):
            with self.subTest(size=len(blob)), self.assertRaisesRegex(ValueError, 'extent'):
                inspect_avb_rsa_key(blob)

    def test_modulus_width(self):
        blob = bytearray(synthetic_key()); blob[8] = 0
        with self.assertRaisesRegex(ValueError, 'bit length'):
            inspect_avb_rsa_key(blob)

    def test_even_modulus(self):
        blob = bytearray(synthetic_key()); blob[8+256-1] = 2
        with self.assertRaisesRegex(ValueError, 'odd'):
            inspect_avb_rsa_key(blob)

    def test_wrong_n0inv(self):
        blob = bytearray(synthetic_key()); blob[7] ^= 1
        with self.assertRaisesRegex(ValueError, 'n0inv'):
            inspect_avb_rsa_key(blob)

    def test_wrong_rr(self):
        blob = bytearray(synthetic_key()); blob[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'rr'):
            inspect_avb_rsa_key(blob)

    def test_swapped_modulus_and_rr(self):
        good = synthetic_key()
        with self.assertRaisesRegex(ValueError, 'bit length'):
            inspect_avb_rsa_key(good[:8]+good[264:]+good[8:264])


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.words = {0x151a74: 0x90000e61, 0x151a80: 0x90000e60,
                      0x151a8c: 0xb9473821, 0x151a90: 0x911d0000}

    def test_addresses_from_machine_words(self):
        self.assertEqual(input_locations(self.words), (0x31d740, 0x31d738))

    def test_signed_adrp_page_displacement(self):
        self.assertEqual(adrp(0xf0ffffe0, 0x1000), (0, 0))

    def test_non_adrp_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ADRP'):
            adrp(0xd503201f, 0)

    def test_non_add_and_wrong_registers_rejected(self):
        for value in (0xd1000000, 0x911d0001, 0x911d0020):
            changed = dict(self.words); changed[0x151a90] = value
            with self.subTest(word=hex(value)), self.assertRaisesRegex(ValueError, 'ADD'):
                input_locations(changed)

    def test_shifted_add_supported_explicitly(self):
        changed = dict(self.words); changed[0x151a90] = 0x91400400
        self.assertEqual(input_locations(changed), (0x31e000, 0x31d738))

    def test_non_w_load_and_wrong_base_rejected(self):
        for value in (0xf9400021, 0xb9473801, 0xb9473820):
            changed = dict(self.words); changed[0x151a8c] = value
            with self.subTest(word=hex(value)), self.assertRaisesRegex(ValueError, 'LDR W1'):
                input_locations(changed)

    def test_wrong_input_rejected_before_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'invalid.bin'
            for content in (b'not firmware', bytes(IMAGES['sboot'][0])):
                path.write_bytes(content)
                with self.subTest(size=len(content)), patch('inspect_lk_embedded_key.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError, 'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_refuses_unidentified_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'invalid.bin'; path.write_bytes(b'bad')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('inspect_lk_embedded_key.py')), str(path)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
