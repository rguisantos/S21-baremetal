"""Bounded source parsing and dialect separation; no hardware responses."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from check_epbl_hash_sources import definitions, hash_modes, macro_value, read_reference


def mode_source(body):
    return 'static bool sss_hash_mode(uint32_t mode, const EVP_MD **md, bool *hmac) { switch (mode) {' + body + '} }'


class HashSources(unittest.TestCase):
    def test_defines_are_names_not_function_macros_or_code(self):
        self.assertEqual(definitions('#define BASE 0x1000\n#define FN(x) x\nint x;'), {'BASE': '0x1000'})

    def test_conflicting_definitions_are_refused(self):
        with self.assertRaises(ValueError):
            definitions('#define BASE 1\n#define BASE 2')

    def test_macro_arithmetic_preserves_offsets_and_64bit_base(self):
        d = {'BASE': '0x100000000ULL', 'OFFSET': '(BASE + 0x1030)', 'MASK': 'UINT32_C(0x40)'}
        self.assertEqual(macro_value(d, 'OFFSET'), 0x100001030)
        self.assertEqual(macro_value(d, 'MASK'), 0x40)

    def test_unknown_and_cyclic_macro_dependencies_are_refused(self):
        for values in ({'A': 'B'}, {'A': 'B', 'B': 'A'}):
            with self.assertRaises(ValueError):
                macro_value(values, 'A')

    def test_large_shift_negative_and_overflow_are_refused(self):
        for expression in ('1 << 64', '0 - 1', '0xffffffffffffffff + 1', 'UINT32_C(0x100000000)'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                macro_value({'A': expression}, 'A')

    def test_calls_attributes_and_boolean_constants_are_not_evaluated(self):
        for expression in ('__import__("os")', 'object.attribute', 'True', '(lambda: 1)()'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                macro_value({'A': expression}, 'A')

    def test_macro_dependency_depth_is_bounded(self):
        values = {f'A{i}': f'A{i+1}' for i in range(33)} | {'A33': '1'}
        with self.assertRaises(ValueError):
            macro_value(values, 'A0')

    def test_mode_switch_fallthrough_keeps_both_labels(self):
        source = mode_source('case 0x14: case 0x34: /* restored IV */ *md = EVP_sha256(); *hmac = false; return true; default: return false;')
        modes = hash_modes(source)
        self.assertEqual(modes[0x14], modes[0x34])
        self.assertEqual(modes[0x14], {'algorithm': 'sha256', 'hmac': False})

    def test_unsupported_0x19_is_not_inferred_from_sha512_neighbor(self):
        modes = hash_modes(mode_source('case 0x1a: *md = EVP_sha512(); *hmac = false; return true; case 0x1b: *md = EVP_sha512(); *hmac = true; return true; default: return false;'))
        self.assertNotIn(0x19, modes)
        self.assertTrue(modes[0x1b]['hmac'])

    def test_switch_rejects_unknown_statement_or_duplicate_case(self):
        block = 'case 0x14: *md = EVP_sha256(); *hmac = false; return true; '
        for body in (block + 'unexpected(); default: return false;', block + block + 'default: return false;'):
            with self.assertRaises(ValueError):
                hash_modes(mode_source(body))

    def test_switch_requires_explicit_default_rejection(self):
        with self.assertRaises(ValueError):
            hash_modes(mode_source('case 0x14: *md = EVP_sha256(); *hmac = false; return true; default: return true;'))

    def test_reference_requires_both_hashes_and_bounded_size(self):
        raw = b'#define BASE 1\n'
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'header.h'; path.write_bytes(raw)
            identity = ('example/source', 'pinned', 'header.h', blob, digest)
            content, record = read_reference(path, identity)
            self.assertEqual(content, raw.decode())
            self.assertFalse(record['reference_is_HZC2_hardware_specification'])
            with self.assertRaises(ValueError):
                read_reference(path, (*identity[:3], '0' * 40, digest))
            path.write_bytes(b'x' * 65537)
            with self.assertRaises(ValueError):
                read_reference(path, identity)


if __name__ == '__main__':
    unittest.main()
