#!/usr/bin/env python3
"""Testes do verificador de contrato s21xnu e do parse_fdt legado, com FDT sintéticos."""
import contextlib
import io
import json
import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s21xnu_board_contract as sbc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def be(*w):
    return struct.pack(">%dI" % len(w), *w)


def cstr(*s):
    return b"".join(x.encode() + b"\0" for x in s)


def fdt(tree):
    """tree = (nome, {prop: bytes}, [filhos]) -> blob FDT v17."""
    strings, offs, out = bytearray(), {}, bytearray()

    def soff(k):
        if k not in offs:
            offs[k] = len(strings)
            strings.extend(k.encode() + b"\0")
        return offs[k]

    def emit(node):
        name, props, kids = node
        out.extend(be(1))
        n = name.encode() + b"\0"
        out.extend(n + b"\0" * (-len(n) % 4))
        for k, v in props.items():
            out.extend(be(3, len(v), soff(k)))
            out.extend(v + b"\0" * (-len(v) % 4))
        for c in kids:
            emit(c)
        out.extend(be(2))

    emit(tree)
    out.extend(be(9))
    rsv = be(0, 0, 0, 0)
    off_rsv = 40
    off_struct = off_rsv + len(rsv)
    off_str = off_struct + len(out)
    total = off_str + len(strings)
    hdr = be(0xD00DFEED, total, off_struct, off_str, off_rsv, 17, 16, 0, len(strings), len(out))
    return hdr + rsv + bytes(out) + bytes(strings)


def board(model, panel_modes, ep_ver, touch_pins=("gpp4-0", "gpp4-1"), reserved=None):
    ph = iter(range(0x10, 0x100))
    P = {}

    def pin(label, *names):
        P[label] = next(ph)
        return (label, {"samsung,pins": cstr(*names), "phandle": be(P[label])}, [])

    pinctrl = ("pinctrl@10430000", {}, [
        pin("tspi2c-bus", *touch_pins), pin("hsi2c5-bus", "gpp0-2", "gpp0-3"),
        pin("hsi2c6-bus", "gpp1-0", "gpp1-1"), pin("attn_irq", "gpa1-0"),
        pin("key-volup", "gpa0-3"), pin("key-voldown", "gpa0-4"),
        pin("pcie0_clkreq", "gpf0-0")])
    P["ldo2"], P["ldo3"] = next(ph), next(ph)
    s2dos = ("hsi2c@10560000", {"pinctrl-0": be(P["hsi2c5-bus"])}, [
        ("s2dos05_pmic@60", {"compatible": cstr("samsung,s2dos05pmic"), "reg": be(0x60)}, [
            ("regulators", {}, [
                ("s2dos05-ldo2", {"regulator-name": cstr("tsp_io"),
                                  "regulator-min-microvolt": be(1800000), "phandle": be(P["ldo2"])}, []),
                ("s2dos05-ldo3", {"regulator-name": cstr("tsp_avdd"),
                                  "regulator-min-microvolt": be(3000000), "phandle": be(P["ldo3"])}, [])])])])
    touch = ("hsi2c@105D0000", {"pinctrl-0": be(P["tspi2c-bus"])}, [
        ("touchscreen@48", {"compatible": cstr("slsi,slsi_ts"), "reg": be(0x48),
                            "pinctrl-0": be(P["attn_irq"]), "tsp_io_ldo-supply": be(P["ldo2"]),
                            "tsp_avdd_ldo-supply": be(P["ldo3"]), "sec,max_coords": be(4096, 4096),
                            "sec,firmware_name": cstr("y792_%s.bin" % model)}, [])])
    mx = ("hsi2c@10570000", {"pinctrl-0": be(P["hsi2c6-bus"])}, [
        ("max77705@66", {"compatible": cstr("maxim,max77705"), "reg": be(0x66)}, [])])
    keys = ("gpio_keys", {"compatible": cstr("gpio-keys"),
                          "pinctrl-0": be(P["key-voldown"], P["key-volup"])}, [
        ("button@2", {"linux,code": be(114)}, []), ("button@3", {"linux,code": be(115)}, [])])
    pcie = ("pcie@113B0000", {"ep-ver": be(ep_ver), "max-link-speed": be(1),
                              "pinctrl-0": be(P["pcie0_clkreq"])}, [])
    gic = ("interrupt-controller@10200000", {"compatible": cstr("arm,gic-v3"),
                                              "reg": be(0, 0x10200000, 0x10000, 0, 0x10240000, 0x200000)}, [])
    mali = ("mali@18500000", {"compatible": cstr("arm,mali"), "reg": be(0, 0x18500000, 0x5000)}, [])
    ufs = ("ufs@0x13100000", {"compatible": cstr("samsung,exynos-ufs"), "reg": be(0, 0x13100000, 0x200)}, [])
    cpus = ("cpus", {"#address-cells": be(2), "#size-cells": be(0)}, [
        ("cpu@%d00" % i, {"device_type": cstr("cpu"), "reg": be(0, i * 0x100)}, []) for i in range(8)])
    modes = ("%s_panel_display_modes" % model, {}, [
        ("%s_panel_display_mode_%s_60hs" % (model, m), {}, []) for m in panel_modes])
    rsv_children = [("cp_rmem", {"reg": be(0x8, 0x80000000, 0xd800000)}, [])]
    if reserved:
        rsv_children.append(("intruso", {"reg": be(reserved >> 32, reserved & 0xffffffff, 0x100000)}, []))
    rsv = ("reserved-memory", {"#address-cells": be(2), "#size-cells": be(1)}, rsv_children)
    root = ("", {"#address-cells": be(2), "#size-cells": be(1), "model": cstr(model)},
            [pinctrl, s2dos, touch, mx, keys, pcie, gic, mali, ufs, cpus, modes, rsv])
    return fdt(root)


