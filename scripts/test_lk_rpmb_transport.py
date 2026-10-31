#!/usr/bin/env python3
"""Test static callback slots and raw security-CDB operand bindings."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_rpmb_transport import callback_bindings, inspect, security_cdb, store_unsigned_b


def callbacks():
    return {
        0x18f420: 0xa9091a60,
        0x10c4dc: 0xa90c0381,
        0x18f3ec: 0xf0ffffe0,
        0x18f3fc: 0x9122a000,
        0x18f404: 0xf0ffffe6,
        0x18f414: 0x911940c6,
        0x10c4cc: 0x90000001,
        0x10c4d4: 0x91006021,
        0x10c4d0: 0x90000000,
        0x10c4d8: 0x91034000,
        0x109f78: 0xf9404c04,
        0x109f88: 0xd63f0080,
        0x109f9c: 0xf9404ac4,
        0x109fb0: 0xd63f0080,
        0x18e968: 0xf9406365,
        0x18e990: 0xd63f00a0,
        0x18e710: 0xf9406745,
        0x18e738: 0xd63f00a0,
        0x18eb18: 0xb0000c96,
        0x18eb24: 0x913de2d4,
        0x18f4bc: 0x90000c94,
        0x18f4c4: 0x913de296,
    }


def cdb_words(*, output=False):
    words = {
        0x10c064: 0x12800ba4,
        0x10c068: 0x12800262,
        0x10c070: 0x52800020,
        0x10c034: 0xf0003cd5,
        0x10c03c: 0x910e02b3,
        0x10c06c: 0x390e02a4,
        0x10c07c: 0x39000662,
        0x10c080: 0x39000e60,
        0x10c088: 0x39000a7f,
        0x10c090: 0x3900267f,
        0x10c098: 0x39001a64,
        0x10c09c: 0x39001e62,
        0x10c0a0: 0x39002263,
    }
    if output:
        words[0x10c064] = 0x12800944
        words = {pc+0xb8: word for pc, word in words.items()}
    return words


class CallbackTests(unittest.TestCase):
    def test_installed_methods_match_consumer_slots(self):
        result = callback_bindings(callbacks())
        self.assertEqual(result['device_methods'], {'144':'0x18e8a8', '152':'0x18e650'})
        self.assertEqual(result['underlying_methods'], {'192':'0x10c018', '200':'0x10c0d0'})
        self.assertEqual(result['registry_relative_address'], '0x31ff78')
        self.assertFalse(result['live_installation_and_preservation_established'])

    def test_pair_sources_base_and_slot_mutations_are_refused(self):
        for pc in (0x18f420, 0x10c4dc):
            for bit in (1, 1<<10, 1<<5, 1<<15):
                words=callbacks(); words[pc]^=bit
                with self.subTest(pc=pc, bit=bit), self.assertRaisesRegex(ValueError, 'installer'):
                    callback_bindings(words)

    def test_consumer_register_base_and_slot_mutations_are_refused(self):
        for pc in (0x109f78, 0x109f9c, 0x18e968, 0x18e710):
            for bit in (1, 1<<5, 1<<10):
                words=callbacks(); words[pc]^=bit
                with self.subTest(pc=pc, bit=bit), self.assertRaisesRegex(ValueError, 'consumer'):
                    callback_bindings(words)

    def test_wrong_indirect_branch_register_is_refused(self):
        for pc in (0x109f88, 0x109fb0, 0x18e990, 0x18e738):
            words=callbacks(); words[pc]^=1<<5
            with self.subTest(pc=pc), self.assertRaisesRegex(ValueError, 'consumer'):
                callback_bindings(words)

    def test_wrong_add_source_is_refused(self):
        for pc in (0x18f3fc, 0x18f414, 0x10c4d4, 0x10c4d8):
            words=callbacks(); words[pc]^=1<<5
            with self.subTest(pc=pc), self.assertRaisesRegex(ValueError, 'source'):
                callback_bindings(words)

    def test_registration_and_lookup_root_mismatch_is_refused(self):
        words=callbacks(); words[0x18eb24]^=1<<10
        with self.assertRaisesRegex(ValueError, 'roots differ'):
            callback_bindings(words)

    def test_wrong_pair_or_load_width_is_refused(self):
        for pc, word in ((0x18f420,0x29091a60),(0x18e968,0xb9406365)):
            words=callbacks();words[pc]=word
            with self.subTest(pc=pc), self.assertRaises(ValueError):
                callback_bindings(words)


class CdbTests(unittest.TestCase):
    def test_movn_values_are_truncated_only_at_byte_stores(self):
        result=security_cdb(cdb_words())
        self.assertEqual((result['opcode'],result['protocol'],result['protocol_specific']), ('0xa2','0xec',1))
        self.assertEqual(result['workspace_relative_address'], '0x8a7380')
        self.assertEqual(result['callback_offset_in_parent'],368)
        self.assertFalse(result['original_block_index_used_in_cdb'])

    def test_security_out_has_same_workspace_and_different_opcode(self):
        result=security_cdb(cdb_words(output=True),output=True)
        self.assertEqual(result['opcode'],'0xb5')
        self.assertEqual(result['workspace_relative_address'],'0x8a7380')
        self.assertEqual(result['protocol'],'0xec')

    def test_constant_register_and_width_mutations_are_refused(self):
        for bit in (1,1<<31):
            words=cdb_words();words[0x10c064]^=bit
            with self.subTest(bit=bit),self.assertRaises(ValueError):
                security_cdb(words)

    def test_byte_store_source_base_and_offset_mutations_are_refused(self):
        for pc in (0x10c06c,0x10c07c,0x10c080,0x10c088,0x10c090,0x10c098,0x10c09c,0x10c0a0):
            for bit in (1,1<<5,1<<10):
                words=cdb_words();words[pc]^=bit
                with self.subTest(pc=pc,bit=bit),self.assertRaisesRegex(ValueError,'binding'):
                    security_cdb(words)

    def test_opcode_address_must_be_the_workspace_start(self):
        words=cdb_words();words[0x10c03c]^=1<<10
        with self.assertRaisesRegex(ValueError,'binding'):
            security_cdb(words)

    def test_byte_store_immediates_are_not_scaled(self):
        self.assertEqual(store_unsigned_b(0x39000662),(2,19,1))
        self.assertEqual(store_unsigned_b(0x393ffc20),(0,1,4095))

    def test_other_widths_loads_indexed_forms_and_non_words_refused(self):
        for word in (0x39400662,0x79000662,0x38001422,-1,0x139000662,True):
            with self.subTest(word=word),self.assertRaisesRegex(ValueError,'STRB'):
                store_unsigned_b(word)


class RefusalTests(unittest.TestCase):
    def test_wrong_size_or_hash_refused_before_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.bin'
            for content in (b'bad',bytes(IMAGES['sboot'][0])):
                path.write_bytes(content)
                with self.subTest(size=len(content)),patch('inspect_lk_rpmb_transport.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError,'unsupported image'):
                        inspect(path)
                    gnu.assert_not_called()

    def test_cli_failure_does_not_emit_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.bin';path.write_bytes(b'bad')
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_lk_rpmb_transport.py')),str(path)],capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,2)
            self.assertEqual(result.stdout,'')
            self.assertIn('unsupported image',result.stderr)


if __name__=='__main__':
    unittest.main()
