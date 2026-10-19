#!/usr/bin/env python3
# abl_triage.py — triagem estática de imagens de bootloader (ABL) do firmware
#
# PROPÓSITO (Dia 2, sem hardware): extrair do firmware stock TODOS os dados
# que o payload precisa para o Dia 3, sem executar nada:
#   * endereço do console UART (nó serial@ de DTB embutido no ABL)
#   * base e tamanho da RAM (nó memory@ do mesmo DTB)
#   * mensagens de log do ABL (o formato exato das linhas que o minicom vai
#     cuspir antes do handoff — para reconhecer o momento do controle)
#   * endereços citados em strings (pistas de bases de carga)
#
# ENTRADA (qualquer uma):
#   abl.img | boot.img | dtb | binário raw | AP_*.tar.md5 do firmware
#   (no .tar/.tar.md5: procura abl.img/boot.img/DTB nos membros)
#
# SAÍDA: relatório em stdout (+ opcional --json) e, com --dump-dtb,
#   extrai os DTBs encontrados em arquivos.
#
# Offline, Python puro, sem dependências — mesma disciplina do kit:
# zero ferramenta externa, roda em qualquer Linux com python3.

import json
import os
import re
import struct
import sys
import tarfile

MIN_STR = 6            # strings com interesse a partir deste tamanho
DTB_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


# ---------------------------------------------------------------- util

def be32(buf, off):
    return struct.unpack_from(">I", buf, off)[0]


def be64_cells(buf, off, cells):
    v = 0
    for i in range(cells):
        v = (v << 32) | be32(buf, off + 4 * i)
    return v


def cstr(buf, off):
    end = buf.find(b"\x00", off)
    if end < 0:
        end = len(buf)
    return buf[off:end].decode("ascii", "replace")


# ------------------------------------------------------- boot image v0-v4

def parse_bootimg_header(k):
    """Android boot image header — retorna dict ou None."""
    if k[:8] != b"ANDROID!":
        return None
    h = {}
    h["magic"] = "ANDROID!"
    h["kernel_size"], h["kernel_addr"] = struct.unpack_from("<II", k, 8)
    h["ramdisk_size"], h["ramdisk_addr"] = struct.unpack_from("<II", k, 16)
    h["second_size"], h["second_addr"] = struct.unpack_from("<II", k, 24)
    h["tags_addr"] = struct.unpack_from("<I", k, 32)[0]
    h["page_size"] = struct.unpack_from("<H", k, 36)[0]
    h["header_version"], h["os_version"] = struct.unpack_from("<HH", k, 38)
    h["name"] = cstr(k, 48) if len(k) > 48 else ""
    if h["header_version"] >= 3:
        # v3/v4: header de 1580 B, kernel na PRIMEIRA página inteira
        h["kernel_off"] = h["page_size"]
        h["header_len"] = 1580
    else:
        # v0-v2: header 1632/1648 B + cmdline; kernel após a 1a página
        h["kernel_off"] = h["page_size"]
        h["header_len"] = 1632 + len(k[1632:1632 + 512])  # aproximação
    return h


def bootimg_extract_kernel(blob):
    h = parse_bootimg_header(blob)
    if not h:
        return None, None
    off = h["kernel_off"]
    kern = blob[off:off + h["kernel_size"]]
    return h, kern


# ---------------------------------------------------------- arm64 Image

def parse_arm64_image_header(k):
    """Linux arm64 Image header (booting.rst) — retorna dict ou None."""
    if len(k) < 64 or k[0x38:0x3C] != b"ARM\x64":
        return None
    text_off, image_sz, flags = struct.unpack_from("<QQQ", k, 8)
    return {
        "magic": "ARM\\x64",
        "text_offset": text_off,
        "image_size": image_sz,
        "flags": flags,
        "page_size_kb": {1: 4, 2: 16, 3: 64}.get((flags >> 1) & 3, 4),
        "placement_2mb": bool(flags & 8),
        "little_endian": not (flags & 1),
        "pe_coff_off": struct.unpack_from("<I", k, 0x3C)[0],
    }


