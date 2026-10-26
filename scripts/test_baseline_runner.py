#!/usr/bin/env python3
"""Fault-inject the baseline gate without running a compiler or QEMU."""
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest

from validate_baseline import new_output, run_step, sha256

ROOT = Path(__file__).resolve().parent.parent


class BaselineGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)

    def run_child(self, code, required=(r'^EXPECTED PASS$',), timeout=5):
        return run_step('child', [sys.executable, '-c', code], self.output,
                        dict(os.environ), timeout, required)

    def test_success_keeps_log_and_hash(self):
        result = self.run_child(
            "import subprocess, sys\n"
            "subprocess.run([sys.executable, '-c', \"import sys; print('x'*20000, file=sys.stderr)\"], check=True)\n"
            "print('EXPECTED PASS')")
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['log_sha256'], sha256(self.output/result['log']))
        self.assertEqual((self.output/result['log']).read_text(), 'x'*20000+'\nEXPECTED PASS\n')

    def test_exit_zero_without_coverage_fails(self):
        result = self.run_child("print('SKIP: artifact absent')")
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['missing_markers'])

    def test_pass_marker_does_not_hide_nonzero_exit(self):
        result = self.run_child("print('EXPECTED PASS'); raise SystemExit(7)")
        self.assertEqual(result['returncode'], 7)
        self.assertEqual(result['status'], 'failed')

    def test_timeout_stops_a_process_group(self):
        result = self.run_child(
            "import subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c', "
            "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'], "
            "start_new_session=True)\n"
            "print(child.pid, flush=True)\n"
            "print('EXPECTED PASS', flush=True)\n"
            "time.sleep(30)\n", timeout=1)
        self.assertTrue(result['timed_out'])
        self.assertEqual(result['status'], 'failed')
        self.assertLess(result['seconds'], 6)
        child = int((self.output/result['log']).read_text().splitlines()[0])
        try:
            fd = os.pidfd_open(child)
        except ProcessLookupError:
            return
        try:
            self.assertTrue(select.select([fd], [], [], 2)[0], 'timed-out descendant still running')
        finally:
            os.close(fd)

    def test_output_cannot_reuse_an_existing_directory(self):
        with self.assertRaises(FileExistsError):
            new_output(self.output)
        result = new_output(self.output/'fresh')
        self.assertEqual(list(result.iterdir()), [])

    def test_payload_requires_the_requested_elf(self):
        result = subprocess.run([sys.executable, str(ROOT/'scripts/test_payload.py'),
                                 '--elf', str(self.output/'absent.elf')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('required R10 ELF is missing', result.stderr)
        self.assertNotIn('PAYLOAD PASS', result.stdout)

    def test_optimized_python_is_refused(self):
        result = subprocess.run([sys.executable, '-O', str(ROOT/'scripts/validate_baseline.py'),
                                 '--output-dir', str(self.output/'optimized')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('disables test assertions', result.stderr)
        self.assertFalse((self.output/'optimized').exists())


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BaselineGateTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print('BASELINE RUNNER PASS')
    sys.exit(not result.wasSuccessful())
