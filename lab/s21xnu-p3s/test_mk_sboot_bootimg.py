#!/usr/bin/env python3
"""Testes do montador de boot.img S-Boot para o shim s21xnu (entradas sintéticas)."""
import os
import struct
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import mk_sboot_bootimg as mk  # noqa: E402
from capture_a0_formats import layout  # noqa: E402


def stock_boot(kernel=b"K" * 5000, ramdisk=b"R" * 700, os_version=0x16000000):
    hdr = bytearray(mk.BOOT_V3_HEADER)
    hdr[:8] = b"ANDROID!"
    struct.pack_into("<4I", hdr, 8, len(kernel), len(ramdisk), os_version, mk.BOOT_V3_HEADER)
    struct.pack_into("<I", hdr, 40, 3)
    hdr[44:44 + 39] = b"androidboot.selinux=permissive loop.max"
    body = bytes(hdr) + b"\0" * (4096 - len(hdr))
    for blob in (kernel, ramdisk):
        body += blob + b"\0" * (-len(blob) % 4096)
    return body


def vendor_boot(ramdisk=b"V" * 1001, page=4096):
    hdr = bytearray(mk.VENDOR_V3_HEADER)
    hdr[:8] = b"VNDRBOOT"
    struct.pack_into("<5I", hdr, 8, 3, page, 0x80008000, 0x84000000, len(ramdisk))
    struct.pack_into("<II", hdr, 2096, mk.VENDOR_V3_HEADER, 0)
    body = bytes(hdr) + b"\0" * (-len(hdr) % page) + ramdisk
    return body + b"\0" * (-len(body) % page)


def shim_image(size=4096, image_size=None):
    img = bytearray(size)
    struct.pack_into("<I", img, 0, 0x14000010)            # b _start
    struct.pack_into("<QQQ", img, 8, 0, image_size or size + 0x9000, 0xA)
    img[56:60] = b"ARM\x64"
    return bytes(img)


def payload(phys_base=0x8C0000000, mem_size=0x80000000, segs=None, adt=b"A" * 64):
    virt = 0xFFFFFE0007004000
    segs = segs or [(virt, 0x8000, 0x1000)]
    hdr_end = mk.PAYLOAD_HDR + 32 * len(segs)
    data_off = (hdr_end + 0xFFF) & ~0xFFF
    blob = bytearray(data_off)
    table = []
    off = data_off
    for vm, vmsize, fsize in segs:
        table.append((vm, vmsize, off, fsize))
        blob += b"S" * fsize
        off += fsize
    adt_off = (len(blob) + 7) & ~7
    blob += b"\0" * (adt_off - len(blob)) + adt
    kernel_end = max(vm + vmsize for vm, vmsize, _ in segs)
    blob[:8] = mk.PAYLOAD_MAGIC
    struct.pack_into("<II", blob, 8, 1, len(segs))
    struct.pack_into("<7Q", blob, 0x10, virt, virt, adt_off, len(adt), kernel_end, phys_base, mem_size)
    for i, s in enumerate(table):
        struct.pack_into("<4Q", blob, mk.PAYLOAD_HDR + 32 * i, *s)
    return bytes(blob)


class ProbeTests(unittest.TestCase):
    def test_probe_image_layout_and_addresses(self):
        shim = shim_image()
        img, rep = mk.build(stock_boot(), vendor_boot(), shim)
        lay = layout(img)                               # parser independente do repo
        parts = {p["name"]: p for p in lay["parts"]}
        self.assertEqual(parts["kernel"]["bytes"], len(shim))
        self.assertEqual(img[parts["kernel"]["start"]:parts["kernel"]["end"]], shim)
        self.assertEqual(img[parts["ramdisk"]["start"]:parts["ramdisk"]["end"]], mk.PROBE_RAMDISK)
        self.assertEqual(rep["mode"], "probe")
        self.assertEqual(rep["initrd"], [hex(0x84080000), hex(0x84080000 + 1001 + len(mk.PROBE_RAMDISK))])
        self.assertEqual(rep["os_version"], hex(0x16000000))
        self.assertTrue(rep["cmdline"].startswith("androidboot.selinux=permissive"))
        # header stock preservado exceto os dois tamanhos
        stock = stock_boot()
        self.assertEqual(img[16:mk.BOOT_V3_HEADER], stock[16:mk.BOOT_V3_HEADER])

    def test_vendor_ramdisk_with_magic_is_refused(self):
        rd = b"x" * 3 + mk.PAYLOAD_MAGIC + b"y" * 100      # endereço 0x84080003: não alinhado
        mk.build(stock_boot(), vendor_boot(rd), shim_image())
        rd = b"x" * 4 + mk.PAYLOAD_MAGIC + b"y" * 100      # alinhado a 4: o shim pararia
        with self.assertRaisesRegex(mk.ContractError, "vendor ramdisk contém SWEETXNU"):
            mk.build(stock_boot(), vendor_boot(rd), shim_image())

    def test_kernel_reaching_ramdisk_destination_is_refused(self):
        too_big = 0x84080000 - 0x80080000 - 0x1F8000 + 0x1000
        with self.assertRaisesRegex(mk.ContractError, "KASLR"):
            mk.build(stock_boot(), vendor_boot(), shim_image(image_size=too_big))

    def test_bad_inputs_are_refused(self):
        with self.assertRaisesRegex(mk.ContractError, "ANDROID"):
            mk.build(b"\0" * 8192, vendor_boot(), shim_image())
        bad = bytearray(stock_boot())
        struct.pack_into("<I", bad, 40, 4)
        with self.assertRaisesRegex(mk.ContractError, "v3"):
            mk.build(bytes(bad), vendor_boot(), shim_image())
        with self.assertRaisesRegex(mk.ContractError, "ARM"):
            mk.build(stock_boot(), vendor_boot(), b"\0" * 4096)
        with self.assertRaisesRegex(mk.ContractError, "truncado"):
            mk.build(stock_boot(), vendor_boot()[:4096], shim_image())

    def test_partition_limit(self):
        with self.assertRaisesRegex(mk.ContractError, "excede a partição"):
            mk.build(stock_boot(), vendor_boot(), shim_image(), partition=8192)

    def test_initrd_past_lk_fdt_is_refused(self):
        with mock.patch.object(mk, "FDT_X0", 0x84080000 + 1001 + 8):
            with self.assertRaisesRegex(mk.ContractError, "depois do FDT"):
                mk.build(stock_boot(), vendor_boot(), shim_image())