# ------------------------------------------------------------------- FDT

def fdt_parse_header(buf, base):
    totalsize = be32(buf, base + 4)
    off_struct = be32(buf, base + 8)
    off_strs = be32(buf, base + 12)
    version = be32(buf, base + 20)
    return {
        "offset": base,
        "totalsize": totalsize,
        "off_struct": off_struct,
        "off_strs": off_strs,
        "version": version,
    }


NODE_INTEREST = re.compile(
    r"(?i)(serial|uart|memory|watchdog|reboot|gic|timer|chipid|pmu|syscon)")
# LIÇÃO do virt.dtb: o nó UART chama-se "pl011@9000000" — NOME não contém
# "serial/uart". O casamento confiável é pelo COMPATIBLE (arm,pl011,
# ns16550a, samsung exynos uart...). Como a ordem das props é arbitrária
# (reg pode vir ANTES do compatible), acumulamos por nó e decidimos no
# END_NODE.
UART_RE = re.compile(r"(?i)(uart|pl011|ns16550|8250|serial)")
PROP_KEEP = ("reg", "compatible", "status", "clock-frequency",
             "current-speed", "interrupts")


def _decode_prop(data):
    """compatible vira lista de strings; binário legível vira ascii; resto hex."""
    txt = data.split(b"\x00")
    if data and all(20 <= b < 127 for b in data if b != 0) and \
            any(len(t) >= 2 for t in txt):
        return " | ".join(t.decode("ascii") for t in txt if t)
    return data.hex()


def _emit_node(path, nac, nsc, props, interesting):
    compat = props.get("compatible", b"").decode("ascii", "replace")
    is_uart = UART_RE.search(compat) or UART_RE.search(path)
    is_other = NODE_INTEREST.search(path)
    if not (is_uart or is_other):
        return
    for pname, pval in props.items():
        if pname == "reg":
            try:
                addr = be64_cells(pval, 0, min(nac, 4))
                extra = ""
                if len(pval) >= 4 * (nac + nsc):
                    extra = "+" + hex(be64_cells(pval, 4 * nac, min(nsc, 4)))
                interesting.append(("reg", path, pname, hex(addr) + extra))
            except (struct.error, IndexError):
                pass
        else:
            interesting.append((pname, path, pname, _decode_prop(pval)))


def fdt_walk(buf, base, info):
    """Percorre o FDT inteiro acumulando props por nó; no END_NODE decide
    se o nó é de interesse (UART pelo compatible — o nome pode enganar,
    ex. pl011@9000000; memory/reboot/watchdog/gic/timer pelo nome).
    #address/#size-cells herdados por nível."""
    interesting = []
    stack = []          # [(nome, addr_cells, size_cells, props)]
    p = base + info["off_struct"]
    end = base + info["totalsize"]
    while p < end:
        tok = be32(buf, p)
        p += 4
        if tok == FDT_END:
            break
        if tok == FDT_BEGIN_NODE:
            name = cstr(buf, p)
            p += (len(name) + 1 + 3) & ~3
            if stack:
                _, ac, sc, _ = stack[-1]
                stack.append([name, ac, sc, {}])
            else:
                stack.append([name, 2, 2, {}])
            continue
        if tok == FDT_END_NODE:
            if stack:
                name, ac, sc, props = stack.pop()
                parts = [s[0] for s in stack if s[0]] + [name]
                path = "/" + "/".join(x for x in parts if x) if parts else "/"
                _emit_node(path, ac, sc, props, interesting)
            continue
        if tok == FDT_PROP:
            ln, nameoff = struct.unpack_from(">II", buf, p)
            pname = cstr(buf, base + info["off_strs"] + nameoff)
            data = buf[p + 8:p + 8 + ln]
            p += 8 + (ln + 3) & ~3
            if not stack:
                continue
            node = stack[-1]
            if pname == "#address-cells" and len(data) >= 4:
                node[1] = be32(data, 0)
            elif pname == "#size-cells" and len(data) >= 4:
                node[2] = be32(data, 0)
            elif pname in PROP_KEEP and len(node) > 3:
                node[3][pname] = data
            elif pname in ("model",) and len(stack) == 1:
                interesting.append(("root", "/", "model",
                                    _decode_prop(data)))
            elif pname in ("compatible",) and len(stack) == 1:
                interesting.append(("root", "/", "compatible",
                                    _decode_prop(data)))
            continue
    return interesting


