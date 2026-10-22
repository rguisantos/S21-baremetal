#!/usr/bin/env python3
"""Synthetic FDT -> Apple resource tests, with the production parser sanitized."""
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.xnu import boot_contract as c
from lab.xnu import fdt_adapter as a
from scripts import test_fdt as dt

PBASE, VBASE = 0x40000000, 0xFFFFFFF004000000


def fixture(ac=2):
    def reg(base, size):
        return (dt.u64(base) if ac == 2 else dt.u32(base)) + dt.u32(size)
    return dt.node("", {"#address-cells": dt.u32(ac), "#size-cells": dt.u32(1),
                       "interrupt-parent": dt.u32(1)}, [
        dt.node("memory@40000000", {"device_type": dt.text("memory"), "reg": reg(PBASE, 0x20000000)}),
        dt.node("reserved-memory", {"#address-cells": dt.u32(ac), "#size-cells": dt.u32(1), "ranges": b""}, [
            dt.node("firmware@5f000000", {"reg": reg(0x5F000000, 0x1000000)})]),
        dt.node("cpus", {"#address-cells": dt.u32(2), "#size-cells": dt.u32(0)}, [
            dt.node(f"cpu@{i << 8:x}", {"device_type": dt.text("cpu"), "reg": dt.u64(i << 8),
                                       "enable-method": dt.text("psci")}) for i in range(8)]),
        dt.node("gic@10200000", {"compatible": dt.text("arm,gic-v3"),
            "reg": reg(0x10200000, 0x10000) + reg(0x10240000, 0x200000),
            "phandle": dt.u32(1), "#interrupt-cells": dt.u32(3), "interrupt-controller": b""}),
        dt.node("timer", {"compatible": dt.text("arm,armv8-timer"),
            "interrupts": dt.u32(1, 13, 0xff08, 1, 14, 0xff08, 1, 11, 0xff08, 1, 10, 0xff08),
            "clock-frequency": dt.u32(26000000), "use-physical-timer": b""}),
        dt.node("psci", {"compatible": dt.text("arm,psci-1.0"), "method": dt.text("smc")}),
        dt.node("chosen", {"linux,initrd-start": dt.u32(0x58000000), "linux,initrd-end": dt.u32(0x58400000)}),
    ])


def child(tree, name):
    return next(n for n in tree[2] if n[0] == name)


