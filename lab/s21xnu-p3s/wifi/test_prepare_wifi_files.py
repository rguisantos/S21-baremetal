#!/usr/bin/env python3
"""Testes de prepare_wifi_files.py com arquivos sintéticos (nenhum firmware real)."""
import hashlib
import pathlib
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import prepare_wifi_files as pw  # noqa: E402


def fake_fw(ram=None, size=0x1000):
    fw = bytearray(size)
    fw[0:4] = struct.pack("<I", 0xEA00002E)
    if ram is not None:
        fw[0x6C:0x74] = struct.pack("<II", pw.RAMSIZE_MAGIC, ram)
    fw[0x200:0x200 + 22] = b"20.80.87.4 01-3fe70789"
    return bytes(fw)


def setup(d, fw, nv=b"boardrev=0x1\nkey=1\n", clm=b"CLM"):
    d = pathlib.Path(d)
    (d / "bcmdhd_sta.bin_c1").write_bytes(fw)
    (d / "nvram.txt_ES40_semco_c1").write_bytes(nv)
    (d / "bcmdhd_clm.blob").write_bytes(clm)
    return {"bcmdhd_sta.bin_c1": ("bcm4389-sta.bin", hashlib.sha256(fw).hexdigest()),
            "nvram.txt_ES40_semco_c1": ("bcm4389-nvram-semco.txt", hashlib.sha256(nv).hexdigest()),
            "bcmdhd_clm.blob": ("bcm4389-clm.blob", hashlib.sha256(clm).hexdigest())}


class Prepare(unittest.TestCase):
    def test_copies_and_names(self):
        with tempfile.TemporaryDirectory() as t:
            src, out = pathlib.Path(t, "src"), pathlib.Path(t, "out")
            src.mkdir()
            pins = setup(src, fake_fw(ram=0x1C0000))
            r = pw.prepare(src, out, pins)
            self.assertEqual(sorted(p.name for p in out.iterdir()),
                             ["LEIAME.txt", "SHA256SUMS", "bcm4389-clm.blob", "bcm4389-nvram-semco.txt",
                              "bcm4389-sta.bin"])
            for name, (target, want) in pins.items():
                self.assertEqual(hashlib.sha256((out / target).read_bytes()).hexdigest(), want)
                self.assertIn("%s  %s" % (want, target), (out / "SHA256SUMS").read_text())
            f = r["firmware"]
            self.assertEqual(f["reset_vector"], "0xea00002e")
            self.assertEqual(f["ram_declared"], "0x1c0000")
            self.assertEqual(f["ram_end"], "0x3c0000")
            self.assertFalse(f["bar2_remap_needed"])
            self.assertEqual(f["markers"], {"20.80.87.4": True, "01-3fe70789": True})

    def test_big_ram_needs_remap(self):
        with tempfile.TemporaryDirectory() as t:
            src = pathlib.Path(t, "src")
            src.mkdir()
            r = pw.prepare(src, pathlib.Path(t, "o"), setup(src, fake_fw(ram=0x2C0000)))
            self.assertTrue(r["firmware"]["bar2_remap_needed"])
            self.assertEqual(r["firmware"]["ram_end"], "0x4c0000")

    def test_no_smar(self):
        with tempfile.TemporaryDirectory() as t:
            src = pathlib.Path(t, "src")
            src.mkdir()
            r = pw.prepare(src, pathlib.Path(t, "o"), setup(src, fake_fw()))
            self.assertIsNone(r["firmware"]["ram_declared"])
            self.assertNotIn("ram_end", r["firmware"])

    def test_wrong_hash_refused(self):
        with tempfile.TemporaryDirectory() as t:
            src = pathlib.Path(t, "src")
            src.mkdir()
            pins = setup(src, fake_fw())
            (src / "bcmdhd_clm.blob").write_bytes(b"other")
            with self.assertRaisesRegex(pw.WifiError, "bcmdhd_clm.blob: SHA-256"):
                pw.prepare(src, pathlib.Path(t, "o"), pins)
            self.assertFalse(pathlib.Path(t, "o").exists())

    def test_missing_refused(self):
        with tempfile.TemporaryDirectory() as t:
            src = pathlib.Path(t, "src")
            src.mkdir()
            pins = setup(src, fake_fw())
            (src / "nvram.txt_ES40_semco_c1").unlink()
            with self.assertRaisesRegex(pw.WifiError, "falta nvram.txt_ES40_semco_c1"):
                pw.prepare(src, pathlib.Path(t, "o"), pins)

    def test_fw_bigger_than_declared_ram(self):
        with tempfile.TemporaryDirectory() as t:
            src = pathlib.Path(t, "src")
            src.mkdir()
            with self.assertRaisesRegex(pw.WifiError, "não cabe na RAM"):
                pw.prepare(src, pathlib.Path(t, "o"), setup(src, fake_fw(ram=0x800, size=0x1000)))

    def test_nonempty_out_refused(self):
        with tempfile.TemporaryDirectory() as t:
            src, out = pathlib.Path(t, "src"), pathlib.Path(t, "o")
            src.mkdir()
            out.mkdir()
            (out / "x").write_text("x")
            with self.assertRaisesRegex(pw.WifiError, "não está vazio"):
                pw.prepare(src, out, setup(src, fake_fw()))

    def test_real_pins_are_the_documented_ones(self):
        doc = (pathlib.Path(__file__).resolve().parents[3] / "docs" / "s21xnu-wifi-bcm4389-hzc2.md").read_text()
        for name, (target, want) in pw.FILES.items():
            self.assertRegex(doc, r"\| %s \| \d+ \| %s \|" % (name.replace(".", r"\."), want))


if __name__ == "__main__":
    unittest.main()
