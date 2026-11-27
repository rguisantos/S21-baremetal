#!/usr/bin/env python3
"""Testes de vbmeta_disabled.py com vbmeta AVB sintético (layout da libavb)."""
import pathlib
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vbmeta_disabled as vd  # noqa: E402


def hash_desc(name):
    body = struct.pack(">Q32sIIII60s", 0x4000000, b"sha256", len(name), 0, 32, 0, b"") + name.encode()
    body += b"\0" * (-len(body) % 8)
    return struct.pack(">QQ", 2, len(body)) + body


def chain_desc(name):
    body = struct.pack(">IIII60s", 1, len(name), 8, 0, b"") + name.encode() + b"K" * 8
    body += b"\0" * (-len(body) % 8)
    return struct.pack(">QQ", 4, len(body)) + body


def vbmeta(flags=0, pad=4096):
    descs = hash_desc("dtbo") + chain_desc("boot") + chain_desc("vendor_boot")
    aux = descs + b"\0" * (-len(descs) % 64)
    auth = b"\0" * 576
    hdr = bytearray(256)
    hdr[0:4] = b"AVB0"
    struct.pack_into(">IIQQ", hdr, 4, 1, 0, len(auth), len(aux))
    struct.pack_into(">QQ", hdr, 96, 0, len(descs))
    struct.pack_into(">I", hdr, 120, flags)
    hdr[128:132] = b"avbt"
    img = bytes(hdr) + auth + aux
    return img + b"\0" * (pad - len(img))


class Vbmeta(unittest.TestCase):
    def test_disable_changes_only_flags(self):
        img = vbmeta()
        new, info = vd.disable(img)
        self.assertEqual(info["flags"], 0)
        self.assertEqual(struct.unpack_from(">I", new, 120)[0], 3)
        self.assertEqual([i for i, (a, b) in enumerate(zip(img, new)) if a != b], [123])
        self.assertEqual(len(new), len(img))
        self.assertEqual(info["descriptors"], [{"tag": "hash", "partition": "dtbo"},
                                               {"tag": "chain_partition", "partition": "boot"},
                                               {"tag": "chain_partition", "partition": "vendor_boot"}])

    def test_keeps_other_flag_bits_and_is_idempotent(self):
        new, info = vd.disable(vbmeta(flags=0x10))
        self.assertEqual(struct.unpack_from(">I", new, 120)[0], 0x13)
        again, _ = vd.disable(new)
        self.assertEqual(again, new)

    def test_refusals(self):
        with self.assertRaisesRegex(vd.VbmetaError, "AVB0"):
            vd.disable(b"\0" * 4096)
        img = bytearray(vbmeta())
        struct.pack_into(">Q", img, 20, 1 << 20)
        with self.assertRaisesRegex(vd.VbmetaError, "fora do arquivo"):
            vd.disable(bytes(img))
        img = bytearray(vbmeta())
        struct.pack_into(">I", img, 4, 2)
        with self.assertRaisesRegex(vd.VbmetaError, "versão"):
            vd.disable(bytes(img))

    def test_kit_files(self):
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t, "k")
            rep = vd.prepare(vbmeta(), out)
            self.assertEqual(rep["changed_bytes"], 1)
            with tarfile.open(out / "vbmeta_disabled.tar") as tf:
                self.assertEqual(tf.getnames(), ["vbmeta.img"])
                self.assertEqual(tf.extractfile("vbmeta.img").read(), (out / "vbmeta.img").read_bytes())
            self.assertTrue((out / "vbmeta_disabled.tar.md5").read_bytes().endswith(b"  vbmeta_disabled.tar\n"))
            r = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=out, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with self.assertRaisesRegex(vd.VbmetaError, "novo"):
                vd.prepare(vbmeta(), out)

    def test_lz4_input(self):
        import ctypes as c
        lib = c.CDLL("liblz4.so.1")                 # o mesmo que lz4_frame usa para descomprimir
        lib.LZ4F_compressFrameBound.restype = c.c_size_t
        lib.LZ4F_compressFrame.restype = c.c_size_t
        src = vbmeta()
        dst = c.create_string_buffer(lib.LZ4F_compressFrameBound(c.c_size_t(len(src)), None))
        n = lib.LZ4F_compressFrame(dst, c.c_size_t(len(dst)), src, c.c_size_t(len(src)), None)
        with tempfile.TemporaryDirectory() as t:
            packed, raw = pathlib.Path(t, "vbmeta.img.lz4"), pathlib.Path(t, "vbmeta.img")
            packed.write_bytes(dst.raw[:n])
            raw.write_bytes(src)
            pins = {"parent_lz4": {"bytes": n, "sha256": vd.sha(dst.raw[:n])},
                    "parent_raw": {"bytes": len(src), "sha256": vd.sha(src)}}
            self.assertEqual(vd.load(packed, pins), src)
            self.assertEqual(vd.load(raw, pins), src)
            other = vbmeta(flags=1)                       # outro vbmeta, estruturalmente válido: recusado
            raw.write_bytes(other)
            with self.assertRaisesRegex(vd.VbmetaError, "não é o vbmeta.img do BL HZC2"):
                vd.load(raw, pins)
            packed.write_bytes(dst.raw[:n] + b"x")
            with self.assertRaisesRegex(vd.VbmetaError, "vbmeta.img.lz4 do BL HZC2"):
                vd.load(packed, pins)
            with self.assertRaisesRegex(vd.VbmetaError, "BL HZC2 fixado"):   # pins reais: sintético recusado
                vd.load(raw)


if __name__ == "__main__":
    unittest.main()
