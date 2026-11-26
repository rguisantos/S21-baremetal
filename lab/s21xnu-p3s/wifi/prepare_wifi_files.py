#!/usr/bin/env python3
"""Arquivos do Wi-Fi BCM4389 C1 para o XNU no p3s (patch 0150), a partir do vendor HZC2.

  prepare_wifi_files.py --vendor-wifi DIR --out NOVO_DIR [--json r.json]

DIR é /vendor/firmware/wifi do próprio aparelho (ou da imagem HZC2). Os três
arquivos que o diagnóstico do Android identificou (módulo SEMCO SWB-E53 ES4.0,
firmware 20.80.87.4, docs/s21xnu-wifi-bcm4389-hzc2.md) são conferidos pelo
SHA-256 fixado e copiados com os nomes que o driver do 0150 procura em
/usr/local/etc/wifi:

  bcmdhd_sta.bin_c1        -> bcm4389-sta.bin
  nvram.txt_ES40_semco_c1  -> bcm4389-nvram-semco.txt
  bcmdhd_clm.blob          -> bcm4389-clm.blob

Também lê do firmware o que o driver vai usar: a palavra 0 (vetor de reset),
o tamanho de RAM declarado pela imagem ("SMAR" em 0x6c, se houver) e onde a
RAM termina a partir de 0x200000; e procura a versão e o FWID esperados.
Um hash diferente é recusado: outra revisão de módulo pede outra seleção.
Os arquivos do vendor não entram no repositório.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import sys

FILES = {
    "bcmdhd_sta.bin_c1": ("bcm4389-sta.bin", "234e3abe763343689ca8026003b87c80565cca7d08be56850d723b34a60f7e71"),
    "nvram.txt_ES40_semco_c1": ("bcm4389-nvram-semco.txt",
                                "bb111969049ad8a4243cbac88d36748a645d6fea2ce813dd607cfbae1ffde071"),
    "bcmdhd_clm.blob": ("bcm4389-clm.blob", "d52bc311084ebfbfaf45ee2d483bf9de43438f6ef89e2cb43afa7d9d2300ce4c"),
}
RAMBASE_4389 = 0x200000
RAMSIZE_MAGIC, RAMSIZE_OFFSET = 0x534D4152, 0x6C
FW_MARKERS = (b"20.80.87.4", b"01-3fe70789")
BAR2_FIRST_MAP = 0x400000       # o que o driver mapeia do BAR2 antes de remapear


class WifiError(Exception):
    pass


def firmware_facts(fw):
    if len(fw) < RAMSIZE_OFFSET + 8:
        raise WifiError("firmware curto demais: %d bytes" % len(fw))
    facts = {"bytes": len(fw), "reset_vector": "%#010x" % struct.unpack_from("<I", fw, 0)[0]}
    magic, ram = struct.unpack_from("<II", fw, RAMSIZE_OFFSET)
    facts["ram_declared"] = "%#x" % ram if magic == RAMSIZE_MAGIC else None
    if magic == RAMSIZE_MAGIC:
        end = RAMBASE_4389 + ram
        facts["ram_end"] = "%#x" % end
        facts["bar2_remap_needed"] = end > BAR2_FIRST_MAP
        if len(fw) > ram:
            raise WifiError("firmware de %d bytes não cabe na RAM declarada %#x" % (len(fw), ram))
    facts["markers"] = {m.decode(): m in fw for m in FW_MARKERS}
    return facts


def prepare(src, out, files=FILES):
    src, out = pathlib.Path(src), pathlib.Path(out)
    if out.exists() and any(out.iterdir()):
        raise WifiError("%s já existe e não está vazio" % out)
    found = {}
    for name, (target, want) in files.items():
        p = src / name
        if not p.is_file():
            raise WifiError("falta %s em %s" % (name, src))
        data = p.read_bytes()
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            raise WifiError("%s: SHA-256 %s, esperado %s (outra revisão de módulo?)" % (name, got, want))
        found[name] = data
    report = {"files": [], "firmware": firmware_facts(found["bcmdhd_sta.bin_c1"])}
    out.mkdir(parents=True, exist_ok=True)
    sums = []
    for name, (target, want) in files.items():
        (out / target).write_bytes(found[name])
        (out / target).chmod(0o644)
        sums.append("%s  %s\n" % (want, target))
        report["files"].append({"vendor": name, "target": target, "bytes": len(found[name]), "sha256": want})
    (out / "SHA256SUMS").write_text("".join(sums))
    (out / "LEIAME.txt").write_text(
        "Copiar os tres arquivos bcm4389-* para /usr/local/etc/wifi no rootfs do s21xnu\n"
        "(dono root, modo 0644). Boot-args: sweetwifi=4 carrega o firmware (patch 0150);\n"
        "sweetwifi=3 so identifica o chip (patch 0149). Conferir com: sha256sum -c SHA256SUMS\n")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor-wifi", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    try:
        report = prepare(a.vendor_wifi, a.out)
    except WifiError as e:
        print("RECUSADO:", e, file=sys.stderr)
        return 1
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if a.json:
        pathlib.Path(a.json).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
