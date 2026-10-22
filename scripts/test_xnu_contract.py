#!/usr/bin/env python3
"""Host contract tests; optionally compare layout with the exact Apple header.

All memory in fixtures is synthetic. These tests neither boot a kernel nor
establish memory ownership on Samsung. The separate capture tool reads QEMU.
"""
import argparse
import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("s21_boot_contract_tests", ROOT / "lab/xnu/boot_contract.py")
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)
HEADER_SHA = "efdfec46319cb147297682a8faebe02873f845261b57f7511ab8e15c13ef3439"
VBASE = 0xFFFFFFF004000000
PBASE = 0x40000000
BOOT_PA = PBASE + 0x03210000


def q(*values):
    return struct.pack("<" + "Q" * len(values), *values)


def node(name, properties=None, children=()):
    return c.Node({"name": name.encode() + b"\0", **(properties or {})}, list(children))


def kernel_image(segments=(("__TEXT", VBASE + 0x03004000, 0x4000),)):
    commands = b"".join(struct.pack("<II16s4Q4I", 0x19, 72, name.encode(),
                                   va, size, 0, 0x4000, 5, 5, 0, 0)
                        for name, va, size in segments)
    header = struct.pack("<8I", 0xFEEDFACF, 0x100000C, 0, 2, len(segments), len(commands), 0, 0)
    return (header + commands).ljust(0x4000, b"\0")


def fixture():
    tree = node("device-tree", children=[
        node("chosen", {"dram-base": q(PBASE), "dram-size": q(0x10000000), "psci-method": b"hvc\0"}, [
            node("memory-map", {"RAMDisk": q(PBASE + 0x03100000, 0x4000)})]),
        node("cpus", children=[node("cpu0", {"reg": struct.pack("<I", 0), "timebase-frequency": q(62500000)})]),
        node("arm-io", {"ranges": q(0, 0x08000000, 0x08000000)}, [
            node("gic", {"compatible": b"arm,gic-v3\0", "reg": q(0, 0x10000, 0xa0000, 0x100000)})]),
    ])
    args = c.BootArgs(VBASE, PBASE, 0x10000000, PBASE + 0x03400000, (0,) * 6, 0,
                      VBASE + 0x03200000, len(c.encode_tree(tree)), "cpus=1 rd=md0", 0, 0x10000000)
    return args, tree, kernel_image()


def validate(args, tree, kernel, *, update_tree=True, **kwargs):
    if update_tree:
        args = replace(args, tree_size=len(c.encode_tree(tree)))
    options = {"ram": [c.Span(PBASE, 0x10000000)], "reserved": [], "protected": [], "complete": True}
    options.update(kwargs)
    return c.validate_profile(args, tree, options.pop("boot_args_pa", BOOT_PA), kernel, **options)


def verify_header(path):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != HEADER_SHA:
        raise ValueError("Apple boot.h hash mismatch")
    with tempfile.TemporaryDirectory(prefix="xnu-layout-") as directory:
        work = Path(directory)
        (work / "boot.h").write_bytes(data)
        (work / "pexpert/arm").mkdir(parents=True)
        # Those headers do not define the LP64 fields under test. Keep the
        # original boot.h untouched and stub only its unrelated includes.
        for name in ("consistent_debug.h", "protos.h"):
            (work / "pexpert/arm" / name).write_text("/* layout-only include stub */\n")
        code = ['#include <stdint.h>', '#include <stddef.h>', '#include <stdio.h>', '#include "boot.h"',
                'int main(void) { printf("{\\"sizeof\\":%zu", sizeof(boot_args));']
        for name in c.OFFSETS:
            code.append(f'printf(",\\"{name}\\":%zu", offsetof(boot_args, {name}));')
        code += ['printf(",\\"Boot_Video_size\\":%zu}", sizeof(Boot_Video)); return 0; }']
        (work / "layout.c").write_text("\n".join(code))
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(work),
                        str(work / "layout.c"), "-o", str(work / "layout")], check=True, timeout=20)
        result = json.loads(subprocess.check_output([str(work / "layout")], text=True, timeout=5))
    expected = {"sizeof": c.BOOT_SIZE, **c.OFFSETS, "Boot_Video_size": 48}
    if result != expected:
        raise ValueError(f"LP64 layout differs: {result}")
    return result


