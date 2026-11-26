#!/usr/bin/env python3
"""Compara, entre duas placas Exynos 2100, o contrato de hardware usado pelo s21xnu.

O port s21xnu (XNU no Galaxy S21+, `t2s`) fixa no código barramentos, pinos,
endereços e geometria do painel. Este verificador lê dois FDT já mesclados
(base SoC + overlay da placa) e confere, item a item, se o S21 Ultra (`p3s`)
expõe os mesmos recursos. É leitura estática das fontes: não prova estado do
aparelho, energia, clocks ou o FDT final entregue pelo LK.

Uso:
  s21xnu_board_contract.py --dtb p3s=p3s.dtb --dtb t2s=t2s.dtb [--json saida.json]
  s21xnu_board_contract.py --flop-dts DIR [--rev r17] [--json saida.json]

Com --flop-dts, DIR é arch/arm64/boot/dts/exynos de uma árvore FlopKernel /
Samsung; os FDT são compilados com dtc e mesclados com fdtoverlay (PATH ou
tools/root). O primeiro rótulo é o alvo; o segundo, a referência s21xnu.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9

# Janela de RAM que o s21xnu entrega ao XNU (tools/mkadt.py --highmem).
XNU_WINDOW = (0x8C0000000, 0x940000000)


class Node:
    def __init__(self, name, parent=None):
        self.name, self.parent, self.props, self.children = name, parent, {}, []

    @property
    def path(self):
        if self.parent is None:
            return "/"
        base = self.parent.path
        return (base if base != "/" else "") + "/" + self.name

    def u32(self, key):
        v = self.props.get(key)
        if v is None or len(v) % 4:
            return None
        return list(struct.unpack(">%dI" % (len(v) // 4), v))

    def strs(self, key):
        v = self.props.get(key)
        if v is None:
            return None
        return [s.decode("latin1") for s in v.rstrip(b"\0").split(b"\0")]

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


def parse_fdt(blob):
    if len(blob) < 40:
        raise ValueError("FDT truncado")
    magic, total, off_struct, off_strings = struct.unpack(">IIII", blob[:16])
    if magic != FDT_MAGIC:
        raise ValueError("magic FDT inválido: %#x" % magic)
    if total > len(blob):
        raise ValueError("totalsize %d maior que o arquivo %d" % (total, len(blob)))
    pos, root, cur = off_struct, None, None
    while True:
        if pos + 4 > total:
            raise ValueError("estrutura sem FDT_END")
        tok, = struct.unpack(">I", blob[pos:pos + 4])
        pos += 4
        if tok == FDT_BEGIN_NODE:
            end = blob.index(b"\0", pos)
            node = Node(blob[pos:end].decode("latin1"), cur)
            pos = (end + 4) & ~3
            if cur is None:
                if root is not None:
                    raise ValueError("mais de uma raiz")
                root = node
            else:
                cur.children.append(node)
            cur = node
        elif tok == FDT_END_NODE:
            if cur is None:
                raise ValueError("END_NODE sem nó aberto")
            cur = cur.parent
        elif tok == FDT_PROP:
            if cur is None:
                raise ValueError("propriedade fora de nó")
            ln, nameoff = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            s0 = off_strings + nameoff
            key = blob[s0:blob.index(b"\0", s0)].decode("latin1")
            cur.props[key] = blob[pos:pos + ln]
            pos = (pos + ln + 3) & ~3
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            if cur is not None:
                raise ValueError("FDT_END com nó aberto")
            return root
        else:
            raise ValueError("token %d inválido em %#x" % (tok, pos - 4))


class Board:
    def __init__(self, label, blob):
        self.label, self.sha256 = label, hashlib.sha256(blob).hexdigest()
        self.root = parse_fdt(blob)
        self.nodes = {n.path: n for n in self.root.walk()}
        self.ph = {}
        for n in self.root.walk():
            v = n.u32("phandle")
            if v:
                self.ph[v[0]] = n

    def find(self, pred):
        return [n for n in self.root.walk() if pred(n)]

    def first_compat(self, compat):
        hits = self.find(lambda n: compat in (n.strs("compatible") or []))
        return hits[0] if hits else None

    def pins(self, node, key="pinctrl-0"):
        out = []
        for h in node.u32(key) or []:
            target = self.ph.get(h)
            out += (target.strs("samsung,pins") or [target.name]) if target else ["?%#x" % h]
        return out

    def supply(self, node, key):
        v = node.u32(key)
        if not v or v[0] not in self.ph:
            return None
        reg = self.ph[v[0]]
        return {
            "name": (reg.strs("regulator-name") or [reg.name])[0],
            "node": reg.path,
            "uV": (reg.u32("regulator-min-microvolt") or [None])[0],
        }


def reg_pairs(board, node):
    """(endereço, tamanho) de reg usando as células do pai."""
    parent = node.parent
    ac = (parent.u32("#address-cells") or [2])[0] if parent else 2
    sc = (parent.u32("#size-cells") or [1])[0] if parent else 1
    words = node.u32("reg") or []
    out, step = [], ac + sc
    if step == 0:
        return out
    for i in range(0, len(words) - step + 1, step):
        a = 0
        for w in words[i:i + ac]:
            a = (a << 32) | w
        s = 0
        for w in words[i + ac:i + step]:
            s = (s << 32) | w
        out.append((a, s))
    return out


def facts(b):
    """Recursos que o s21xnu fixa no código, extraídos do FDT da placa."""
    f = {}
    ts = b.first_compat("slsi,slsi_ts")
    if ts:
        f["touch.bus"] = ts.parent.path
        f["touch.addr"] = hex((ts.u32("reg") or [0])[0])
        f["touch.bus_pins"] = b.pins(ts.parent)
        f["touch.attn_pins"] = b.pins(ts)
        f["touch.io_supply"] = b.supply(ts, "tsp_io_ldo-supply")
        f["touch.avdd_supply"] = b.supply(ts, "tsp_avdd_ldo-supply")
        f["touch.max_coords"] = ts.u32("sec,max_coords")
        f["touch.firmware"] = (ts.strs("sec,firmware_name") or [None])[0]
    pm = b.first_compat("samsung,s2dos05pmic")
    if pm:
        f["s2dos05.bus"] = pm.parent.path
        f["s2dos05.addr"] = hex((pm.u32("reg") or [0])[0])
        f["s2dos05.bus_pins"] = b.pins(pm.parent)
    mx = b.first_compat("maxim,max77705")
    if mx:
        f["max77705.bus"] = mx.parent.path
        f["max77705.addr"] = hex((mx.u32("reg") or [0])[0])
        f["max77705.bus_pins"] = b.pins(mx.parent)
    keys = b.first_compat("gpio-keys")
    if keys:
        f["keys.pins"] = sorted(b.pins(keys))
        f["keys.codes"] = sorted((c.u32("linux,code") or [0])[0] for c in keys.children)
    pcie = b.nodes.get("/pcie@113B0000")
    if pcie:
        f["wifi.pcie_ep_ver"] = hex((pcie.u32("ep-ver") or [0])[0])
        f["wifi.pcie_max_link_speed"] = (pcie.u32("max-link-speed") or [None])[0]
        f["wifi.pcie_pins"] = b.pins(pcie)
    for label, compat in (("mali", "arm,mali"), ("ufs", "samsung,exynos-ufs")):
        n = b.first_compat(compat)
        if n:
            f[label + ".reg"] = [[hex(a), hex(s)] for a, s in reg_pairs(b, n)]
    gic = b.first_compat("arm,gic-v3")
    if gic:
        f["gic.reg"] = [[hex(a), hex(s)] for a, s in reg_pairs(b, gic)]
    cpus = b.nodes.get("/cpus")
    if cpus:
        f["cpu.mpidr"] = sorted(hex((c.u32("reg") or [0])[-1]) for c in cpus.walk()
                                if (c.strs("device_type") or [""])[0] == "cpu")
    modes = set()
    for n in b.root.walk():
        if n.name.endswith("_panel_display_modes"):
            for c in n.children:
                tail = c.name.rsplit("_", 2)
                if len(tail) == 3 and "x" in tail[1]:
                    w, h = tail[1].split("x")
                    if w.isdigit() and h.isdigit():
                        modes.add((int(w), int(h)))
    if modes:
        f["panel.max_mode"] = "%dx%d" % max(modes, key=lambda m: m[0] * m[1])
        f["panel.modes"] = ["%dx%d" % m for m in sorted(modes)]
    rm = b.nodes.get("/reserved-memory")
    if rm:
        hits = []
        for c in rm.children:
            for a, s in reg_pairs(b, c):
                if a < XNU_WINDOW[1] and a + s > XNU_WINDOW[0]:
                    hits.append("%s %#x+%#x" % (c.name, a, s))
        f["memory.fixed_reserved_in_xnu_window"] = hits
    return f


# Consequência para o s21xnu quando o item difere. Itens ausentes daqui são
# informativos.
IMPACT = {
    "touch.bus_pins": "0094 faz bit-bang em gpp4-0/1",
    "touch.attn_pins": "0094 lê ATTN em gpa1-0",
    "touch.addr": "0094 usa SEC_TS_ADDR 0x48",
    "touch.io_supply": "0094/0107 ligam S2DOS05 LDO2 (tsp_io)",
    "touch.avdd_supply": "0094/0107 ligam S2DOS05 LDO3 (tsp_avdd)",
    "touch.max_coords": "0094 converte 0..4095 para pixels do painel",
    "s2dos05.bus_pins": "0094 faz bit-bang em gpp0-2/3",
    "s2dos05.addr": "0094 usa S2DOS05_ADDR 0x60",
    "max77705.bus_pins": "0123 usa o banco gpp1 (0x10430020)",
    "max77705.addr": "0123 fala com o MAX77705",
    "keys.pins": "0125 lê volume em gpa0",
    "wifi.pcie_ep_ver": "0109/0111/0142 carregam firmware BCM4375",
    "wifi.pcie_max_link_speed": "0109 treina o link PCIe ch0",
    "panel.max_mode": "shim/console.h, mkadt.py, 0010/0061/0094 fixam 1080x2400",
    "mali.reg": "0111/0112 usam MALI_PHYS 0x18500000",
    "ufs.reg": "0028 usa o host UFS 0x13100000",
    "gic.reg": "shim/mkadt fixam GICD/GICR",
    "memory.fixed_reserved_in_xnu_window": "mkadt.py --highmem entrega 0x8c0000000-0x940000000",
}


def compare(target, ref):
    ft, fr = facts(target), facts(ref)
    items = []
    for key in sorted(set(ft) | set(fr)):
        a, b = ft.get(key), fr.get(key)
        if a is None or b is None:
            status = "ausente"
        else:
            status = "igual" if a == b else "difere"
        items.append({"item": key, "status": status, target.label: a, ref.label: b,
                      "s21xnu": IMPACT.get(key, "")})
    return items


def find_tool(name):
    here = os.path.dirname(os.path.abspath(__file__))
    local = os.path.join(here, "..", "tools", "root", "usr", "bin", name)
    if os.path.exists(local):
        return os.path.abspath(local), os.path.join(here, "..", "tools", "root")
    path = shutil.which(name)
    if path:
        return path, None
    raise SystemExit("ferramenta ausente: %s" % name)


def run_tool(name, args, tmp):
    exe, root = find_tool(name)
    env = dict(os.environ)
    if root:
        # Só libfdt: a libc de tools/root não deve substituir a do host.
        libdir = os.path.join(tmp, "libfdt")
        os.makedirs(libdir, exist_ok=True)
        src = os.path.join(root, "usr", "lib", "x86_64-linux-gnu")
        for f in os.listdir(src):
            if f.startswith("libfdt.so"):
                dst = os.path.join(libdir, f)
                if not os.path.exists(dst):
                    shutil.copy(os.path.join(src, f), dst)
        env["LD_LIBRARY_PATH"] = libdir
        if not os.access(exe, os.X_OK):
            copy = os.path.join(tmp, name)
            if not os.path.exists(copy):
                shutil.copy(exe, copy)
                os.chmod(copy, 0o755)
            exe = copy
    subprocess.run([exe] + args, check=True, env=env)


def build_from_flop(dts_dir, boards, rev, tmp):
    out, pins = {}, {}
    base_src = os.path.join(dts_dir, "exynos2100.dts")
    base = os.path.join(tmp, "base.dtb")
    run_tool("dtc", ["-q", "-I", "dts", "-O", "dtb", "-o", base, base_src], tmp)
    pins["exynos2100.dts"] = hashlib.sha256(pathlib.Path(base_src).read_bytes()).hexdigest()
    for b in boards:
        src = os.path.join(dts_dir, "samsung", b, "%s_eur_openx_w01_%s.dts" % (b, rev))
        dtbo, dtb = os.path.join(tmp, b + ".dtbo"), os.path.join(tmp, b + ".dtb")
        run_tool("dtc", ["-q", "-@", "-I", "dts", "-O", "dtb", "-o", dtbo, src], tmp)
        run_tool("fdtoverlay", ["-i", base, "-o", dtb, dtbo], tmp)
        pins[os.path.relpath(src, dts_dir)] = hashlib.sha256(pathlib.Path(src).read_bytes()).hexdigest()
        out[b] = pathlib.Path(dtb).read_bytes()
    return out, pins


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dtb", action="append", default=[], metavar="ROTULO=ARQ")
    ap.add_argument("--flop-dts", metavar="DIR")
    ap.add_argument("--boards", default="p3s,t2s")
    ap.add_argument("--rev", default="r17")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    sources = {}
    if a.flop_dts:
        with tempfile.TemporaryDirectory() as tmp:
            blobs, sources = build_from_flop(a.flop_dts, a.boards.split(","), a.rev, tmp)
        boards = [Board(k, v) for k, v in blobs.items()]
    else:
        if len(a.dtb) != 2:
            ap.error("informe exatamente dois --dtb ROTULO=ARQ ou --flop-dts")
        boards = []
        for spec in a.dtb:
            label, path = spec.split("=", 1)
            boards.append(Board(label, pathlib.Path(path).read_bytes()))
    target, ref = boards
    items = compare(target, ref)
    report = {
        "schema": "s21xnu-board-contract/1",
        "target": target.label, "reference": ref.label,
        "dtb_sha256": {target.label: target.sha256, ref.label: ref.sha256},
        "sources_sha256": sources, "rev": a.rev if a.flop_dts else None,
        "xnu_window": [hex(x) for x in XNU_WINDOW],
        "items": items,
        "summary": {s: sum(1 for i in items if i["status"] == s)
                    for s in ("igual", "difere", "ausente")},
    }
    for i in items:
        mark = {"igual": "=", "difere": "≠", "ausente": "?"}[i["status"]]
        line = "%s %-40s %s" % (mark, i["item"], i["status"])
        if i["status"] != "igual":
            line += "  %s=%s  %s=%s" % (target.label, i[target.label], ref.label, i[ref.label])
        print(line)
    print("resumo:", report["summary"])
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
