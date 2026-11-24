import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from inspect_a0_runtime import compare, inspect


BANNER = b'Kernel: Linux version example\n'
HEADER = b'===\n== dumpstate: fixture\n===\n' + BANNER
TITLE = b'------ LSMOD (lsmod) ------\nModule  Size  Used by\n'
ROW = b'gpu_cooling  36864  0 [permanent]\n'
END = b"------ 0.016s was the duration of 'LSMOD' ------\n"


class DumpstateComparison(unittest.TestCase):
    def test_names_use_first_column_and_compare_as_a_set(self):
        row = b'other_driver 53248 1 pdic_notifier_module\n'
        a = compare(io.BytesIO(HEADER + TITLE + ROW + row + END))
        b = compare(io.BytesIO(HEADER + TITLE + row + ROW + END))
        self.assertEqual(a, b)
        self.assertEqual(a['banner_match'], 'unknown')
        self.assertEqual(a['module_count'], 2)
        self.assertFalse(a['matches_stock_names'])
        self.assertTrue(a['listed']['gpu_cooling'])
        self.assertFalse(a['listed']['pdic_notifier_module'])

    def test_candidate_banner_is_independent_of_inventory(self):
        banner = (
            b'Linux version 5.4.242 (s21-a0@offline) (Android (6443078 based on r383902) c'
            b'lang version 11.0.1 (https://android.googlesource.com/toolchain/llvm-project'
            b' b397f81060ce6d701042b782172ed13bee898b79), LLD 11.0.1 (/buildbot/tmp/tmp6_m'
            b'7QH b397f81060ce6d701042b782172ed13bee898b79)) #1 SMP PREEMPT Sun Nov 1 00:0'
            b'0:00 UTC 2026\n'
        )
        fixture = HEADER.replace(BANNER, b'Kernel: ' + banner) + TITLE + END
        result = compare(io.BytesIO(fixture))
        self.assertEqual(result['banner_match'], 'aligned_a0')
        self.assertFalse(result['matches_stock_names'])
        modified = fixture.replace(b'00:00:00', b'00:00:01')
        self.assertEqual(compare(io.BytesIO(modified))['banner_match'], 'unknown')

    def test_embedded_kernel_lines_do_not_set_header(self):
        with self.assertRaisesRegex(ValueError, 'missing kernel'):
            compare(io.BytesIO(HEADER.replace(BANNER, b'') + b'------ LAST KMSG ------\n' +
                               BANNER + TITLE + ROW + END))

    def test_reject_ambiguous_and_partial_evidence(self):
        for capture in (HEADER + BANNER + TITLE + ROW + END, HEADER + TITLE + ROW,
                        HEADER + TITLE + ROW + ROW + END, HEADER + TITLE + b'error\n' + END,
                        HEADER + TITLE + ROW + END + TITLE + END):
            with self.subTest(capture=capture), self.assertRaises(ValueError):
                compare(io.BytesIO(capture))

    def test_zip_uses_selected_main_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'report.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('main_entry.txt', 'dumpstate-test.txt\n')
                z.writestr('dumpstate-test.txt', HEADER + TITLE + ROW + END)
                z.writestr('FS/cache/recovery/last_kmsg', HEADER + TITLE + END)
            self.assertEqual(inspect(path)['module_count'], 1)

    def test_bad_main_entry(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'report.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('main_entry.txt', 'FS/cache/recovery/dumpstate-test.txt')
            with self.assertRaisesRegex(ValueError, 'invalid main_entry'):
                inspect(path)


if __name__ == '__main__':
    unittest.main()
