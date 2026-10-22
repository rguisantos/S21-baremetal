#!/usr/bin/env python3
"""Host checks for the Mach-O contract and failure detection (no QEMU).

Actual QEMU success and the corrupted-fixture control are separate runs;
these tests do not count as XNU boots or iOS compatibility tests.
"""
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


ROOT = Path(__file__).resolve().parents[1]
lab = module("s21_xnu_lab", ROOT / "scripts/run_xnu_lab.py")
macho = module("s21_xnu_macho", ROOT / "lab/xnu/macho.py")


def log_with_success():
    return (b"Darwin Kernel Version 22.5.0: test\n"
            b"gic: v3, virtual timer on PPI 27\n"
            b'apfs: volume 0 "S21Lab" of container 0\n'
            + b"\n".join(lab.MARKERS)
            + b"\nCPU halted\nkernel returned: log at 0\nreturned 1000 0\n== END OF LOG ==\n")


class ResultTests(unittest.TestCase):
    def test_complete_success(self):
        self.assertTrue(all(lab.assess_log(log_with_success(), 0, False).values()))

    def test_empty_log_is_failure(self):
        self.assertFalse(all(lab.assess_log(b"", 0, False).values()))

    def test_each_missing_user_stage_is_failure(self):
        for marker in lab.MARKERS:
            with self.subTest(marker=marker):
                data = log_with_success().replace(marker, b"not checked")
                self.assertFalse(all(lab.assess_log(data, 0, False).values()))

    def test_reordered_stages_are_failure(self):
        data = log_with_success().replace(lab.MARKERS[0], b"TEMP")
        data = data.replace(lab.MARKERS[1], lab.MARKERS[0]).replace(b"TEMP", lab.MARKERS[1])
        self.assertFalse(lab.assess_log(data, 0, False)["ordered_user_checks"])

    def test_late_failure_cannot_be_hidden_by_pass(self):
        data = log_with_success() + b"S21 XNU LAB: FAIL RB_HALT returned\n"
        self.assertFalse(lab.assess_log(data, 0, False)["no_failure_marker"])

    def test_panic_cannot_be_hidden_by_exit_zero(self):
        data = log_with_success() + b"panic(cpu 0 caller 0): failed\n"
        self.assertFalse(lab.assess_log(data, 0, False)["no_panic"])

    def test_timeout_is_failure_even_with_markers(self):
        checks = lab.assess_log(log_with_success(), None, True)
        self.assertFalse(checks["no_timeout"])
        self.assertFalse(checks["qemu_exit_zero"])

    def test_abnormal_loader_return_is_failure(self):
        data = log_with_success().replace(b"returned 1000 0", b"returned 1000 1")
        self.assertFalse(lab.assess_log(data, 0, False)["loader_returned_normally"])

    def test_truncated_return_log_is_failure(self):
        data = log_with_success().replace(b"== END OF LOG ==", b"")
        self.assertFalse(lab.assess_log(data, 0, False)["complete_return_log"])

    def test_traps_are_failures(self):
        for extra in (b"usertrap:", b"userabort:", b"early-exception"):
            with self.subTest(extra=extra):
                self.assertFalse(all(lab.assess_log(log_with_success() + extra, 0, False).values()))

    def test_wrong_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                lab.verified(path, "0" * 64)


class MachOTests(unittest.TestCase):
    def test_entry_lies_in_file_backed_rx_segment(self):
        payload = b"\xc0\x03\x5f\xd6"      # ret, format fixture only
        image = macho.build_init(payload)
        magic, cpu, subtype, kind, count, command_bytes, flags, reserved = struct.unpack_from("<8I", image)
        self.assertEqual((magic, cpu, subtype, kind), (0xFEEDFACF, 0x100000C, 0, 2))
        cursor, segments, entry = 32, [], None
        for _ in range(count):
            command, size = struct.unpack_from("<II", image, cursor)
            self.assertGreaterEqual(size, 8)
            self.assertLessEqual(cursor + size, 32 + command_bytes)
            if command == 0x19:
                name, va, memsz, off, filesz, maxprot, initprot, nsect, _ = struct.unpack_from(
                    "<16sQQQQIIII", image, cursor + 8)
                self.assertLessEqual(off + filesz, len(image))
                if filesz:
                    self.assertEqual((maxprot, initprot), (5, 5))
                    self.assertEqual((va % 0x4000, off % 0x4000), (0, 0))
                    segments.append((va, memsz, off, filesz))
            if command == 5:
                flavor, words = struct.unpack_from("<II", image, cursor + 8)
                self.assertEqual((flavor, words, size), (6, 68, 288))
                entry = struct.unpack_from("<Q", image, cursor + 16 + 256)[0]
            cursor += size
        self.assertEqual(cursor, 32 + command_bytes)
        self.assertEqual(len(segments), 1)
        va, memsz, off, filesz = segments[0]
        self.assertLessEqual(va, entry)
        self.assertLess(entry + len(payload), va + filesz)
        self.assertEqual(image[off + entry - va:off + entry - va + len(payload)], payload)

    def test_empty_and_oversized_init_are_rejected(self):
        for data in (b"", b"x" * (0x4000 - 0x1000 + 1)):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                macho.build_init(data)


if __name__ == "__main__":
    unittest.main()
