#!/usr/bin/env python3
"""Testes do kit de primeiro boot com firmware sintético (pins sintéticos)."""
import hashlib
import io
import pathlib
import sys
import tarfile
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
import prepare_first_boot as kit  # noqa: E402
import mk_sboot_bootimg as mk  # noqa: E402
import capture_a0_container as pack  # noqa: E402
import capture_a0_formats as fmt  # noqa: E402
import test_avb_lab  # noqa: E402
from test_capture_a0_parent import lz4  # noqa: E402
from test_mk_sboot_bootimg import shim_image, stock_boot, vendor_boot  # noqa: E402


def sha(b):
    return hashlib.sha256(b).hexdigest()


class KitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        avb = test_avb_lab.AvbLabTests              # chaves RSA reais e boot stock sintético com AVB
        avb.setUpClass()
        cls.addClassCleanup(avb.doClassCleanups)
        cls.stock = avb.stock
        cls.pem = avb.pems[1]
        cls.vendor = vendor_boot(b"V" * 12017257)    # tamanho do ramdisk vendor HZC2
        cls.shim = shim_image()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def test_kit_contents(self):
        out = self.root / "kit"
        rep = kit.prepare(self.stock, self.vendor, self.shim, self.pem, out)
        boot = (out / "boot.img").read_bytes()
        self.assertEqual(len(boot), len(self.stock))
        self.assertTrue(fmt.layout(boot)["avb"]["all_hashes_match"])
        self.assertTrue(pack.signature_valid(pack.describe(boot)))
        self.assertEqual(rep["expected_initrd_end"], hex(0x84080000 + 12017257 + len(mk.PROBE_RAMDISK)))
        with tarfile.open(out / "AP_s21xnu_sonda.tar") as tf:
            self.assertEqual(tf.getnames(), ["boot.img"])
            self.assertEqual(tf.extractfile("boot.img").read(), boot)
        tar, md5 = (out / "AP_s21xnu_sonda.tar").read_bytes(), (out / "AP_s21xnu_sonda.tar.md5").read_bytes()
        self.assertTrue(md5.startswith(tar))
        with tarfile.open(out / "AP_stock_boot.tar") as tf:
            self.assertEqual(tf.getnames(), ["boot.img"])
            self.assertEqual(tf.extractfile("boot.img").read(), self.stock)
        self.assertTrue((out / "AP_stock_boot.tar.md5").read_bytes().endswith(b"  AP_stock_boot.tar\n"))
        self.assertEqual(md5[len(tar):], ("%s  AP_s21xnu_sonda.tar\n" % hashlib.md5(tar).hexdigest()).encode())
        roteiro = (out / "ROTEIRO.md").read_text()
        self.assertIn("end=84BF5E89", roteiro)
        self.assertIn(rep["bootimg"]["sha256"], roteiro)
        for line in (out / "SHA256SUMS").read_text().splitlines():
            h, name = line.split("  ")
            self.assertEqual(sha((out / name).read_bytes()), h, name)
        self.assertTrue((out / "s21xnu-switch.sh").stat().st_mode & 0o100)

    def test_blind_kit_roteiro(self):
        for blind in ("entrada", "etapas", "relogio", "tela"):
            out = self.root / blind
            rep = kit.prepare(self.stock, self.vendor, self.shim, self.pem, out, blind)
            self.assertEqual(rep["cega"], blind)
            r = (out / "ROTEIRO.md").read_text()
            self.assertIn("show_reset_reason_rawdata", r)
            self.assertIn("/proc/sec_log", r)
            self.assertEqual("`0x5112`" in r, blind == "relogio")
            self.assertEqual("`0x6TTG`" in r, blind == "tela")
            self.assertIn("`0x5101`", r)
            self.assertIn("to-xnu --no-reboot", r)
            self.assertNotIn("INITRD", r)
            self.assertEqual("`0x510F`" in r, blind == "etapas")
        self.assertEqual(kit.BLIND, {"entrada": "1", "etapas": "2", "relogio": "3", "tela": "4"})
        patch = kit.PATCH3.read_text()
        for needle in ("0x15860000", "0x12345604", "#0x80c", "#0x808", "#0x3c00", "0x19f00000"):
            self.assertIn(needle, patch)
        self.assertNotIn("#0x810", patch)        # SYSIP_DAT0 não é mais escrito

    def test_reproducible(self):
        a = kit.prepare(self.stock, self.vendor, self.shim, self.pem, self.root / "a")
        b = kit.prepare(self.stock, self.vendor, self.shim, self.pem, self.root / "b")
        self.assertEqual(a["files"], b["files"])

    def test_output_must_be_new(self):
        (self.root / "x").mkdir()
        with self.assertRaisesRegex(kit.KitError, "novo"):
            kit.prepare(self.stock, self.vendor, self.shim, self.pem, self.root / "x")

    def test_load_stock_pins_raw_and_lz4(self):
        d = self.root / "stock"
        d.mkdir()
        pins = {"stock_raw": {"boot.img": {"bytes": len(self.stock), "sha256": sha(self.stock)}},
                "stock_lz4": {}}
        (d / "boot.img").write_bytes(self.stock)
        self.assertEqual(kit.load_stock(d, "boot.img", pins), self.stock)
        (d / "boot.img").write_bytes(self.stock[:-1] + b"\1")
        with self.assertRaisesRegex(kit.KitError, "não é o HZC2"):
            kit.load_stock(d, "boot.img", pins)
        (d / "boot.img").unlink()
        packed = lz4(self.stock)
        pins["stock_lz4"]["boot.img.lz4"] = {"bytes": len(packed), "sha256": sha(packed)}
        (d / "boot.img.lz4").write_bytes(packed)
        self.assertEqual(kit.load_stock(d, "boot.img", pins), self.stock)
        (d / "boot.img.lz4").write_bytes(packed + b"\0")
        with self.assertRaisesRegex(kit.KitError, "lz4 não é"):
            kit.load_stock(d, "boot.img", pins)
        (d / "boot.img.lz4").unlink()
        with self.assertRaisesRegex(kit.KitError, "ausente"):
            kit.load_stock(d, "boot.img", pins)

    def test_cli_refuses_missing_or_foreign_firmware(self):
        import contextlib
        d = self.root / "vazio"
        d.mkdir()
        args = ["--stock-dir", str(d), "--s21xnu", str(self.root), "--out", str(self.root / "o")]
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(kit.main(args), 2)
        self.assertIn("ausente", err.getvalue())
        (d / "boot.img").write_bytes(self.stock)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(kit.main(args), 2)
        self.assertIn("não é o HZC2", err.getvalue())
        self.assertFalse((self.root / "o").exists())

    def test_repo_pins_are_hzc2_partitions(self):
        import json
        pins = json.loads(kit.PINS.read_text())
        self.assertEqual(pins["stock_raw"]["boot.img"]["bytes"], mk.PARTITION_BOOT)
        self.assertIn("boot.img.lz4", pins["stock_lz4"])
        self.assertIn("vendor_boot.img.lz4", pins["stock_lz4"])


if __name__ == "__main__":
    unittest.main()