def scan_dtb(blob, tag):
    """Escaneia o binário INTEIRO procurando FDTs embutidos."""
    found = []
    magic_be = struct.pack(">I", DTB_MAGIC)
    pos = 0
    while True:
        pos = blob.find(magic_be, pos)
        if pos < 0:
            break
        try:
            info = fdt_parse_header(blob, pos)
            # sanidade: totalsize crível e offsets dentro do buffer
            if 0 < info["totalsize"] <= len(blob) - pos and \
               info["off_struct"] < info["totalsize"] and info["version"] <= 17:
                nodes = fdt_walk(blob, pos, info)
                found.append((pos, info, nodes))
        except (struct.error, IndexError):
            pass
        pos += 4
    return found


# --------------------------------------------------------------- strings

STR_INTEREST = re.compile(
    r"(?i)(uart|serial|console|download|odin|heimdall|fastboot|abl|bootloader"
    r"|exynos|universal2100|s5e9840|reboot|ramdump|ecc|loader|pit|efuse)"
)
HEXADDR = re.compile(r"0x[0-9a-fA-F]{5,16}")


def scan_strings(blob):
    raw = re.findall(rb"[\x20-\x7e]{%d,}" % MIN_STR, blob)
    hits, addrs = [], []
    for b in raw:
        s = b.decode("ascii")
        if STR_INTEREST.search(s):
            hits.append(s)
        for m in HEXADDR.finditer(s):
            addrs.append(m.group(0))
    # dedup preservando ordem
    seen = set()
    hits = [x for x in hits if not (x in seen or seen.add(x))]
    seen = set()
    addrs = [x for x in addrs if not (x in seen or seen.add(x))]
    return hits, addrs


# ------------------------------------------------------------------ main