class PayloadTests(unittest.TestCase):
    def test_payload_is_8_aligned_after_odd_vendor_ramdisk(self):
        for vsize in (1001, 1002, 1004, 1008, 12017257):
            img, rep = mk.build(stock_boot(), vendor_boot(b"V" * vsize), shim_image(), payload())
            pa = int(rep["payload_pa"], 16)
            self.assertEqual(pa % 8, 0, vsize)
            self.assertEqual(pa, 0x84080000 + vsize + rep["ramdisk_pad"])
            self.assertLess(rep["ramdisk_pad"], 8)
            # o shim (loader.c) varre de 4 em 4 a partir de initrd-start: acha o header ali
            lay = {p["name"]: p for p in layout(img)["parts"]}
            rd = img[lay["ramdisk"]["start"]:lay["ramdisk"]["end"]]
            self.assertEqual(rd[rep["ramdisk_pad"]:][:8], mk.PAYLOAD_MAGIC)
        self.assertEqual(mk.build(stock_boot(), vendor_boot(b"V" * 12017257), shim_image(),
                                  payload())[1]["ramdisk_pad"], 7)   # HZC2 stock

    def test_payload_window_rules(self):
        with self.assertRaisesRegex(mk.ContractError, "sobrepõe o initrd"):
            mk.build(stock_boot(), vendor_boot(), shim_image(), payload(phys_base=0x84000000))
        with self.assertRaisesRegex(mk.ContractError, "reserva LK el2_code"):
            mk.build(stock_boot(), vendor_boot(), shim_image(), payload(phys_base=0xC1400000))
        with self.assertRaisesRegex(mk.ContractError, "FDT do LK"):
            mk.build(stock_boot(), vendor_boot(), shim_image(), payload(phys_base=0x8B07C000))
        with self.assertRaisesRegex(mk.ContractError, "fora da janela"):
            mk.build(stock_boot(), vendor_boot(), shim_image(), payload(mem_size=0x4000))

    def test_payload_header_validation(self):
        p = bytearray(payload())
        struct.pack_into("<I", p, 8, 2)
        with self.assertRaisesRegex(mk.ContractError, "versão 2"):
            mk.build(stock_boot(), vendor_boot(), shim_image(), bytes(p))
        with self.assertRaisesRegex(mk.ContractError, "SWEETXNU"):
            mk.build(stock_boot(), vendor_boot(), shim_image(), b"\0" * 0x400)
        p = bytearray(payload())
        struct.pack_into("<Q", p, mk.PAYLOAD_HDR + 16, len(p))      # file_off fora do arquivo
        with self.assertRaisesRegex(mk.ContractError, "segmento 0"):
            mk.build(stock_boot(), vendor_boot(), shim_image(), bytes(p))


class CliTests(unittest.TestCase):
    def test_cli_refusal_exit_code(self):
        import tempfile, pathlib, contextlib, io
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "b").write_bytes(stock_boot())
            (d / "v").write_bytes(vendor_boot(b"xxxx" + mk.PAYLOAD_MAGIC))
            (d / "s").write_bytes(shim_image())
            args = ["--stock-boot", str(d / "b"), "--vendor-boot", str(d / "v"),
                    "--shim", str(d / "s"), "--out", str(d / "o")]
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(mk.main(args), 2)
            self.assertIn("RECUSADO", err.getvalue())
            self.assertFalse((d / "o").exists())
            (d / "v").write_bytes(vendor_boot())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mk.main(args + ["--json", str(d / "r.json")]), 0)
            self.assertTrue((d / "o").exists() and (d / "r.json").exists())


if __name__ == "__main__":
    unittest.main()