def template():
    tree = a.node("device-tree", children=[a.node("chosen", {
        "dram-base": a.le64(PBASE), "dram-size": a.le64(0x10000000)}, [
        a.node("memory-map", {"RAMDisk": a.le64(PBASE + 0x03100000, 0x4000)})]),
        a.node("cpus", children=[a.node("old-cpu", {"reg": struct.pack("<I", 999)})]),
        a.node("arm-io", children=[a.node("old-uart", {"compatible": b"arm,pl011\0"})])])
    args = c.BootArgs(VBASE, PBASE, 0x10000000, PBASE + 0x03400000, (0,) * 6, 0,
                      VBASE + 0x03200000, 0, "cpus=1 rd=md0", 0, 0x10000000)
    header = struct.pack("<8I", 0xFEEDFACF, 0x100000C, 0, 2, 1, 72, 0, 0)
    segment = struct.pack("<II16s4Q4I", 0x19, 72, b"__TEXT", VBASE + 0x03004000,
                          0x4000, 0, 0x4000, 5, 5, 0, 0)
    return args, tree, (header + segment).ljust(0x4000, b"\0")


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix="xnu-adapter-tests-")
        cls.probe = a.build_probe(cls.work.name)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def extract(self, tree=None, reservations=((0x5E000000, 0x1000),)):
        return a.extract(dt.encode(fixture() if tree is None else tree, reservations), self.probe)

    def candidate(self, resource=None, *, complete=True, protected=()):
        return a.validate_candidate(resource or self.extract(), *template()[:2],
             PBASE + 0x03210000, template()[2], complete=complete, protected=protected)

    def test_projection_preserves_gic_size_and_endianness(self):
        resource = self.extract()
        tree = resource.project()
        self.assertEqual(c.cells(tree.at("/arm-io/gic"), "reg", 4), (0, 0x10000, 0x40000, 0x200000))
        self.assertEqual(c.cells(tree.at("/arm-io"), "ranges", 3), (0, 0x10200000, 0x240000))
        self.assertEqual(resource.cpus, [i << 8 for i in range(8)])
        self.assertEqual(tree.at("/cpus").children[1].properties["reg"], b"\0\x01\0\0")
        self.assertEqual(c.cells(tree.at("/cpus").children[0], "timebase-frequency", 1), (26000000,))

    def test_resource_fragment_is_not_a_boot_tree(self):
        tree = self.extract().project()
        self.assertNotIn("dram-base", tree.at("/chosen").properties)
        self.assertNotIn("model", tree.properties)
        with self.assertRaises(c.ContractError): tree.at("/chosen/memory-map")
        raw = c.encode_tree(tree)
        self.assertEqual(c.encode_tree(c.decode_tree(raw)), raw)

    def test_provenance_and_nominal_timer(self):
        report = self.extract().report()
        self.assertEqual(report["provenance"]["/chosen/psci-method"]["node"], "/psci")
        self.assertEqual(report["timer"]["physical_intid"], 30)
        self.assertEqual(report["timer"]["virtual_intid"], 27)
        self.assertTrue(report["timer"]["linux_use_physical_timer"])
        self.assertEqual(report["redist_stride_from_fdt"], "0x0")
        self.assertFalse(report["memory_ownership_verified"])
        self.assertFalse(report["hardware_ready"])

    def test_header_and_node_reservations_and_initrd_preserved(self):
        resource = self.extract()
        self.assertEqual(resource.reserved, [c.Span(0x5E000000, 0x1000), c.Span(0x5F000000, 0x1000000)])
        self.assertEqual(resource.initrd, [c.Span(0x58000000, 0x400000)])

    def test_unaligned_initrd_end_is_not_rounded_or_reused(self):
        tree = fixture(); child(tree, "chosen")[1]["linux,initrd-end"] = dt.u32(0x581FFFFF)
        resource = self.extract(tree)
        self.assertEqual(resource.initrd, [c.Span(0x58000000, 0x1FFFFF)])
        with self.assertRaises(c.ContractError): resource.project().at("/chosen/memory-map")

    def test_root_one_address_cell(self):
        self.assertEqual(self.extract(fixture(1)).gic, self.extract().gic)

    def test_ram_above_four_gib_is_preserved(self):
        tree = fixture()
        tree[2].append(dt.node("memory@8e0000000", {"device_type": dt.text("memory"),
                                                 "reg": dt.u64(0x8E0000000) + dt.u32(0x10000000)}))
        self.assertEqual(self.extract(tree).ram[-1], c.Span(0x8E0000000, 0x10000000))

    def test_no_ram_projects_but_refuses_candidate(self):
        tree = fixture(); tree[2].pop(0)
        resource = self.extract(tree)
        self.assertEqual(resource.ram, [])
        self.assertIn("no RAM banks in FDT", resource.report()["memory_description_blockers"])
        with self.assertRaisesRegex(c.ContractError, "RAM banks"): self.candidate(resource)

    def test_dynamic_reservation_projects_but_refuses_candidate(self):
        tree = fixture()
        child(tree, "reserved-memory")[2].append(dt.node("dynamic", {"size": dt.u32(0x100000)}))
        resource = self.extract(tree)
        self.assertTrue(resource.unresolved_reserved)
        with self.assertRaisesRegex(c.ContractError, "unresolved"): self.candidate(resource)

    def test_disabled_cpu_is_not_projected(self):
        tree = fixture(); child(tree, "cpus")[2][2][1]["status"] = dt.text("disabled")
        self.assertNotIn(0x200, self.extract(tree).cpus)

    def test_duplicate_cpu_is_rejected(self):
        tree = fixture(); child(tree, "cpus")[2][1][1]["reg"] = dt.u64(0)
        with self.assertRaises(c.ContractError): self.extract(tree)

    def test_cpu_aff3_cannot_be_truncated_to_u32(self):
        tree = fixture(); child(tree, "cpus")[2][0][1]["reg"] = dt.u64(0x100000000)
        with self.assertRaises(c.ContractError): self.extract(tree)

    def test_missing_cpu_enable_method_has_no_default(self):
        tree = fixture(); del child(tree, "cpus")[2][0][1]["enable-method"]
        with self.assertRaisesRegex(c.ContractError, "enable-method"): self.extract(tree)

    def test_psci_smc_hvc_and_missing_method(self):
        for method in ("smc", "hvc"):
            tree = fixture(); child(tree, "psci")[1]["method"] = dt.text(method)
            self.assertEqual(self.extract(tree).method, method)
        tree = fixture(); del child(tree, "psci")[1]["method"]
        with self.assertRaises(c.ContractError): self.extract(tree)

    def test_disabled_or_duplicate_psci_is_rejected(self):
        for duplicate in (False, True):
            tree = fixture()
            if duplicate:
                other = copy.deepcopy(child(tree, "psci")); other[0] = "psci-two"; tree[2].append(other)
            else: child(tree, "psci")[1]["status"] = dt.text("disabled")
            with self.subTest(duplicate=duplicate), self.assertRaises(c.ContractError): self.extract(tree)

    def test_missing_or_zero_counter_has_no_platform_fallback(self):
        for value in (None, dt.u32(0)):
            tree = fixture()
            if value is None: del child(tree, "timer")[1]["clock-frequency"]
            else: child(tree, "timer")[1]["clock-frequency"] = value
            with self.subTest(value=value), self.assertRaises(c.ContractError): self.extract(tree)

    def test_virtual_timer_irq_and_trigger_are_checked(self):
        for values in ((1, 12, 8), (0, 11, 8), (1, 11, 1)):
            tree = fixture(); raw = bytearray(child(tree, "timer")[1]["interrupts"])
            struct.pack_into(">III", raw, 24, *values); child(tree, "timer")[1]["interrupts"] = bytes(raw)
            with self.subTest(values=values), self.assertRaises(c.ContractError): self.extract(tree)

    def test_timer_parent_must_match_gic(self):
        tree = fixture(); child(tree, "timer")[1]["interrupt-parent"] = dt.u32(3)
        with self.assertRaises(c.ContractError): self.extract(tree)

    def test_nested_gic_bus_is_not_assumed_identity(self):
        tree = fixture(); gic = child(tree, "gic@10200000"); tree[2].remove(gic)
        tree[2].append(dt.node("soc", {"#address-cells": dt.u32(2), "#size-cells": dt.u32(1)}, [gic]))
        with self.assertRaises(c.ContractError): self.extract(tree)

    def test_extra_gic_ranges_are_not_silently_dropped(self):
        tree = fixture(); child(tree, "gic@10200000")[1]["reg"] += dt.u64(0x10400000) + dt.u32(0x1000)
        with self.assertRaises(c.ContractError): self.extract(tree)

    def test_overlap_of_gic_or_ram_is_rejected(self):
        tree = fixture(); child(tree, "gic@10200000")[1]["reg"] = (
            dt.u64(0x10200000) + dt.u32(0x10000) + dt.u64(0x10200000) + dt.u32(0x200000))
        with self.assertRaises(c.ContractError): self.extract(tree)

    def test_malformed_fdt_and_trailing_bytes_are_rejected(self):
        raw = dt.encode(fixture())
        for data in (b"", raw[:39], raw[:-1], raw + b"\0", b"\0" * 40):
            with self.subTest(size=len(data)), self.assertRaises(c.ContractError): a.extract(data, self.probe)

    def test_synthetic_candidate_drops_old_uart_and_preserves_inputs(self):
        args, tree, result = self.candidate(protected=[c.Span(0x5D000000, 0x100000)])
        self.assertEqual(result["psci_method"], "smc")
        self.assertEqual(result["gic"][1], ["0x10240000", "0x200000"])
        self.assertEqual(args.tree_size, len(c.encode_tree(tree)))
        self.assertEqual([x.name for x in tree.at("/arm-io").children], ["gic"])
        self.assertEqual([x.name for x in template()[1].at("/arm-io").children], ["old-uart"])
        self.assertFalse(result["hardware_ready"])

    def test_candidate_requires_explicit_completeness(self):
        with self.assertRaises(c.ContractError): self.candidate(complete=False)

    def test_candidate_refuses_reservation_inside_window(self):
        resource = self.extract(reservations=((PBASE + 0x10000, 0x1000),))
        with self.assertRaises(c.ContractError): self.candidate(resource)

    def test_candidate_protects_original_linux_initrd(self):
        tree = fixture(); child(tree, "chosen")[1]["linux,initrd-start"] = dt.u32(PBASE + 0x10000)
        child(tree, "chosen")[1]["linux,initrd-end"] = dt.u32(PBASE + 0x20000)
        with self.assertRaises(c.ContractError): self.candidate(self.extract(tree))

    def test_candidate_protects_live_fdt_or_loader_buffers(self):
        with self.assertRaises(c.ContractError): self.candidate(protected=[c.Span(PBASE + 0x10000, 0x1000)])

    def test_candidate_does_not_merge_banks_across_a_hole(self):
        tree = fixture(); child(tree, "memory@40000000")[1]["reg"] = dt.u64(PBASE) + dt.u32(0x8000000)
        tree[2].append(dt.node("memory@50000000", {"device_type": dt.text("memory"),
                                                 "reg": dt.u64(0x50000000) + dt.u32(0x10000000)}))
        with self.assertRaises(c.ContractError): self.candidate(self.extract(tree))

    def test_cli_creates_fragment_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory); fdt = work / "test.dtb"; out = work / "out"
            fdt.write_bytes(dt.encode(fixture()))
            command = [sys.executable, str(ROOT / "scripts/inspect_xnu_fdt.py"), str(fdt), "--out", str(out)]
            first = subprocess.run(command, capture_output=True, text=True, timeout=40)
            self.assertEqual(first.returncode, 0, first.stderr)
            report = (out / "report.json").read_bytes()
            self.assertFalse(json.loads(report)["load_plan_generated"])
            self.assertFalse(json.loads(report)["apple_resource_tree"]["bootable"])
            self.assertEqual(subprocess.run(command, capture_output=True, timeout=10).returncode, 2)
            self.assertEqual((out / "report.json").read_bytes(), report)


if __name__ == "__main__":
    unittest.main(verbosity=1)
