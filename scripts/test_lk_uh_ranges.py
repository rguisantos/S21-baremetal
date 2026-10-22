"""Independent FDT fixtures for the memory-prefix walker callback model."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from check_lk_uh_ranges import MAX_FDT, model
from test_fdt import encode, node, text, u32, u64


def reg(base, size):
    return u64(base) + u32(size)


def tree(children, cells=(2, 1)):
    return encode(node('', {'#address-cells': u32(cells[0]),
                            '#size-cells': u32(cells[1])}, children))


class RangeWalkerTests(unittest.TestCase):
    def test_big_endian_addresses_and_structure_order(self):
        data = tree([node('memory@880000000', {'reg': reg(0x880000000, 0x20000000)}),
                     node('memory@80000000', {'reg': reg(0x80000000, 0x40000000)})])
        report = model(data)
        ranges = report['submitted_ranges']
        self.assertEqual([(r['base'], r['size']) for r in ranges],
                         [('0x880000000', '0x20000000'), ('0x80000000', '0x40000000')])
        self.assertEqual(ranges[0]['end_exclusive'], '0x8a0000000')
        self.assertFalse(report['allocation_simulated'])
        self.assertFalse(report['uh_acceptance_verified'])
        self.assertFalse(report['memory_map_verified'])
        self.assertFalse(report['is_final_fdt'])

    def test_name_prefix_instead_of_device_type_or_status(self):
        data = tree([node('ram@80000000', {'device_type': text('memory'),
                                          'reg': reg(0x80000000, 0x100000)}),
                     node('memory-extra', {'device_type': text('other'),
                                           'status': text('disabled'),
                                           'reg': reg(0x90000000, 0x200000)}),
                     node('memory-without-reg')])
        report = model(data)
        self.assertEqual([r['node'] for r in report['submitted_ranges']], ['/memory-extra'])
        self.assertEqual(report['skipped_nodes_without_reg'], ['/memory-without-reg'])

    def test_nested_bus_does_not_translate_reg(self):
        bus = node('bus', {'#address-cells': u32(2), '#size-cells': u32(1),
                           'ranges': u64(0) + u64(0x100000000) + u32(0x1000000)},
                   [node('memory@200000', {'reg': reg(0x200000, 0x100000)})])
        report = model(tree([bus]))
        self.assertEqual(report['submitted_ranges'][0]['base'], '0x200000')
        self.assertFalse(report['selection']['parent_ranges_translated'])

    def test_only_first_reg_tuple_is_submitted(self):
        data = tree([node('memory', {'reg': reg(0x80000000, 0x100000)
                                          + reg(0x880000000, 0x20000000)})])
        ranges = model(data)['submitted_ranges']
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0]['base'], '0x80000000')
        self.assertEqual(ranges[0]['ignored_reg_tuple_count'], 1)

    def test_host_refuses_widths_truncation_and_overflow(self):
        for value in (b'', u64(0x80000000), reg(0x80000000, 1) + b'X',
                      reg(0xfffffffffffff000, 0x1000),
                      reg(0xfffffffffffff000, 0x2000)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                model(tree([node('memory', {'reg': value})]))
        with self.assertRaisesRegex(ValueError, 'cells 2/1'):
            model(tree([node('memory', {'reg': u32(0x80000000, 0x100000)})], cells=(1, 1)))
        with self.assertRaisesRegex(ValueError, 'cells 2/1'):
            model(encode(node('', children=[node('memory', {'reg': reg(1, 1)})])))

    def test_missing_banks_are_not_an_empty_verified_map(self):
        for data in (tree([]), tree([node('memory')])):
            with self.subTest(size=len(data)), self.assertRaisesRegex(ValueError, 'no memory-prefix'):
                model(data)
        with self.assertRaises(ValueError):
            model(b'bad FDT')
        with self.assertRaisesRegex(ValueError, '2 MiB'):
            model(bytes(MAX_FDT + 1))

    def test_initial_argument_guard_is_not_acceptance(self):
        data = tree([node('memory@0', {'reg': reg(0, 0x100000)}),
                     node('memory@80000000', {'reg': reg(0x80000000, 0)})])
        report = model(data)
        self.assertEqual([r['uh_initial_nonzero_guard_passes']
                          for r in report['submitted_ranges']], [False, False])
        self.assertFalse(report['uh_acceptance_verified'])
        self.assertFalse(report['callback_return_checks_uh_success'])

    def test_cli_rejects_wrong_firmware_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wrong.bin'
            path.write_bytes(b'not HZC2')
            script = Path(__file__).with_name('check_lk_uh_ranges.py')
            result = subprocess.run([sys.executable, str(script), str(path), str(path)],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('unsupported image', result.stderr)


if __name__ == '__main__':
    unittest.main()
