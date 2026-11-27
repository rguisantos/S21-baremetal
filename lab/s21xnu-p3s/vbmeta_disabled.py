#!/usr/bin/env python3
"""vbmeta com verificação desativada, a partir do vbmeta.img do próprio firmware.

  vbmeta_disabled.py --vbmeta vbmeta.img[.lz4] --out NOVO_DIR

O vbmeta.img (ou vbmeta.img.lz4) vem do arquivo BL do firmware HZC2 e é
conferido contra os pins de docs/references/capture-a0-parent-pins-hzc2.json
(lz4 e cru); qualquer outro vbmeta é recusado antes de virar tar. O
script confere o cabeçalho AVB ("AVB0", tamanhos dos blocos dentro do
arquivo), liga os bits 0 e 1 de `flags` (offset 120, big endian:
HASHTREE_DISABLED e VERIFICATION_DISABLED, os mesmos que `avbtool
--flags 3` e o Magisk usam) e não muda mais nenhum byte. Grava:

  vbmeta.img               a imagem com flags |= 3
  vbmeta_disabled.tar      para o Odin (slot USERDATA, junto com o AP)
  vbmeta_disabled.tar.md5
  relatorio.json, SHA256SUMS

Com o bootloader desbloqueado, é o que deixa o S-Boot aceitar um boot.img
que não é assinado pela Samsung (o mesmo que os guias do TWRP para o
Exynos pedem). Exige desbloqueio OEM; gravar com o bootloader travado não
funciona. Nada é gravado no aparelho.
"""
import argparse
import hashlib
import io
import json
import pathlib
import struct
import sys
import tarfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
PINS = REPO / "docs" / "references" / "capture-a0-parent-pins-hzc2.json"

HEADER = 256
FLAGS_OFF = 120
DISABLE = 0x3                     # HASHTREE_DISABLED | VERIFICATION_DISABLED
FIXED_TAR_TIME = 1764115200
TAGS = {0: "property", 1: "hashtree", 2: "hash", 3: "kernel_cmdline", 4: "chain_partition"}


class VbmetaError(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise VbmetaError(msg)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def parse(img):
    need(len(img) >= HEADER and img[:4] == b"AVB0", "não é vbmeta AVB (magic AVB0 ausente)")
    major, minor = struct.unpack_from(">II", img, 4)
    auth, aux = struct.unpack_from(">QQ", img, 12)
    need(major == 1, "versão AVB %d.%d inesperada" % (major, minor))
    need(auth % 64 == 0 and aux % 64 == 0 and HEADER + auth + aux <= len(img), "blocos AVB fora do arquivo")
    desc_off, desc_size = struct.unpack_from(">QQ", img, 96)
    need(desc_off + desc_size <= aux, "descritores fora do bloco auxiliar")
    flags, = struct.unpack_from(">I", img, FLAGS_OFF)
    base = HEADER + auth + desc_off
    at, end, descs = base, base + desc_size, []
    while at + 16 <= end:
        tag, n = struct.unpack_from(">QQ", img, at)
        need(n % 8 == 0 and at + 16 + n <= end, "descritor %d truncado" % len(descs))
        name = None
        if tag == 2:                            # hash: image_size, hash_algorithm[32], name_len, salt, digest, flags, 60
            nlen, = struct.unpack_from(">I", img, at + 16 + 8 + 32)
            name = img[at + 16 + 116:at + 16 + 116 + nlen].decode("ascii", "replace")
        elif tag == 4:                          # chain: location, name_len, key_len, flags, 60 reservados
            _, nlen = struct.unpack_from(">II", img, at + 16)
            name = img[at + 16 + 76:at + 16 + 76 + nlen].decode("ascii", "replace")
        descs.append({"tag": TAGS.get(tag, str(tag)), "partition": name})
        at += 16 + n
    return {"version": "%d.%d" % (major, minor), "flags": flags, "auth_size": auth, "aux_size": aux,
            "descriptors": descs}


def disable(img):
    info = parse(img)
    out = bytearray(img)
    struct.pack_into(">I", out, FLAGS_OFF, info["flags"] | DISABLE)
    return bytes(out), info


def odin_tar(data, name="vbmeta.img"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        ti = tarfile.TarInfo(name)
        ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = len(data), FIXED_TAR_TIME, 0o644, 0, 0, "", ""
        tf.addfile(ti, io.BytesIO(data))
    tar = buf.getvalue()
    return tar, tar + ("%s  vbmeta_disabled.tar\n" % hashlib.md5(tar).hexdigest()).encode()


def load(path, pins=None):
    """vbmeta.img ou vbmeta.img.lz4 do BL HZC2, conferido pelos pins (tamanho e SHA-256)."""
    pins = pins or json.loads(PINS.read_text())
    p = pathlib.Path(path)
    data = p.read_bytes()
    if p.suffix == ".lz4":
        lz = pins["parent_lz4"]
        need(len(data) == lz["bytes"] and sha(data) == lz["sha256"], "%s não é o vbmeta.img.lz4 do BL HZC2 fixado" % p.name)
        from check_capture_a0_parent import lz4_frame
        data = lz4_frame(data, pins["parent_raw"]["bytes"])
    raw = pins["parent_raw"]
    need(len(data) == raw["bytes"] and sha(data) == raw["sha256"], "%s não é o vbmeta.img do BL HZC2 fixado" % p.name)
    return data


def prepare(img, out):
    out = pathlib.Path(out)
    need(not out.exists(), "diretório de saída precisa ser novo: %s" % out)
    new, info = disable(img)
    tar, md5 = odin_tar(new)
    out.mkdir(parents=True)
    files = {"vbmeta.img": new, "vbmeta_disabled.tar": tar, "vbmeta_disabled.tar.md5": md5}
    for n, d in files.items():
        (out / n).write_bytes(d)
    report = {"schema": "s21xnu-vbmeta-disabled/1", "input_sha256": sha(img), "input_bytes": len(img),
              "flags_before": info["flags"], "flags_after": info["flags"] | DISABLE, "avb": info,
              "changed_bytes": sum(a != b for a, b in zip(img, new)), "files": {n: sha(d) for n, d in files.items()}}
    (out / "relatorio.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    names = sorted(files) + ["relatorio.json"]
    (out / "SHA256SUMS").write_text("".join("%s  %s\n" % (sha((out / n).read_bytes()), n) for n in names))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vbmeta", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        rep = prepare(load(a.vbmeta), a.out)
    except (VbmetaError, OSError, ValueError) as e:
        print("RECUSADO:", e, file=sys.stderr)
        return 2
    print("flags %#x -> %#x, %d byte(s) alterado(s)" % (rep["flags_before"], rep["flags_after"], rep["changed_bytes"]))
    for d in rep["avb"]["descriptors"]:
        print("  descritor %s %s" % (d["tag"], d["partition"] or ""))
    print("kit em", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
