#!/usr/bin/env python3
"""Testes do kit do segundo boot (XNU) com kernel Mach-O e firmware sintéticos.

Os testes de ponta a ponta (shim + mkadt + mkpayload reais) rodam quando
S21XNU aponta para o clone fixado do s21xnu (no CI); os demais rodam sempre.
"""
import os
import pathlib
import struct
import sys
import tarfile
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
import prepare_xnu_boot as xb  # noqa: E402
import mk_sboot_bootimg as mk  # noqa: E402
import capture_a0_container as pack  # noqa: E402
import capture_a0_formats as fmt  # noqa: E402
import test_avb_lab  # noqa: E402
from test_mk_sboot_bootimg import vendor_boot  # noqa: E402

S21XNU = os.environ.get("S21XNU")


def fake_kernel(marks=tuple(xb.KERNEL_MARKS.values()), size=0x40000):
    """Mach-O arm64 mínimo: __TEXT com todo o arquivo e LC_UNIXTHREAD com o pc."""
    vm = 0xFFFFFFF007004000
    seg = struct.pack("<II16s4Q4I", 0x19, 72, b"__TEXT", vm, size, 0, size, 5, 5, 0, 0)
    thread = struct.pack("<IIII", 0x5, 16 + 68 * 4, 6, 68) + b"\0" * (32 * 8) + struct.pack("<Q", vm + 0x1000) \
        + b"\0" * 8
    hdr = struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2, 2, len(seg) + len(thread), 0, 0)
    body = bytearray(hdr + seg + thread)
    body += b"\0" * (0x1000 - len(body))
    for m in marks:
        body += m + b"\0"
    body += b"\0" * (size - len(body))
    return bytes(body)


FILEFRAG = """Filesystem type is: f2f52010
File size of /data/iosroot.img is 33554432 (8192 blocks of 4096 bytes)
 ext:     logical_offset:        physical_offset: length:   expected: flags:
   0:        0..    4095:     100000..    104095:   4096:
   1:     4096..    8191:     200000..    204095:   4096:     104096: last,eof
/data/iosroot.img: 2 extents found
"""


class Rules(unittest.TestCase):
    def test_kernel_marks(self):
        xb.check_kernel(fake_kernel())
        with self.assertRaisesRegex(xb.kit.KitError, "falta 0150 BAR2 primeiro"):
            xb.check_kernel(fake_kernel(marks=tuple(m for k, m in xb.KERNEL_MARKS.items() if k != "0150 BAR2 primeiro")))
        with self.assertRaisesRegex(xb.kit.KitError, "não é Mach-O"):
            xb.check_kernel(b"\x7fELF" + fake_kernel()[4:])

    def test_cmdline(self):
        self.assertEqual(xb.cmdline(1, 0, False), xb.BASE_ARGS + " cpus=1")
        c = xb.cmdline(8, 4, True)
        self.assertTrue(c.endswith("cpus=8 " + xb.ROOT_ARGS + " sweetwifi=4"))
        self.assertIn("ufsov=1", c)
        self.assertNotIn("ufsrw", c)
        self.assertNotIn("ufshs", c)
        self.assertLess(len(c.encode()), 607)
        self.assertIn("sweetwifi=3", xb.cmdline(1, 3, False))
        with self.assertRaisesRegex(xb.kit.KitError, "precisa da raiz"):
            xb.cmdline(1, 4, False)
        with self.assertRaisesRegex(xb.kit.KitError, "--cpus"):
            xb.cmdline(9, 0, False)
        with self.assertRaisesRegex(xb.kit.KitError, "--sweetwifi"):
            xb.cmdline(1, 5, True)

    def test_identify_kernel(self):
        k = fake_kernel()
        with tempfile.TemporaryDirectory() as t:
            table = pathlib.Path(t, "k.json")
            table.write_text('{"kernels": {"%s": {"fork_commit": "abc1234", "run_id": 1, "patches_up_to": "0151"}}}'
                             % xb.kit.sha(k))
            self.assertEqual(xb.identify_kernel(k, table)["patches_up_to"], "0151")
            self.assertFalse(xb.identify_kernel(k + b"x", table)["known"])
        self.assertIn("0151", xb.identify_kernel(k)["note"])          # tabela real: sintético não está nela

    def test_series_is_complete(self):
        self.assertEqual([p.name[:4] for p in xb.FORK_SERIES], ["0001", "0002", "0003", "0004", "0005", "0006", "0007"])


@unittest.skipUnless(S21XNU, "S21XNU (clone fixado do s21xnu) não definido")
class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        avb = test_avb_lab.AvbLabTests
        avb.setUpClass()
        cls.addClassCleanup(avb.doClassCleanups)
        cls.stock, cls.pem = avb.stock, avb.pems[1]
        cls.vendor = vendor_boot(b"V" * 12017257)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = pathlib.Path(cls.tmp.name)
        (cls.root / "kernel").write_bytes(fake_kernel())
        (cls.root / "ff.txt").write_text(FILEFRAG)
        cls.shim, cls.payload, cls.kernel, cls.extra = xb.build_inputs(
            S21XNU, cls.root / "kernel", cls.root / "ff.txt", 1, 4, cls.root / "work")

    def test_payload_and_kit(self):
        p = mk.parse_payload(self.payload)
        self.assertEqual(self.extra["ufs_extents"], 2)
        self.assertTrue(self.extra["root"])
        self.assertIn(b"sweetwifi=4", self.payload)
        self.assertIn(b"touch_panel_w=1440", self.payload)
        self.assertGreater(p["kernel_end"], 0)
        out = self.root / "kit"
        rep = xb.prepare(self.stock, self.vendor, self.shim, self.payload, self.kernel, self.pem, out, self.extra)
        boot = (out / "boot.img").read_bytes()
        self.assertEqual(len(boot), len(self.stock))
        self.assertEqual(rep["bootimg"]["mode"], "payload")
        self.assertTrue(fmt.layout(boot)["avb"]["all_hashes_match"])
        self.assertTrue(pack.signature_valid(pack.describe(boot)))
        with tarfile.open(out / "AP_s21xnu_xnu.tar") as tf:
            self.assertEqual(tf.extractfile("boot.img").read(), boot)
        self.assertTrue((out / "AP_s21xnu_xnu.tar.md5").read_bytes().endswith(b"  AP_s21xnu_xnu.tar\n"))
        r = (out / "ROTEIRO-XNU.md").read_text()
        self.assertIn(rep["bootimg"]["sha256"], r)
        self.assertIn("2 extents", r)
        self.assertIn("W4 PASS", r)
        self.assertIn("fora da tabela", r)
        i = r.index("to-android --no-reboot")
        self.assertLess(i, r.index("install boot.img"))
        self.assertLess(r.index("install boot.img"), r.index("switch.sh to-xnu"))
        self.assertEqual(sorted(l.split()[1] for l in (out / "SHA256SUMS").read_text().splitlines()),
                         sorted(["AP_s21xnu_xnu.tar", "AP_s21xnu_xnu.tar.md5", "ROTEIRO-XNU.md", "boot.img",
                                 "relatorio.json", "s21xnu-switch.sh"]))

    def test_shim_is_p3s(self):
        self.assertEqual(self.shim[0x38:0x3c], b"ARMd")


if __name__ == "__main__":
    unittest.main()
