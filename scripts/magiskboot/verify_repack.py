#!/usr/bin/env python3
"""verify_repack.py — inspeção forense do round-trip magiskboot:
onde o payload realmente vive em cada imagem, o que diz o header,
e o que exatamente foi armazenado como kernel."""
import struct

P = "/home/z/my-project/download/exynos-baremetal-qemu/payload.bin"
payload = open(P, "rb").read()
print("payload: len=%d  primeiros 12 bytes: %s" % (len(payload), payload[:12].hex()))

for f in ("boot.img", "custom_boot.img"):
    d = open("/home/z/my-project/scripts/magiskboot/" + f, "rb").read()
    ks, rs = struct.unpack("<II", d[8:16])
    hs = struct.unpack("<I", d[20:24])[0]
    hv = struct.unpack("<I", d[40:44])[0]
    print("\n%s: arquivo=%d kernel_size=%d ramdisk_size=%d header_size=%d versao=%d"
          % (f, len(d), ks, rs, hs, hv))
    print("   @1580..1595 : %s" % d[1580:1596].hex())
    print("   payload[0:8] em offset : %d" % d.find(payload[:8]))
    print("   payload[-8:] em offset : %d" % d.find(payload[-8:]))
    if d.find(payload[:4]) >= 0:
        print("   -> o kernel CRU esta armazenado (comeca em %d)" % d.find(payload[:4]))