class CodecTests(unittest.TestCase):
    def test_boot_args_offsets_and_roundtrip(self):
        args, _, _ = fixture()
        raw = args.encode()
        self.assertEqual(len(raw), 736)
        self.assertEqual(struct.unpack_from("<Q", raw, 96)[0], args.tree_va)
        self.assertEqual(raw[108:122], b"cpus=1 rd=md0\0")
        self.assertEqual(c.BootArgs.decode(raw), args)

    def test_boot_args_size_version_and_padding(self):
        raw = fixture()[0].encode()
        bad_version = bytearray(raw); bad_version[0] = 1
        bad_padding = bytearray(raw); bad_padding[92] = 1
        for data in (raw[:-1], raw + b"x", bytes(bad_version), bytes(bad_padding)):
            with self.subTest(length=len(data)), self.assertRaises(c.ContractError):
                c.BootArgs.decode(data)

    def test_command_line_boundaries(self):
        args = fixture()[0]
        self.assertEqual(c.BootArgs.decode(replace(args, cmdline="x" * 607).encode()).cmdline, "x" * 607)
        for text in ("x" * 608, "a\0b", "não"):
            with self.subTest(text=text[:8]), self.assertRaises(c.ContractError):
                replace(args, cmdline=text).encode()

    def test_unterminated_command_is_rejected(self):
        raw = bytearray(fixture()[0].encode()); raw[108:716] = b"x" * 608
        with self.assertRaises(c.ContractError):
            c.BootArgs.decode(raw)

    def test_integer_and_range_limits(self):
        for base, size in ((0, 0), (-1, 1), (c.U64_MAX, 1), (True, 16)):
            with self.subTest(base=base, size=size), self.assertRaises(c.ContractError):
                c.Span(base, size)

    def test_virtual_pointer_does_not_wrap(self):
        args = fixture()[0]
        for address, size in ((VBASE - 1, 1), (VBASE + args.mem_size, 1),
                              (VBASE + args.mem_size - 4, 8)):
            with self.subTest(address=address), self.assertRaises(c.ContractError):
                args.physical(address, size)

    def test_tree_roundtrip_and_little_endian_header(self):
        tree = fixture()[1]; raw = c.encode_tree(tree)
        self.assertEqual(struct.unpack_from("<II", raw), (1, 3))
        self.assertEqual(c.encode_tree(c.decode_tree(raw)), raw)

    def test_every_truncated_tree_prefix_is_rejected(self):
        raw = c.encode_tree(fixture()[1])
        for size in range(len(raw)):
            with self.subTest(size=size), self.assertRaises(c.ContractError):
                c.decode_tree(raw[:size])

    def test_duplicate_properties_and_child_names(self):
        prop = struct.pack("<32sI", b"name", 2) + b"r\0\0\0"
        raw = struct.pack("<II", 2, 0) + prop + prop
        with self.assertRaises(c.ContractError):
            c.decode_tree(raw)
        with self.assertRaises(c.ContractError):
            c.encode_tree(node("root", children=[node("same"), node("same")]))

    def test_missing_name_and_nonzero_padding(self):
        with self.assertRaises(c.ContractError):
            c.encode_tree(c.Node({"foo": b"bar"}, []))
        raw = bytearray(c.encode_tree(node("root", {"foo": b"x"}))); raw[-1] = 1
        with self.assertRaises(c.ContractError):
            c.decode_tree(raw)

    def test_depth_count_and_property_length_limits(self):
        tree = node("last")
        for _ in range(c.MAX_DEPTH):
            tree = node("parent", children=[tree])
        with self.assertRaises(c.ContractError):
            c.encode_tree(tree)
        for raw in (struct.pack("<II", 0xFFFFFFFF, 0),
                    struct.pack("<II32sI", 1, 0, b"name", 0xFFFFFFFF)):
            with self.subTest(raw=raw), self.assertRaises(c.ContractError):
                c.decode_tree(raw)

    def test_raw_fdt_and_trailing_data_are_rejected(self):
        for raw in (b"\xd0\x0d\xfe\xed" + b"\0" * 36,
                    c.encode_tree(fixture()[1]) + b"\0" * 4):
            with self.subTest(raw=raw[:8]), self.assertRaises(c.ContractError):
                c.decode_tree(raw)

    def test_unterminated_property_name(self):
        raw = struct.pack("<II32sI", 1, 0, b"n" * 32, 0)
        with self.assertRaises(c.ContractError):
            c.decode_tree(raw)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.args, self.tree, self.kernel = fixture()

    def check(self, args=None, tree=None, kernel=None, **kwargs):
        return validate(args or self.args, tree or self.tree, kernel or self.kernel, **kwargs)

    def test_consistent_fixture_does_not_authorize_hardware(self):
        result = self.check()
        self.assertTrue(result["profile_consistent"])
        self.assertFalse(result["hardware_ready"])

    def test_missing_or_incomplete_memory_is_rejected(self):
        for kwargs in ({"complete": False}, {"ram": []}):
            with self.subTest(kwargs=kwargs), self.assertRaises(c.ContractError):
                self.check(**kwargs)

    def test_holes_and_overlapping_ram_are_rejected(self):
        for banks in ([c.Span(PBASE, 0x8000000), c.Span(PBASE + 0x8004000, 0x7ffc000)],
                      [c.Span(PBASE, 0x10000000), c.Span(PBASE + 0x4000, 0x4000)]):
            with self.subTest(banks=banks), self.assertRaises(c.ContractError):
                self.check(ram=banks)

    def test_reservations_and_protected_inputs_are_rejected(self):
        for kind in ("reserved", "protected"):
            with self.subTest(kind=kind), self.assertRaises(c.ContractError):
                self.check(**{kind: [c.Span(PBASE + 0x4000, 0x4000)]})

    def test_touching_intervals_do_not_overlap(self):
        self.check(protected=[c.Span(PBASE - 0x4000, 0x4000)])

    def test_tree_args_disk_and_kernel_overlap_are_rejected(self):
        with self.assertRaises(c.ContractError):
            self.check(boot_args_pa=PBASE + 0x03200000)
        for address in (PBASE + 0x03004000, BOOT_PA):
            tree = copy.deepcopy(self.tree)
            tree.at("/chosen/memory-map").properties["RAMDisk"] = q(address, 0x4000)
            with self.subTest(address=address), self.assertRaises(c.ContractError):
                self.check(tree=tree)

    def test_top_alignment_and_truncated_window(self):
        for args in (replace(self.args, top=PBASE + 0x4000), replace(self.args, top=self.args.top + 1),
                     replace(self.args, phys_base=PBASE + 1), replace(self.args, mem_size=1)):
            with self.subTest(args=args), self.assertRaises(c.ContractError):
                self.check(args=args)

    def test_actual_ram_total_does_not_authorize_a_window(self):
        args = replace(self.args, mem_size_actual=12 << 30)
        with self.assertRaises(c.ContractError):
            self.check(args=args, ram=[c.Span(PBASE, 0x8000000)])

    def test_wrong_tree_length_and_physical_pointer(self):
        for args in (replace(self.args, tree_size=self.args.tree_size + 4),
                     replace(self.args, tree_va=PBASE + 0x03200000)):
            with self.subTest(args=args), self.assertRaises(c.ContractError):
                self.check(args=args, update_tree=False)

    def test_dram_tree_must_agree_with_args(self):
        tree = copy.deepcopy(self.tree); tree.at("/chosen").properties["dram-size"] = q(1)
        with self.assertRaises(c.ContractError):
            self.check(tree=tree)

    def test_samsung_resource_values_preserved_in_synthetic_fixture(self):
        tree = copy.deepcopy(self.tree)
        tree.at("/chosen").properties["psci-method"] = b"smc\0"
        tree.at("/arm-io").properties["ranges"] = q(0, 0x10000000, 0x10000000)
        tree.at("/arm-io/gic").properties["reg"] = q(0x200000, 0x10000, 0x240000, 0x200000)
        tree.at("/cpus").children = [node(f"cpu{i}", {"reg": struct.pack("<I", i << 8),
                                          "timebase-frequency": q(26000000)}) for i in range(8)]
        result = self.check(tree=tree)
        self.assertEqual(result["gic"][1], ["0x10240000", "0x200000"])
        self.assertEqual(result["cpus"], [hex(i << 8) for i in range(8)])
        self.assertEqual(result["psci_method"], "smc")
        self.assertFalse(result["hardware_ready"])

    def test_duplicate_cpu_and_missing_frequency(self):
        for change in ("duplicate", "zero-frequency"):
            tree = copy.deepcopy(self.tree)
            if change == "duplicate":
                extra = copy.deepcopy(tree.at("/cpus").children[0]); extra.properties["name"] = b"cpu1\0"
                tree.at("/cpus").children.append(extra)
            else:
                tree.at("/cpus").children[0].properties["timebase-frequency"] = q(0)
            with self.subTest(change=change), self.assertRaises(c.ContractError):
                self.check(tree=tree)

    def test_gic_range_and_compatible_errors(self):
        for values in (q(0, 0x10000, 0, 0x10000), q(0, 0x10000, 0x9000000, 0x20000)):
            tree = copy.deepcopy(self.tree); tree.at("/arm-io/gic").properties["reg"] = values
            with self.subTest(values=values), self.assertRaises(c.ContractError):
                self.check(tree=tree)
        tree = copy.deepcopy(self.tree); tree.at("/arm-io/gic").properties["compatible"] = b"arm,gic-v2\0"
        with self.assertRaises(c.ContractError):
            self.check(tree=tree)

    def test_unvalidated_video_and_memory_map_are_rejected(self):
        with self.assertRaises(c.ContractError):
            self.check(args=replace(self.args, video=(1, 0, 0, 0, 0, 0)))
        tree = copy.deepcopy(self.tree); tree.at("/chosen/memory-map").properties["unknown"] = q(1, 1)
        with self.assertRaises(c.ContractError):
            self.check(tree=tree)

    def test_macho_bounds_and_segment_overlap(self):
        bad = bytearray(self.kernel); struct.pack_into("<Q", bad, 32 + 48, len(bad) + 1)
        zero = bytearray(self.kernel); struct.pack_into("<I", zero, 36, 0)
        overlap = kernel_image((("__TEXT", VBASE + 0x03004000, 0x4000),
                                ("__DATA", VBASE + 0x03004000, 0x4000)))
        for image in (bytes(bad), bytes(zero), overlap):
            with self.subTest(size=len(image)), self.assertRaises(c.ContractError):
                self.check(kernel=image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apple-boot-header", type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not result.wasSuccessful():
        return 1
    if args.apple_boot_header:
        print("APPLE_LAYOUT_JSON=" + json.dumps(verify_header(args.apple_boot_header), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
