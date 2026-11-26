#!/usr/bin/env python3
"""Testes do s21xnu-switch.sh com arquivos no lugar da BOOT (dash e bash)."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "s21xnu-switch.sh"
SIZE = 1 << 20
SHELLS = [s for s in ("dash", "bash") if shutil.which(s)]


def image(tag):
    data = bytearray(SIZE)
    data[:8] = b"ANDROID!"
    data[8:8 + len(tag)] = tag
    return bytes(data)


class SwitchTests(unittest.TestCase):
    shell = "dash"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = pathlib.Path(self.tmp.name)
        self.boot, self.store, self.marker = t / "BOOT", t / "cache" / "s21xnu", t / "rebooted"
        self.xnu = t / "xnu.img"
        self.boot.write_bytes(image(b"stock"))
        self.xnu.write_bytes(image(b"s21xnu-shim"))

    def run_sw(self, *args, ok=True):
        env = dict(os.environ, S21XNU_BOOT_DEV=str(self.boot), S21XNU_DIR=str(self.store),
                   S21XNU_REBOOT="touch %s" % self.marker)
        r = subprocess.run([self.shell, str(SCRIPT)] + list(args), env=env, capture_output=True, text=True)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        else:
            self.assertNotEqual(r.returncode, 0, r.stdout)
        return r.stdout + r.stderr

    def test_full_cycle(self):
        out = self.run_sw("install", str(self.xnu))
        self.assertIn("BOOT atual: stock", out)
        self.assertEqual((self.store / "stock-boot.img").read_bytes(), image(b"stock"))
        self.assertTrue((self.store / "s21xnu-switch.sh").exists())
        self.run_sw("to-xnu")
        self.assertEqual(self.boot.read_bytes(), image(b"s21xnu-shim"))
        self.assertTrue(self.marker.exists())
        self.assertIn(": xnu", self.run_sw("status"))
        self.marker.unlink()
        self.run_sw("to-android", "--no-reboot")
        self.assertEqual(self.boot.read_bytes(), image(b"stock"))
        self.assertFalse(self.marker.exists())
        self.assertIn("já está em stock", self.run_sw("to-android", "--no-reboot"))

    def test_install_refusals(self):
        self.xnu.write_bytes(image(b"x")[:SIZE - 4096])
        self.assertIn("tamanho da BOOT", self.run_sw("install", str(self.xnu), ok=False))
        self.xnu.write_bytes(b"\0" * SIZE)
        self.assertIn("ANDROID!", self.run_sw("install", str(self.xnu), ok=False))
        self.assertIn("uso: install", self.run_sw("install", ok=False))
        self.assertFalse((self.store / "stock-boot.img").exists())

    def test_reinstall_keeps_backup_and_refuses_corrupt_backup(self):
        self.run_sw("install", str(self.xnu))
        self.run_sw("to-xnu", "--no-reboot")
        self.xnu.write_bytes(image(b"s21xnu-shim-v2"))
        self.assertIn("mantido", self.run_sw("install", str(self.xnu)))
        self.assertEqual((self.store / "stock-boot.img").read_bytes(), image(b"stock"))
        st = self.store / "stock-boot.img"
        st.write_bytes(image(b"corrompido"))
        self.assertIn("não confere", self.run_sw("install", str(self.xnu), ok=False))
        self.assertIn("não confere", self.run_sw("to-android", "--no-reboot", ok=False))

    def test_unknown_boot_blocks_xnu_but_allows_return(self):
        self.run_sw("install", str(self.xnu))
        self.boot.write_bytes(image(b"meio-gravado"))
        self.assertIn("desconhecido", self.run_sw("to-xnu", "--no-reboot", ok=False))
        self.assertEqual(self.boot.read_bytes(), image(b"meio-gravado"))
        self.run_sw("to-android", "--no-reboot")
        self.assertEqual(self.boot.read_bytes(), image(b"stock"))

    def test_commands_need_install(self):
        self.assertIn("install", self.run_sw("to-xnu", "--no-reboot", ok=False))
        self.assertEqual(self.boot.read_bytes(), image(b"stock"))

    def test_install_from_xnu_boot_is_refused(self):
        self.boot.write_bytes(image(b"s21xnu-shim"))
        self.assertIn("já contém", self.run_sw("install", str(self.xnu), ok=False))

    def test_unknown_command_prints_usage(self):
        r = subprocess.run([self.shell, str(SCRIPT), "x"], capture_output=True, text=True,
                           env=dict(os.environ, S21XNU_BOOT_DEV=str(self.boot), S21XNU_DIR=str(self.store)))
        self.assertEqual(r.returncode, 2)
        self.assertIn("install XNU_BOOT.img", r.stdout)


class BashSwitchTests(SwitchTests):
    shell = "bash"


if "dash" not in SHELLS:
    del SwitchTests
if "bash" not in SHELLS:
    del BashSwitchTests

if __name__ == "__main__":
    unittest.main()
