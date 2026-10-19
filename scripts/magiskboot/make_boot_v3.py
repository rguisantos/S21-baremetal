#!/usr/bin/env python3
"""
make_boot_v3.py — sintetiza um boot.img header v3 (formato S21/GKI,
Android 11) com o payload comprimido em LZ4 como "kernel", para exercitar
o fluxo magiskboot unpack/repack ANTES de pôr a mão no firmware real.

Layout v3 (sem campos de endereço! o load address mora dentro do ABL):
  offset  0: magic "ANDROID!"
  offset  8: kernel_size (u32 LE)
  offset 12: ramdisk_size (u32 LE)
  offset 16: os_version (u32 LE)
  offset 20: header_size = 1580 (u32 LE)
  offset 24: reserved[4]
  offset 40: header_version = 3 (u32 LE)
  offset 44: cmdline (1536 bytes)
  offset 1580..4095: padding — o header v3 ocupa a PRIMEIRA página inteira
  offset 4096: kernel (comprimido), pad p/ 4096; então ramdisk
"""

import struct
import sys

from lz4.frame import compress as lz4_compress

PAGE = 4096


def pad(data: bytes, page: int = PAGE) -> bytes:
    r = len(data) % page
    return data + b"\x00" * ((page - r) % page)


def build(kernel_raw: bytes, ramdisk: bytes = b"") -> bytes:
    kernel_lz4 = lz4_compress(kernel_raw)

    hdr = b"ANDROID!"
    hdr += struct.pack("<II", len(kernel_lz4), len(ramdisk))
    hdr += struct.pack("<I", 0)            # os_version
    hdr += struct.pack("<I", 1580)         # header_size (v3)
    hdr += struct.pack("<4I", 0, 0, 0, 0)  # reserved[4]
    hdr += struct.pack("<I", 3)            # header_version
    hdr += b"\x00".ljust(1536, b"\x00")    # cmdline
    assert len(hdr) == 1580, len(hdr)

    # o header ocupa a 1a página INTEIRA — kernel começa em 4096, não em 1580
    return pad(hdr) + pad(kernel_lz4) + pad(ramdisk)


if __name__ == "__main__":
    a = sys.argv[1:]
    payload = open(a[0], "rb").read()
    ramdisk = open(a[1], "rb").read() if len(a) > 2 else b""
    out = a[3] if len(a) > 3 else a[2] if len(a) > 2 else "boot.img"
    blob = build(payload, ramdisk)
    with open(out, "wb") as f:
        f.write(blob)
    print(f"{out}: {len(blob)} bytes | kernel lz4: {len(lz4_compress(payload))} "
          f"de {len(payload)} bytes crus")
