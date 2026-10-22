#!/usr/bin/env python3
"""Host tests for the bounded, read-only LK copy model; no firmware fixture."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from check_lk_v3_layout import check_fdt_initrd, model
from test_fdt import encode, node, u32, u64


def fixture():
    # Unequal and non-page-aligned sizes expose alignment/concatenation errors.
    boot = bytearray(3*4096+37)
    boot[:8] = b'ANDROID!'
    struct.pack_into('<II', boot, 8, 4097, 37)
    struct.pack_into('<I', boot, 20, 1580)
    struct.pack_into('<I', boot, 40, 3)
    struct.pack_into('<QQQ', boot, 4096+8, 0x80000, 8192, 8)
    boot[4096+56:4096+60] = b'ARMd'
    boot[3*4096:] = b'B'*37
    vendor = bytearray(4*4096+64)
    vendor[:8] = b'VNDRBOOT'
    struct.pack_into('<II', vendor, 8, 3, 4096)
    struct.pack_into('<I', vendor, 24, 8193)
    struct.pack_into('<II', vendor, 2096, 2112, 64)
    vendor[4096:4096+8193] = b'V'*8193
    return boot, vendor


class LayoutTest(unittest.TestCase):
    def test_chosen_values_match_copies_without_padding(self):
        boot, vendor = fixture()
        report = model(boot, vendor, 0)
        chosen = report['chosen_initrd']
        self.assertEqual(chosen['start'], report['copies'][1]['destination'])
        self.assertEqual(chosen['end_exclusive'], report['copies'][2]['destination_end'])
        self.assertEqual(chosen['property_bytes_be'],
                         {'linux,initrd-start':'84080000', 'linux,initrd-end':'84082026'})
        self.assertFalse(report['fdt_initrd_check']['performed'])

    def test_partial_fdt_check_does_not_validate_memory_or_reservations(self):
        boot, vendor = fixture()
        report = model(boot, vendor, 0)
        data = encode(node('', children=[node('chosen',
                      {'linux,initrd-start':u32(0x84080000), 'linux,initrd-end':u32(0x84082026)})]))
        result = check_fdt_initrd(data, report)
        self.assertTrue(result['matches'])
        self.assertEqual(result['scope'], 'chosen_initrd_only')
        self.assertFalse(result['is_final_fdt'])
        self.assertFalse(result['memory_map_verified'])
        self.assertFalse(result['reservations_verified'])

    def test_stale_missing_or_different_width_initrd_is_rejected(self):
        boot, vendor = fixture()
        report = model(boot, vendor, 0)
        cases = ({}, {'linux,initrd-start':u32(0x84080000)},
                 {'linux,initrd-start':u32(0x84000000), 'linux,initrd-end':u32(0x841fffff)},
                 {'linux,initrd-start':u64(0x84080000), 'linux,initrd-end':u64(0x84082026)},
                 {'linux,initrd-start':u32(0x84080000), 'linux,initrd-end':u32(0x84082027)})
        for props in cases:
            with self.subTest(props=props), self.assertRaisesRegex(ValueError, '/chosen/'):
                check_fdt_initrd(encode(node('', children=[node('chosen', props)])), report)

    def test_partial_check_rejects_malformed_fdt(self):
        boot, vendor = fixture()
        with self.assertRaises(ValueError):
            check_fdt_initrd(b'bad', model(boot, vendor, 0))

    def test_duplicate_property_cannot_hide_stale_initrd(self):
        boot, vendor = fixture()
        data = bytearray(encode(node('', children=[node('chosen', {
            'linux,initrd-start':u32(0x84000000), 'candidate-start':u32(0x84080000),
            'linux,initrd-end':u32(0x84082026)})])))
        strings = struct.unpack_from('>I', data, 12)[0]
        stale_name = data.index(b'linux,initrd-start\0', strings)-strings
        replacement_name = data.index(b'candidate-start\0', strings)-strings
        pos = data.index(u32(3, 4, replacement_name)+u32(0x84080000))
        struct.pack_into('>I', data, pos+8, stale_name)
        with self.assertRaisesRegex(ValueError, 'duplicate FDT property'):
            check_fdt_initrd(bytes(data), model(boot, vendor, 0))

    def test_duplicate_node_cannot_hide_stale_chosen(self):
        boot, vendor = fixture()
        data = encode(node('', children=[node('chosen', {
            'linux,initrd-start':u32(0x84000000), 'linux,initrd-end':u32(0x841fffff)}),
            node('chosen', {'linux,initrd-start':u32(0x84080000),
                            'linux,initrd-end':u32(0x84082026)})]))
        with self.assertRaisesRegex(ValueError, 'duplicate FDT node'):
            check_fdt_initrd(data, model(boot, vendor, 0))

    def test_unaligned_components_and_separate_memory_extent(self):
        boot, vendor = fixture()
        report = model(boot, vendor, 0)
        kernel, vendor_rd, boot_rd = report['copies']
        self.assertEqual((kernel['file_offset'], kernel['size'], kernel['destination']),
                         ('0x1000', 4097, '0x80080000'))
        self.assertEqual((vendor_rd['file_offset'], vendor_rd['size']), ('0x1000', 8193))
        self.assertEqual((boot_rd['file_offset'], boot_rd['destination']),
                         ('0x3000', '0x84082001'))
        self.assertEqual(report['vendor_dtb_region']['file_offset'], '0x4000')
        self.assertEqual(report['image']['bytes_beyond_kernel_copy'], 4095)
        self.assertFalse(report['runtime_observed'])
        self.assertFalse(report['bootability_verified'])
        self.assertFalse(report['vendor_dtb_region']['is_final_fdt'])

    def test_all_64_offset_scenarios(self):
        boot, vendor = fixture()
        for offset in range(0, 0x200000, 0x8000):
            with self.subTest(offset=offset):
                report = model(boot, vendor, offset)
                self.assertEqual(int(report['modeled_kernel_entry'], 16), 0x80080000+offset)
                self.assertEqual(report['copies'][1]['destination'], '0x84080000')

    def test_invalid_offsets(self):
        boot, vendor = fixture()
        for offset in (-0x8000, 1, 0x200000):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'offset'):
                model(boot, vendor, offset)

    def test_truncated_components(self):
        boot, vendor = fixture()
        for b, v in ((boot[:100], vendor), (boot, vendor[:100]),
                     (boot[:4096+4096], vendor), (boot[:-1], vendor),
                     (boot, vendor[:4096+8192]), (boot, vendor[:-1])):
            with self.subTest(lengths=(len(b), len(v))), self.assertRaises(ValueError):
                model(b, v, 0)

    def test_unsupported_or_dangerous_layouts(self):
        mutations = [('boot', 40, 4), ('boot', 20, 0), ('vendor', 8, 4),
                     ('vendor', 12, 0), ('vendor', 12, 2048), ('vendor', 2096, 0),
                     ('boot', 8, 0xffffffff), ('vendor', 24, 0xffffffff),
                     ('vendor', 2100, 0xffffffff), ('boot', 4096+24, 1),
                     ('boot', 4096+16, 1), ('boot', 4096+16, 0x4100000)]
        for which, off, value in mutations:
            boot, vendor = fixture()
            struct.pack_into('<I', boot if which == 'boot' else vendor, off, value)
            with self.subTest(which=which, off=off, value=value), self.assertRaises(ValueError):
                model(boot, vendor, 0)

    def test_header_addresses_do_not_choose_destination(self):
        boot, vendor = fixture()
        before = model(boot, vendor, 0x8000)
        struct.pack_into('<II', vendor, 16, 0x10008000, 0x11000000)
        struct.pack_into('<Q', vendor, 2104, 0x11f00000)
        after = model(boot, vendor, 0x8000)
        self.assertEqual(before['copies'], after['copies'])

    def test_cli_rejects_wrong_firmware_before_reporting_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp)/'sboot.bin'
            wrong.write_bytes(b'bad')
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('check_lk_v3_layout.py')),
                                     str(wrong), str(wrong), str(wrong), '--offset', '0'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('unsupported image', result.stderr)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
