#!/usr/bin/env python3
"""Synthetic envelope/candidate controls; never evidence of HZC2 plaintext."""
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_tzsw_bien import (aes_trial, candidate_result, envelope,
    public_constants, reference_probe, soc_profiles)


def pair():
    original = bytearray(0x200)
    original[0x10:0x14] = b'BiEn'
    original[0x18:0x20] = b'teegris\0'
    struct.pack_into('<II', original, 0x28, 0x100, 0x140)
    original[0x70:0x90] = hashlib.sha256(b'A' * 64).digest()
    original[0x100:0x140] = b'B' * 64
    candidate = original.copy()
    candidate[0x100:0x140] = b'A' * 64
    return bytes(original), bytes(candidate)


KEY_SOURCE = "MASTER_KEY = bytes.fromhex('" + 'a0' * 32 + "')\nMASTER_IV = bytes.fromhex('" + 'b0' * 16 + "')\n"


class BienTests(unittest.TestCase):
    def test_envelope_uses_original_little_endian_bounds(self):
        original, _ = pair()
        self.assertEqual(envelope(original), (0x100, 0x140))

    def test_magic_tag_and_minimum_size_refused(self):
        original, _ = pair()
        for data in (original[:0x8f], original[:0x10] + b'Bad!' + original[0x14:],
                     original[:0x18] + b'unknown\0' + original[0x20:]):
            with self.assertRaises(ValueError):
                envelope(data)

    def test_extent_truncation_order_and_block_width_refused(self):
        original, _ = pair()
        for start, end in ((0, 64), (0x100, 0x100), (0x140, 0x100), (0x100, 0x210), (0x100, 0x141)):
            data = bytearray(original)
            struct.pack_into('<II', data, 0x28, start, end)
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                envelope(data)

    def test_unknown_words_are_not_promoted_to_format_requirements(self):
        original, _ = pair()
        data = bytearray(original)
        struct.pack_into('<II', data, 0x30, 7, 9)
        self.assertEqual(envelope(data), (0x100, 0x140))

    def test_synthetic_candidate_acceptance_is_digest_correspondence_only(self):
        original, candidate = pair()
        result = candidate_result(original, candidate)
        self.assertTrue(result['accepted'])
        self.assertTrue(result['outside_region_identical'])
        self.assertFalse(result['reference_marker_present'])
        self.assertIn('signature/runtime not verified', result['acceptance_scope'])

    def test_payload_corruption_refuses_acceptance(self):
        original, candidate = pair()
        bad = bytearray(candidate)
        bad[0x110] ^= 1
        result = candidate_result(original, bad)
        self.assertFalse(result['accepted'])
        self.assertFalse(result['matches_original_stored_SHA256'])

    def test_changes_outside_region_refused_even_with_matching_digest(self):
        original, candidate = pair()
        for offset in (0x20, 0x90, 0x140, 0x1ff):
            bad = bytearray(candidate)
            bad[offset] ^= 1
            result = candidate_result(original, bad)
            self.assertFalse(result['accepted'])
            self.assertTrue(result['matches_original_stored_SHA256'])

    def test_replacement_candidate_digest_is_not_trusted(self):
        original, candidate = pair()
        bad = bytearray(candidate)
        bad[0x100:0x140] = b'C' * 64
        bad[0x70:0x90] = hashlib.sha256(b'C' * 64).digest()
        result = candidate_result(original, bad)
        self.assertFalse(result['accepted'])
        self.assertFalse(result['matches_original_stored_SHA256'])

    def test_candidate_length_must_equal_original(self):
        original, candidate = pair()
        for bad in (b'', candidate[:-1], candidate + b'\0'):
            self.assertEqual(candidate_result(original, bad), dict(accepted=False, reason='candidate_size_differs'))

    def test_public_literals_are_read_without_running_source(self):
        source = 'raise RuntimeError("must not execute")\n' + KEY_SOURCE
        self.assertEqual(public_constants(source), (b'\xa0' * 32, b'\xb0' * 16))

    def test_public_constants_reject_calls_aliases_widths_and_duplicates(self):
        for source in ('', KEY_SOURCE + KEY_SOURCE, KEY_SOURCE.replace('bytes.fromhex', 'other.fromhex'),
                       KEY_SOURCE.replace('a0', 'z0'), KEY_SOURCE.replace('a0' * 32, 'a0' * 16),
                       KEY_SOURCE.replace("bytes.fromhex('", "bytes.fromhex(text='"),
                       "MASTER_KEY = make_key()\n" + KEY_SOURCE.splitlines()[1]):
            with self.subTest(source=source[:50]), self.assertRaises(ValueError):
                public_constants(source)

    def test_SoC_profiles_require_one_literal_dictionary(self):
        self.assertEqual(soc_profiles("EXYNOS_DATA = {'Exynos9830\\0': {}, 'Exynos9820\\0': {}}"),
                         ['Exynos9820\0', 'Exynos9830\0'])
        for source in ('', 'EXYNOS_DATA = make_profiles()', 'EXYNOS_DATA = []', 'EXYNOS_DATA = {1: {}}',
                       'EXYNOS_DATA = {}\nEXYNOS_DATA = {}'):
            with self.assertRaises(ValueError):
                soc_profiles(source)

    def test_AES_width_guards_run_before_backend(self):
        def forbidden(*args):
            self.fail('invalid input reached crypto backend')
        for block, key, iv in ((b'', b'K' * 32, b'I' * 16), (b'A' * 15, b'K' * 32, b'I' * 16),
                                (b'A' * 16, b'K' * 16, b'I' * 16), (b'A' * 16, b'K' * 32, b'I' * 15)):
            with self.assertRaises(ValueError):
                aes_trial(block, key, iv, forbidden)

    def test_changed_reference_is_rejected_before_crypto(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'tzsw_crypt_tool.py').write_text(KEY_SOURCE)
            with self.assertRaises(ValueError):
                reference_probe(pair()[0], tmp)

    def test_wrong_firmware_CLI_emits_no_partial_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'wrong.img'
            path.write_bytes(b'\0' * 4)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('inspect_tzsw_bien.py')), str(path),
                                     '--probe-reference-dir', str(Path(tmp) / 'missing')],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('MASTER_KEY', result.stderr)


if __name__ == '__main__':
    unittest.main()
