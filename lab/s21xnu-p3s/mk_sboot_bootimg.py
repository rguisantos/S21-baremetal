#!/usr/bin/env python3
"""Monta um boot.img v3 que o S-Boot HZC2 carrega com o shim do s21xnu.

O shim entra como kernel; o ramdisk de boot leva o payload SWEETXNU (ou só
um marcador, no modo sonda). Nada é gravado no aparelho por este script.

  mk_sboot_bootimg.py --stock-boot boot.img --vendor-boot vendor_boot.img \
      --shim Image [--payload payload.bin] --out boot-s21xnu.img [--json r.json]

Sem --payload gera a sonda: o shim não acha SWEETXNU, mostra o motivo na
tela e segue para o diagnóstico (MMU, PSCI, GIC) e PSCI SYSTEM_RESET.

Modelo do LK HZC2 usado nas verificações (docs/lk-v3-layout.md,
docs/lk-dynamic-fdt.md, docs/bootloader-hzc2.md, docs/lk-cache-handoff.md):
  kernel  -> 0x80080000 + KASLR, KASLR em 0..0x1f8000 passo 0x8000
  vendor ramdisk -> 0x84080000; ramdisk de boot logo após, sem padding
  /chosen linux,initrd-start/end = 0x84080000 / +vendor+boot (células u32)
  X0 (FDT) = 0x8b080000; contêiner boot staging em 0x94000000
É análise estática: o percurso real no telefone não foi observado.
"""
import argparse
import hashlib
import json
import pathlib
import struct
import sys

PAGE = 4096
BOOT_V3_HEADER = 1580
VENDOR_V3_HEADER = 2112
PARTITION_BOOT = 64 * 1024 * 1024          # PIT HZC2: BOOT 16384 blocos de 4 KiB

KERNEL_BASE = 0x80080000
KASLR_MAX, KASLR_STEP = 0x1F8000, 0x8000
INITRD_BASE = 0x84080000
FDT_X0 = 0x8B080000
STAGING_BOOT = 0x94000000
# Reservas fixas escritas pelo LK abaixo de 4 GiB (docs/lk-dynamic-fdt.md) e o
# framebuffer; o payload XNU não pode cair sobre elas.
LK_FIXED = {
    "kaslr": (0x80001000, 0x1000),
    "el2_code(uH)": (0xC1400000, 0x200000),
    "sboot": (0xE8000000, 0x1800000),
    "bootloader_fb": (0xFA000000, 0x1194000),
    "mz_zeroisation": (0xFB400000, 0x1000),
}
PAYLOAD_MAGIC = b"SWEETXNU"
PAYLOAD_HDR = 0x2A8
PROBE_RAMDISK = b"S21-BAREMETAL-SHIM-PROBE\0\0\0\0\0\0\0\0"


