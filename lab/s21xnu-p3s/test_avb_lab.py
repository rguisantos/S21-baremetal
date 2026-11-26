#!/usr/bin/env python3
"""Controles com RSA real (openssl) para o transplante AVB de laboratório."""
import contextlib
import hashlib
import io
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
import avb_lab  # noqa: E402
import mk_sboot_bootimg as mk  # noqa: E402
import capture_a0_container as pack  # noqa: E402
import capture_a0_formats as fmt  # noqa: E402
from test_mk_sboot_bootimg import shim_image, stock_boot, vendor_boot  # noqa: E402

PARTITION = 1 << 20


class AvbLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        root = pathlib.Path(cls.tmp.name)
        openssl = shutil.which("openssl")
        if openssl is None:
            raise RuntimeError("openssl é necessário")
        cls.pems, cls.keys = [], []
        for i in range(2):
            pem = root / ("k%d.pem" % i)
            subprocess.run([openssl, "genrsa", "-out", str(pem), "4096"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            cls.pems.append(pem)
            cls.keys.append(avb_lab.openssl_lab_key(pem))
        cls.stock = cls.fixture(stock_boot(kernel=b"K" * 300000, ramdisk=b"R" * 90000))
        cls.root = root

    @classmethod
    def fixture(cls, body):
        """boot.img stock sintético: corpo + extensão opaca + vbmeta assinado (chave 0) + AVBf."""
        prefix = body + b"SignerVer03-synthetic-opaque"
        salt, name = b"fixed-salt", b"boot"
        wanted = hashlib.sha256(salt + prefix).digest()
        desc = bytearray(fmt.align(132 + len(name) + len(salt) + 32, 8))
        struct.pack_into(">3Q", desc, 0, 2, len(desc) - 16, len(prefix))
        desc[24:30] = b"sha256"
        struct.pack_into(">4I", desc, 56, len(name), len(salt), 32, 0)
        desc[132:132 + len(name + salt + wanted)] = name + salt + wanted
        auth, aux = 576, fmt.align(len(desc) + 1032, 64)
        header = bytearray(256)
        header[:4] = b"AVB0"
        struct.pack_into(">IIQQI", header, 4, 1, 0, auth, aux, 2)
        struct.pack_into(">10Q", header, 32, 0, 32, 32, 512, len(desc), 1032, len(desc) + 1032, 0, 0, len(desc))
        header[128:138] = b"test-only\0"
        auxiliary = bytes(desc) + cls.keys[0][0] + b"\0" * (aux - len(desc) - 1032)
        signed = bytes(header) + auxiliary
        meta = bytes(header) + hashlib.sha256(signed).digest() + cls.keys[0][1](signed) + b"\0" * 32 + auxiliary
        offset = fmt.align(len(prefix), 4096)
        data = bytearray(PARTITION)
        data[:len(prefix)] = prefix
        data[offset:offset + len(meta)] = meta
        struct.pack_into(">4sIIQQQ", data, len(data) - 64, b"AVBf", 1, 0, len(prefix), offset, len(meta))
        return bytes(data)

    def body(self, payload=None):
        return mk.build(self.stock, vendor_boot(), shim_image(), payload)[0]

    def test_stock_fixture_is_a_valid_template(self):
        p = pack.template(self.stock)
        self.assertEqual(p["key"], self.keys[0][0])

    def test_transplant_hashes_and_signature(self):
        body = self.body()
        out = avb_lab.transplant(self.stock, body, *self.keys[1])
        self.assertEqual(len(out), len(self.stock))
        self.assertEqual(out[:len(body)], body)
        av = fmt.layout(out)["avb"]
        self.assertTrue(av["all_hashes_match"])
        self.assertEqual(av["original_image_size"], len(body))
        self.assertEqual(av["offset"], fmt.align(len(body), 4096))
        q = pack.describe(out)
        self.assertTrue(pack.signature_valid(q))
        self.assertEqual(q["key"], self.keys[1][0])
        self.assertFalse(any(out[len(body):av["offset"]]))
        # cabeçalho AVB do stock preservado; só digest, tamanho, chave e autenticação mudam
        self.assertEqual(q["meta"][:256], pack.describe(self.stock)["meta"][:256])

    def test_deterministic_for_same_key(self):
        body = self.body()
        self.assertEqual(avb_lab.transplant(self.stock, body, *self.keys[1]),
                         avb_lab.transplant(self.stock, body, *self.keys[1]))

    def test_tampering_breaks_hash(self):
        body = self.body()
        out = bytearray(avb_lab.transplant(self.stock, body, *self.keys[1]))
        out[5000] ^= 1
        self.assertFalse(fmt.layout(bytes(out))["avb"]["all_hashes_match"])

    def test_refusals(self):
        body = self.body()
        with self.assertRaisesRegex(ValueError, "igual à chave do stock"):
            avb_lab.transplant(self.stock, body, *self.keys[0])
        with self.assertRaisesRegex(ValueError, "não cabem"):
            big = mk.build(self.stock, vendor_boot(), shim_image(size=PARTITION), None, partition=4 << 20)[0]
            avb_lab.transplant(self.stock, big, *self.keys[1])
        with self.assertRaises(ValueError):
            avb_lab.transplant(self.stock, b"\0" * 8192, *self.keys[1])
        with self.assertRaisesRegex(ValueError, "assinatura"):
            avb_lab.transplant(self.stock, body, self.keys[1][0], lambda d: b"\0" * 511)
        with self.assertRaisesRegex(ValueError, "falhou"):
            avb_lab.transplant(self.stock, body, self.keys[1][0], self.keys[0][1])   # assina com outra chave
        bad = bytearray(self.stock)
        bad[100] ^= 1
        with self.assertRaises(ValueError):
            avb_lab.transplant(bytes(bad), body, *self.keys[1])

    def test_cli_with_lab_key(self):
        d = self.root / "cli"
        d.mkdir(exist_ok=True)
        (d / "b").write_bytes(self.stock)
        (d / "v").write_bytes(vendor_boot())
        (d / "s").write_bytes(shim_image())
        args = ["--stock-boot", str(d / "b"), "--vendor-boot", str(d / "v"), "--shim", str(d / "s"),
                "--avb-lab-key", str(self.pems[1]), "--out", str(d / "o")]
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(mk.main(args), 2)          # stock com tamanho diferente da partição BOOT
        self.assertIn("partição BOOT", err.getvalue())
        with mock.patch.object(mk, "PARTITION_BOOT", PARTITION), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mk.main(args), 0)
        out = (d / "o").read_bytes()
        self.assertEqual(len(out), PARTITION)
        self.assertTrue(pack.signature_valid(pack.describe(out)))
        self.assertTrue(fmt.layout(out)["avb"]["all_hashes_match"])


if __name__ == "__main__":
    unittest.main()