class ParseTests(unittest.TestCase):
    def test_rejects_bad_magic_and_truncation(self):
        blob = board("t2s", ["1080x2400"], 0x4375)
        with self.assertRaisesRegex(ValueError, "magic"):
            sbc.parse_fdt(b"\0" * 4 + blob[4:])
        with self.assertRaisesRegex(ValueError, "totalsize"):
            sbc.parse_fdt(blob[:-8])
        with self.assertRaisesRegex(ValueError, "truncado"):
            sbc.parse_fdt(blob[:12])

    def test_rejects_unbalanced_structure(self):
        good = board("t2s", ["1080x2400"], 0x4375)
        # troca o último END_NODE (antes de FDT_END) por NOP: nó raiz fica aberto
        idx = good.rindex(be(2) + be(9))
        bad = good[:idx] + be(4) + good[idx + 4:]
        with self.assertRaisesRegex(ValueError, "nó aberto"):
            sbc.parse_fdt(bad)

    def test_reg_uses_parent_cells(self):
        b = sbc.Board("x", board("t2s", ["1080x2400"], 0x4375))
        gic = b.first_compat("arm,gic-v3")
        self.assertEqual(sbc.reg_pairs(b, gic), [(0x10200000, 0x10000), (0x10240000, 0x200000)])


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.t2s = sbc.Board("t2s", board("t2s", ["1080x2400"], 0x4375))

    def statuses(self, target):
        return {i["item"]: i["status"] for i in sbc.compare(target, self.t2s)}

    def test_identical_boards_are_all_equal(self):
        clone = sbc.Board("clone", board("t2s", ["1080x2400"], 0x4375))
        st = self.statuses(clone)
        self.assertTrue(st)
        self.assertEqual(set(st.values()), {"igual"})

    def test_p3s_like_differences_are_reported(self):
        p3s = sbc.Board("p3s", board("p3s", ["720x1600", "1080x2400", "1440x3200"], 0x4389))
        st = self.statuses(p3s)
        for k in ("panel.max_mode", "wifi.pcie_ep_ver", "touch.firmware"):
            self.assertEqual(st[k], "difere", k)
        for k in ("touch.bus_pins", "touch.attn_pins", "touch.io_supply", "s2dos05.bus_pins",
                  "max77705.bus_pins", "keys.pins", "gic.reg", "mali.reg", "ufs.reg", "cpu.mpidr",
                  "memory.fixed_reserved_in_xnu_window"):
            self.assertEqual(st[k], "igual", k)
        mode = [i for i in sbc.compare(p3s, self.t2s) if i["item"] == "panel.max_mode"][0]
        self.assertEqual(mode["p3s"], "1440x3200")
        self.assertIn("1080x2400", mode["s21xnu"])

    def test_moved_touch_pins_are_flagged(self):
        moved = sbc.Board("m", board("t2s", ["1080x2400"], 0x4375, touch_pins=("gpp5-0", "gpp5-1")))
        self.assertEqual(self.statuses(moved)["touch.bus_pins"], "difere")

    def test_reserved_region_inside_xnu_window_is_flagged(self):
        r = sbc.Board("r", board("t2s", ["1080x2400"], 0x4375, reserved=0x900000000))
        item = [i for i in sbc.compare(r, self.t2s) if i["item"] == "memory.fixed_reserved_in_xnu_window"][0]
        self.assertEqual(item["status"], "difere")
        self.assertEqual(item["r"], ["intruso 0x900000000+0x100000"])

    def test_missing_resource_is_absent_not_equal(self):
        stripped = sbc.Board("s", fdt(("", {"#address-cells": be(2), "#size-cells": be(1)}, [])))
        st = self.statuses(stripped)
        self.assertEqual(set(st.values()), {"ausente"})


class CliTests(unittest.TestCase):
    def test_cli_writes_json_with_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            a, b, j = (os.path.join(d, n) for n in ("p.dtb", "t.dtb", "r.json"))
            pathlib.Path(a).write_bytes(board("p3s", ["1440x3200"], 0x4389))
            pathlib.Path(b).write_bytes(board("t2s", ["1080x2400"], 0x4375))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = sbc.main(["--dtb", "p3s=" + a, "--dtb", "t2s=" + b, "--json", j])
            self.assertEqual(rc, 0)
            self.assertIn("resumo:", out.getvalue())
            rep = json.loads(pathlib.Path(j).read_text())
            self.assertEqual(rep["schema"], "s21xnu-board-contract/1")
            self.assertEqual(len(rep["dtb_sha256"]["p3s"]), 64)
            self.assertGreater(rep["summary"]["difere"], 0)

    def test_cli_requires_two_boards(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            sbc.main(["--dtb", "x=y"])


class LegacyParseFdtTests(unittest.TestCase):
    """parse_fdt.py tinha FDT_PROP/FDT_END_NODE trocados e lia a versão no campo errado."""

    def test_reads_version_tokens_and_cells(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.dtb")
            pathlib.Path(p).write_bytes(board("t2s", ["1080x2400"], 0x4375))
            out = subprocess.run([sys.executable, os.path.join(HERE, "parse_fdt.py"), p],
                                 capture_output=True, text=True, check=True).stdout
        self.assertIn("# FDT v17", out)
        self.assertIn("/interrupt-controller@10200000", out)
        self.assertIn("reg: 0x10200000..0x1020ffff (size 0x10000)", out)
        self.assertIn("reg: 0x10240000..0x1043ffff (size 0x200000)", out)
        self.assertIn("compatible: ['slsi,slsi_ts']", out)


if __name__ == "__main__":
    unittest.main()
