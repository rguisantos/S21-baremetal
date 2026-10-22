"""Bank-call contract boundaries; no firmware fixture or physical memory use."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from check_lk_memory_banks import CHUNK, LOW_BASE, model, normalize, read_scenario
from emulate_lk_memory_banks import emulate
from inspect_sec_pgtbl_hzc2 import U32, U64


def supplied(**changes):
    values = dict(total_ram_bytes=0x80000000, soc_version_x0=0x66001000,
                  soc_base_x0=0xa0000000, soc_reserved_size_x0=0x200000,
                  pgtbl_base_x0=0, pgtbl_size_x0=0,
                  harx_status_w0=1, harx_base=0, harx_size=0)
    values.update(changes)
    return values


def pairs(report):
    return [(int(n['base'], 0), int(n['size_low32'], 0)) for n in report['requested_nodes']]


class BankCallsTests(unittest.TestCase):
    def test_two_gib_boundary_and_32bit_tail(self):
        r = model(supplied())
        self.assertEqual(pairs(r), [(0x80000000, 0x20000000), (0xa0200000, 0x5fe00000)])
        self.assertEqual(r['requested_nodes'][-1]['call_offset'], '0xfaf74')
        self.assertEqual(r['high_memory']['call_count'], 0)
        lower = model(supplied(total_ram_bytes=0x7fffffff))
        self.assertEqual(pairs(lower)[-1], (0xa0200000, 0x5fdfffff))
        self.assertEqual(lower['requested_nodes'][-1]['call_offset'], '0xfb7c8')

    def test_first_byte_above_two_gib_requests_a_full_chunk(self):
        r = model(supplied(total_ram_bytes=0x80000001))
        self.assertEqual(pairs(r)[-1], (0x880000000, 0x20000000))
        self.assertEqual(r['high_memory']['bytes_past_supplied_remainder'], '0x1fffffff')
        self.assertFalse(r['high_memory']['final_chunk_is_clamped'])
        self.assertEqual(r['requested_nodes'][-1]['reg_bytes_if_written_be'],
                         '000000088000000020000000')

    def test_twelve_gib_is_only_a_supplied_scenario(self):
        r = model(supplied(total_ram_bytes=12 << 30))
        self.assertEqual(r['high_memory']['call_count'], 20)
        self.assertEqual(pairs(r)[-1], (0xae0000000, 0x20000000))
        self.assertEqual(r['high_memory']['bytes_past_supplied_remainder'], '0x0')
        for key in ('runtime_observed', 'service_replies_observed', 'provider_executed',
                    'fdt_writes_executed', 'is_final_fdt', 'memory_map_verified',
                    'free_memory_verified'):
            self.assertFalse(r[key], key)

    def test_unaligned_pgtbl_size_keeps_the_split(self):
        r = model(supplied(pgtbl_base_x0=0xe0000000, pgtbl_size_x0=0x1003))
        self.assertEqual(pairs(r), [(0x80000000, 0x20000000),
                                    (0xa0200000, 0x3fe00000),
                                    (0xe0001003, 0x1fffeffd)])
        self.assertEqual(r['requested_nodes'][-1]['call_offset'], '0xfb690')
        self.assertEqual(r['sec_pgtbl']['w22_split_flag'], 1)
        self.assertFalse(r['sec_pgtbl']['size_alignment_was_checked'])

    def test_rejected_pgtbl_base_does_not_split_ram(self):
        expected = pairs(model(supplied()))
        for base in (0, 3, U64, 0xe0001000):
            with self.subTest(base=base):
                self.assertEqual(pairs(model(supplied(pgtbl_base_x0=base,
                                                     pgtbl_size_x0=0x200000))), expected)

    def test_harx_gap_requires_success_and_both_nonzero_outputs(self):
        r = model(supplied(harx_status_w0=0, harx_base=0xc0000000, harx_size=0x1400000))
        self.assertEqual(pairs(r), [(0x80000000, 0x20000000),
                                    (0xa0200000, 0x1fe00000),
                                    (0xc1400000, 0x3ec00000)])
        self.assertTrue(r['harx_gap_taken'])
        for status, base, size in ((1, 0xc0000000, 0x1400000),
                                   (U32, 0xc0000000, 0x1400000),
                                   (0, 0, 0x1400000), (0, 0xc0000000, 0)):
            with self.subTest(status=status, base=base, size=size):
                other = model(supplied(harx_status_w0=status, harx_base=base, harx_size=size))
                self.assertFalse(other['harx_gap_taken'])
                self.assertEqual(len(other['requested_nodes']), 2)

    def test_subtraction_wrap_is_not_a_memory_validation(self):
        r = model(supplied(pgtbl_base_x0=0x90000000, pgtbl_size_x0=0x200000))
        self.assertEqual(pairs(r)[1], (0xa0200000, 0xefe00000))
        self.assertEqual(r['requested_nodes'][1]['end_exclusive_math'], '0x190000000')
        self.assertFalse(r['memory_map_verified'])

    def test_soc_widths_and_cursor_wrap(self):
        r = model(supplied(soc_version_x0=0x1234567866001000,
                           soc_base_x0=U64-1, soc_reserved_size_x0=0x100000002))
        self.assertEqual(r['stop'], 'bank_calls_complete')
        self.assertEqual(r['cursor_after_soc_wrapped64'], '0x0')
        self.assertEqual(r['soc_size_upper32_ignored'], '0x1')
        self.assertEqual(pairs(r)[-1], (0, 0))
        self.assertTrue(r['requested_nodes'][-1]['zero_size'])

    def test_zero_size_and_overflowing_end_are_recorded_without_authorizing_memory(self):
        zero = model(supplied(soc_base_x0=LOW_BASE))
        self.assertEqual(pairs(zero)[0], (LOW_BASE, 0))
        self.assertTrue(zero['requested_nodes'][0]['zero_size'])
        overflow = model(supplied(soc_base_x0=U64-1, soc_reserved_size_x0=1))
        self.assertEqual(pairs(overflow)[-1], (U64, 1))
        self.assertTrue(overflow['requested_nodes'][-1]['end_overflows_u64'])

    def test_soc_failures_park_before_any_bank_request(self):
        cases = [({'soc_version_x0': 0}, 'soc_version_park_0xfadc4'),
                 ({'soc_base_x0': U64}, 'soc_base_park_0xfb66c'),
                 ({'soc_reserved_size_x0': U32}, 'soc_size_park_0xfb65c'),
                 ({'soc_reserved_size_x0': 0x12345678ffffffff}, 'soc_size_park_0xfb65c')]
        for changes, stop in cases:
            with self.subTest(changes=changes):
                r = model(supplied(**changes))
                self.assertEqual(r['stop'], stop)
                self.assertEqual(r['requested_nodes'], [])

    def test_host_call_limit_does_not_loop_over_huge_input(self):
        r = model(supplied(total_ram_bytes=LOW_BASE + 126 * CHUNK))
        self.assertEqual(len(r['requested_nodes']), 128)
        for total in (LOW_BASE + 127 * CHUNK, U64):
            with self.subTest(total=total), self.assertRaisesRegex(ValueError, 'host limit'):
                model(supplied(total_ram_bytes=total))


class ScenarioBoundaryTests(unittest.TestCase):
    def test_all_inputs_are_explicit_unsigned_values(self):
        self.assertEqual(normalize({k: hex(v) for k, v in supplied().items()}), supplied())
        bad = [None, [], {}, dict(supplied(), extra=1)]
        missing = supplied()
        del missing['soc_base_x0']
        bad.append(missing)
        for value in (-1, U64+1, True, 1.5, None, '1+2', '0x'+'0'*25):
            bad.append(supplied(soc_base_x0=value))
        bad.append(supplied(harx_status_w0=1 << 32))
        for values in bad:
            with self.subTest(values=values), self.assertRaises(ValueError):
                normalize(values)

    def test_duplicate_json_and_oversized_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'scenario.json'
            p.write_text(json.dumps(supplied()))
            self.assertEqual(read_scenario(p), supplied())
            p.write_text(json.dumps(supplied())[:-1]+', "soc_base_x0": 0}')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                read_scenario(p)
            p.write_bytes(b' ' * 8193)
            with self.assertRaisesRegex(ValueError, '8192'):
                read_scenario(p)

    def test_scenario_read_is_bounded_before_parsing(self):
        stream = unittest.mock.MagicMock()
        stream.__enter__.return_value = stream
        stream.read.return_value = b' ' * 8193
        with patch('builtins.open', return_value=stream):
            with self.assertRaises(ValueError):
                read_scenario('untrusted')
        stream.read.assert_called_once_with(8193)

    def test_deeply_nested_json_is_reported_as_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'scenario.json'
            p.write_text('[' * 2000 + '0' + ']' * 2000)
            with self.assertRaises(ValueError):
                read_scenario(p)

    def test_cli_refuses_wrong_firmware_without_scenario_output(self):
        script = Path(__file__).with_name('check_lk_memory_banks.py')
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'sboot.bin'
            p.write_bytes(b'not HZC2')
            proc = subprocess.run([sys.executable, str(script), str(p)],capture_output=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b'')
        self.assertIn(b'unsupported image', proc.stderr)

    def test_emulator_refuses_wrong_firmware_before_optional_dependency(self):
        with self.assertRaisesRegex(ValueError, 'exact HZC2'):
            emulate(b'not HZC2', supplied())


if __name__ == '__main__':
    unittest.main()