def triage_blob(blob, name, opts):
    lines = []
    rep = {"arquivo": name, "tamanho": len(blob)}
    lines.append("=" * 72)
    lines.append("TRIAGEM: %s (%d bytes)" % (name, len(blob)))

    # 1. formato
    h = parse_bootimg_header(blob)
    kern = None
    if h:
        rep["formato"] = "boot image v%d" % h["header_version"]
        lines.append("[*] Boot image ANDROID! v%d | kernel %d B | page %d B"
                     % (h["header_version"], h["kernel_size"], h["page_size"]))
        if h.get("name"):
            lines.append("    nome: %s" % h["name"])
        kern = blob[h["kernel_off"]:h["kernel_off"] + h["kernel_size"]]
        blob = kern
        name = name + "::kernel"
        lines.append("[*] kernel extraído: %d B" % len(kern))

    ih = parse_arm64_image_header(blob)
    if ih:
        rep["kernel_header"] = ih
        lines.append("[+] Header de Image arm64 (magic ARM\\x64 em 0x38):")
        lines.append("    text_offset=0x%x image_size=0x%x flags=0x%x"
                     " (%s, pages=%dKB, placement2MB=%s)"
                     % (ih["text_offset"], ih["image_size"], ih["flags"],
                        "LE" if ih["little_endian"] else "BE",
                        ih["page_size_kb"],
                        ih["placement_2mb"]))
    elif blob[:4] == b"\x7fELF":
        rep["formato"] = "ELF"
        ei_class, ei_data = blob[4], blob[5]
        lines.append("[*] ELF (class %d, data %d) — ABL completo?"
                     % (ei_class, ei_data))
    elif not h:
        rep["formato"] = "raw"
        lines.append("[*] binário raw (sem header conhecido)")

    # 2. DTB embutido (o ouro: serial@ e memory@)
    dtbs = scan_dtb(blob, name)
    rep["dtbs"] = []
    for pos, info, nodes in dtbs:
        lines.append("")
        lines.append("[+] DTB embutido em offset 0x%x (totalsize 0x%x, v%d)"
                     % (pos, info["totalsize"], info["version"]))
        d = {"offset": hex(pos), "totalsize": hex(info["totalsize"]),
             "nos": []}
        for kind, node, prop, val in nodes:
            lines.append("    %-12s %-34s %-16s %s" % (kind, node, prop, val))
            d["nos"].append({"tipo": kind, "no": node,
                             "prop": prop, "valor": val})
        rep["dtbs"].append(d)
        if opts.get("dump_dtb"):
            out = "%s.dtb.@%x.dtb" % (os.path.splitext(name)[0] or "blob", pos)
            with open(out, "wb") as f:
                f.write(blob[pos:pos + info["totalsize"]])
            lines.append("    extraído -> %s" % out)
    if not dtbs:
        lines.append("[-] nenhum DTB embutido encontrado")

    # 3. strings de interesse + endereços citados
    hits, addrs = scan_strings(blob)
    rep["strings"] = hits[:80]
    rep["enderecos_hex"] = addrs[:60]
    lines.append("")
    lines.append("[*] strings de interesse (%d):" % len(hits))
    for s in hits[:40]:
        lines.append("    | %s" % s[:110])
    lines.append("")
    lines.append("[*] endereços hex citados (%d): %s"
                 % (len(addrs), " ".join(addrs[:30])))
    lines.append("")
    lines.append("[i] próximo passo: Ghidra/objdump com base sugerida pelo "
                 "endereço de carga do header (ou 0x0 se ELF); procurar "
                 "chamadas ao console UART nos endereços acima.")
    return "\n".join(lines), rep


def open_from_container(path):
    """AP_*.tar.md5: devolve [(nome, bytes)] dos membros interessantes."""
    out = []
    try:
        with tarfile.open(path, "r") as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                low = os.path.basename(m.name).lower()
                if low in ("abl.img", "boot.img", "dtbo.img", "vendor_boot.img") \
                        or low.endswith(".dtb") or low.endswith(".mbn"):
                    f = tf.extractfile(m)
                    if f:
                        out.append((m.name, f.read()))
    except (tarfile.TarError, OSError) as e:
        print("[!] não consegui ler %s como tar: %s" % (path, e))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("uso: python3 abl_triage.py <abl.img|boot.img|dtb|AP.tar.md5> "
              "[--json] [--dump-dtb]")
        sys.exit(2)
    opts = {"json": "--json" in sys.argv, "dump_dtb": "--dump-dtb" in sys.argv}
    targets = []
    for p in sys.argv[1:]:
        if p.startswith("--"):
            continue
        if not os.path.exists(p):
            print("[!] arquivo não existe: %s" % p)
            sys.exit(2)
        if tarfile.is_tarfile(p):
            members = open_from_container(p)
            if members:
                print("[*] %s é um tar — %d membros de interesse"
                      % (p, len(members)))
                targets.extend(members)
                continue
        with open(p, "rb") as f:
            targets.append((p, f.read()))

    allrep = []
    for name, blob in targets:
        text, rep = triage_blob(blob, name, opts)
        print(text)
        allrep.append(rep)
    if opts["json"]:
        with open("abl_triage.json", "w") as f:
            json.dump(allrep, f, indent=2)
        print("[*] relatório JSON -> abl_triage.json")


if __name__ == "__main__":
    main()
