"""Host fixtures for embedded config bounds and the bounded EL2 log collector."""
import gzip
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from check_harx_log_evidence import MAX_CONFIG, embedded_config

SCRIPT = Path(__file__).with_name('collect_el2_log.sh')


def image(raw, gzip_data=None):
    return b'prefix00IKCFG_ST' + (gzip.compress(raw) if gzip_data is None else gzip_data) + b'IKCFG_EDsuffix'


class ConfigTests(unittest.TestCase):
    def test_config_values_hash_and_disabled_entries(self):
        raw = b'CONFIG_EXYNOS_EL2=m\nCONFIG_ARM64_4K_PAGES=y\n# CONFIG_UNUSED is not set\n'
        result = embedded_config(image(raw))
        self.assertEqual(result['entries'], dict(CONFIG_EXYNOS_EL2='m',
                                                CONFIG_ARM64_4K_PAGES='y', CONFIG_UNUSED='n'))
        self.assertEqual(result['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['start_marker_image_offset'], '0x8')

    def test_requires_bounded_complete_single_gzip(self):
        zipped = gzip.compress(b'CONFIG_EXYNOS_EL2=m\n')
        for encoded in (zipped[:-4], zipped + b'X', zipped + zipped, b'invalid',
                        gzip.compress(b'X' * (MAX_CONFIG + 1))):
            with self.subTest(size=len(encoded)), self.assertRaises(ValueError):
                embedded_config(image(b'', encoded))

    def test_refuses_duplicate_or_missing_markers_and_assignments(self):
        for data in (b'no markers', image(b'') + b'IKCFG_ST',
                     b'IKCFG_ED' + image(b''),
                     image(b'CONFIG_X=y\nCONFIG_X=m\n'),
                     image(b'CONFIG_X=y\n# CONFIG_X is not set\n')):
            with self.subTest(data=data[:40]), self.assertRaises(ValueError):
                embedded_config(data)


class CollectorTests(unittest.TestCase):
    def run_collector(self, directory, name='output'):
        root, out = Path(directory) / 'sys', Path(directory) / name
        root.mkdir(exist_ok=True)
        result = subprocess.run(['sh', str(SCRIPT), str(out)],
                                env=dict(os.environ, S21_EL2_SYS_ROOT=str(root)),
                                capture_output=True, text=True, timeout=10)
        return result, out

    def test_missing_and_existing_output_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            result, out = self.run_collector(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = (out / 'report.txt').read_bytes()
            self.assertIn(b'ABSENT (or hidden', report)
            self.assertFalse((out / 'el2-log.txt').exists())
            result, _ = self.run_collector(directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((out / 'report.txt').read_bytes(), report)

    def test_one_capture_uses_canonical_path_and_is_bounded(self):
        with tempfile.TemporaryDirectory(prefix='harx log ') as directory:
            root = Path(directory) / 'sys'
            node = root / 'devices/platform/el2_dynamic_lv3/exynos_el2_log'
            alias = root / 'bus/platform/drivers/exynos-el2/device/exynos_el2_log'
            node.parent.mkdir(parents=True)
            alias.parent.mkdir(parents=True)
            node.write_bytes(b'A' * 6000)
            alias.write_bytes(b'alias must not replace the first capture')
            result, out = self.run_collector(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((out / 'el2-log.txt').read_bytes(), b'A' * 4096)
            report = (out / 'report.txt').read_text()
            self.assertEqual(report.count('READ_EXIT='), 1)
            self.assertIn('READ_EXIT=0 BYTES=4096', report)
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)
            self.assertEqual((out / 'el2-log.txt').stat().st_mode & 0o777, 0o600)
            self.assertEqual(node.stat().st_size, 6000)
            self.assertEqual(alias.read_bytes(), b'alias must not replace the first capture')

    def test_driver_path_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            node = Path(directory) / 'sys/bus/platform/drivers/exynos-el2/device/exynos_el2_log'
            node.parent.mkdir(parents=True)
            node.write_bytes(b'fixture log\n')
            result, out = self.run_collector(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((out / 'el2-log.txt').read_bytes(), b'fixture log\n')

    def test_blocked_source_times_out_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            node = Path(directory) / 'sys/devices/platform/el2_dynamic_lv3/exynos_el2_log'
            node.parent.mkdir(parents=True)
            os.mkfifo(node)
            result, out = self.run_collector(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = (out / 'report.txt').read_text()
            self.assertIn('READ_EXIT=124 BYTES=0', report)
            self.assertEqual(report.count('READ_EXIT='), 1)


if __name__ == '__main__':
    unittest.main()