class ContractError(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise ContractError(msg)


def align(n, a):
    return (n + a - 1) & ~(a - 1)


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def parse_boot_v3(data):
    need(data[:8] == b"ANDROID!", "boot: magic ANDROID! ausente")
    need(len(data) >= PAGE, "boot: menor que uma página")
    kernel, ramdisk, os_version, hs = struct.unpack_from("<4I", data, 8)
    version, = struct.unpack_from("<I", data, 40)
    need(version == 3 and hs == BOOT_V3_HEADER, "boot: só header v3 (1580 bytes) é suportado")
    need(not any(data[24:40]), "boot: campos reservados não nulos")
    return {"kernel_size": kernel, "ramdisk_size": ramdisk, "os_version": os_version,
            "cmdline": data[44:44 + 1536]}


def parse_vendor_v3(data):
    need(data[:8] == b"VNDRBOOT", "vendor_boot: magic VNDRBOOT ausente")
    need(len(data) >= VENDOR_V3_HEADER, "vendor_boot: header curto")
    version, page, _kaddr, _raddr, vr_size = struct.unpack_from("<5I", data, 8)
    hs, = struct.unpack_from("<I", data, 2096)
    need(version == 3 and hs == VENDOR_V3_HEADER, "vendor_boot: só header v3 é suportado")
    need(page in (2048, 4096, 8192, 16384), "vendor_boot: page_size inválido")
    start = align(hs, page)
    need(start + vr_size <= len(data), "vendor_boot: ramdisk truncado")
    return {"page_size": page, "vendor_ramdisk_size": vr_size,
            "vendor_ramdisk": data[start:start + vr_size]}


def parse_image(data):
    need(len(data) >= 64, "Image: menor que o header arm64")
    text_offset, image_size, flags = struct.unpack_from("<QQQ", data, 8)
    need(data[56:60] == b"ARM\x64", "Image: magic ARM\\x64 ausente")
    need(image_size >= len(data), "Image: image_size menor que o arquivo")
    need(flags & 1 == 0, "Image: big-endian")
    return {"text_offset": text_offset, "image_size": image_size, "flags": flags}


def parse_payload(data):
    need(len(data) >= PAYLOAD_HDR and data[:8] == PAYLOAD_MAGIC, "payload: magic SWEETXNU ausente")
    version, nsegs = struct.unpack_from("<II", data, 8)
    virt_base, entry_va, adt_off, adt_size, kernel_end, phys_base, mem_size = \
        struct.unpack_from("<7Q", data, 0x10)
    need(version == 1, "payload: versão %d (esperado 1)" % version)
    need(0 < nsegs <= 64, "payload: nsegs fora de 1..64")
    need(PAYLOAD_HDR + nsegs * 32 <= len(data), "payload: tabela de segmentos truncada")
    need(adt_off % 8 == 0 and adt_off + adt_size <= len(data), "payload: ADT fora do arquivo/desalinhado")
    need(virt_base <= kernel_end and phys_base % 0x4000 == 0 and mem_size, "payload: base/tamanho inválidos")
    segs = []
    for i in range(nsegs):
        vm, vmsize, off, fsize = struct.unpack_from("<4Q", data, PAYLOAD_HDR + 32 * i)
        need(off + fsize <= len(data) and fsize <= vmsize, "payload: segmento %d fora do arquivo" % i)
        segs.append((vm, vmsize, off, fsize))
    return {"virt_base": virt_base, "entry_va": entry_va, "adt_size": adt_size,
            "kernel_end": kernel_end, "phys_base": phys_base, "mem_size": mem_size, "segs": segs}


def check_payload_memory(p, initrd):
    """Regiões que o shim escreve ao carregar o XNU, contra o mapa do LK."""
    delta = p["phys_base"] - p["virt_base"]
    window = (p["phys_base"], p["phys_base"] + p["mem_size"])
    writes = [(vm + delta, vm + delta + vmsize) for vm, vmsize, _, _ in p["segs"]]
    adt_pa = p["kernel_end"] + delta
    ba = align(adt_pa + p["adt_size"], 0x4000)
    writes.append((adt_pa, ba + 0x4000))            # ADT + boot_args (shim loader.c)
    need(not overlaps(window, initrd), "payload: janela de RAM do XNU sobrepõe o initrd (shim recusa)")
    for lo, hi in writes:
        need(window[0] <= lo and hi <= window[1], "payload: escrita %#x-%#x fora da janela XNU" % (lo, hi))
        need(not overlaps((lo, hi), initrd), "payload: escrita %#x sobre o initrd" % lo)
        need(not overlaps((lo, hi), (FDT_X0, FDT_X0 + 0x200000)), "payload: escrita sobre o FDT do LK")
        for name, (b, s) in LK_FIXED.items():
            need(not overlaps((lo, hi), (b, b + s)), "payload: escrita sobre reserva LK %s" % name)
    return {"window": [hex(x) for x in window], "writes": [[hex(a), hex(b)] for a, b in writes]}


def first_magic(blob, base, start, end):
    """Primeira ocorrência que o scan do shim veria (endereços múltiplos de 4)."""
    i = blob.find(PAYLOAD_MAGIC[:4])
    while i != -1:
        addr = base + i
        if start <= addr and addr + 8 <= end and addr % 4 == 0 and blob[i:i + 8] == PAYLOAD_MAGIC:
            return addr
        i = blob.find(PAYLOAD_MAGIC[:4], i + 1)
    return None


def build(stock_boot, vendor_boot, shim, payload=None, partition=PARTITION_BOOT):
    sb, vb, im = parse_boot_v3(stock_boot), parse_vendor_v3(vendor_boot), parse_image(shim)
    V = vb["vendor_ramdisk_size"]
    report = {"mode": "payload" if payload is not None else "probe",
              "vendor_ramdisk_size": V, "shim": im}

    # Kernel: todo deslocamento KASLR precisa caber antes do ramdisk vendor.
    k_hi = KERNEL_BASE + KASLR_MAX + im["image_size"]
    need(k_hi <= INITRD_BASE, "shim: image_size+KASLR alcança o destino do ramdisk (%#x)" % k_hi)
    report["kernel_range"] = [hex(KERNEL_BASE), hex(k_hi)]

    # Ramdisk de boot: padding para o header SWEETXNU cair alinhado a 8.
    if payload is not None:
        p = parse_payload(payload)
        pad = (-(INITRD_BASE + V)) % 8
        ramdisk = b"\0" * pad + payload
        payload_pa = INITRD_BASE + V + pad
    else:
        p, pad, payload_pa = None, 0, None
        ramdisk = PROBE_RAMDISK
    R = len(ramdisk)
    need(V + R < 1 << 32, "initrd: soma excede 32 bits (LK usa registradores W)")
    initrd = (INITRD_BASE, INITRD_BASE + V + R)
    need(initrd[1] <= FDT_X0, "initrd termina em %#x, depois do FDT do LK %#x" % (initrd[1], FDT_X0))
    need(initrd[1] <= STAGING_BOOT, "initrd alcança o staging do contêiner")
    report.update(initrd=[hex(x) for x in initrd], ramdisk_pad=pad, ramdisk_size=R)

    # O scan do shim começa em initrd-start e para no primeiro SWEETXNU.
    seen = first_magic(vb["vendor_ramdisk"], INITRD_BASE, INITRD_BASE, initrd[1])
    need(seen is None, "vendor ramdisk contém SWEETXNU em %#x: o shim pararia ali" % (seen or 0))
    if p is not None:
        found = first_magic(ramdisk, INITRD_BASE + V, INITRD_BASE, initrd[1])
        need(found == payload_pa, "shim não acharia o payload no endereço esperado")
        need(payload_pa % 8 == 0, "payload desalinhado")
        report["payload_pa"] = hex(payload_pa)
        report["payload_memory"] = check_payload_memory(p, initrd)
    else:
        need(PAYLOAD_MAGIC not in ramdisk, "sonda não pode conter SWEETXNU")

    # boot.img v3: header stock com tamanhos novos; páginas de 4 KiB.
    hdr = bytearray(stock_boot[:BOOT_V3_HEADER])
    struct.pack_into("<II", hdr, 8, len(shim), R)
    out = bytearray(hdr) + b"\0" * (PAGE - BOOT_V3_HEADER)
    out += shim + b"\0" * (align(len(shim), PAGE) - len(shim))
    out += ramdisk + b"\0" * (align(R, PAGE) - R)
    need(len(out) <= partition, "boot.img (%d) excede a partição (%d)" % (len(out), partition))
    report.update(boot_img_size=len(out), os_version=hex(sb["os_version"]),
                  cmdline=sb["cmdline"].rstrip(b"\0").decode("latin1"),
                  sha256=hashlib.sha256(out).hexdigest())
    return bytes(out), report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stock-boot", required=True)
    ap.add_argument("--vendor-boot", required=True)
    ap.add_argument("--shim", required=True, help="shim/out/Image (BOARD=p3s ou p3s-window)")
    ap.add_argument("--payload", help="payload SWEETXNU de tools/mkpayload.py; ausente = sonda")
    ap.add_argument("--out", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rd = lambda p: pathlib.Path(p).read_bytes()
    try:
        img, rep = build(rd(a.stock_boot), rd(a.vendor_boot), rd(a.shim),
                         rd(a.payload) if a.payload else None)
    except ContractError as e:
        print("RECUSADO:", e, file=sys.stderr)
        return 2
    pathlib.Path(a.out).write_bytes(img)
    for k in ("mode", "kernel_range", "initrd", "ramdisk_pad", "payload_pa", "boot_img_size", "sha256"):
        if k in rep:
            print("%-14s %s" % (k, rep[k]))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
