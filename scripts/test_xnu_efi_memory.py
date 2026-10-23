#!/usr/bin/env python3
"""Host counterexamples for the exact memory guard linked into the lab EFI."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.xnu import boot_contract as c
from lab.xnu import efi_memory as m
from scripts import test_xnu_contract as contract_fixture

PROBE = r'''
#include <stdio.h>
#include <stdlib.h>
#include "efi_memory.h"
static uint32_t u32(const unsigned char *p)
{ return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
int main(int argc,char **argv) {
    if (argc!=6) return 2;
    unsigned char raw[S21_MAP_CAPACITY+9];
    FILE *f=fopen(argv[1],"rb"); if (!f) return 2;
    size_t n=fread(raw,1,sizeof(raw),f); int error=ferror(f); fclose(f);
    if (error || n<8 || n>sizeof(raw)-1) return 2;
    struct s21_memory_map map={raw+8,n-8,u32(raw),u32(raw+4)};
    int valid=s21_memory_valid(&map),covered=0,largest=0; uint64_t base=0,size=0;
    if (valid) {
        covered=s21_memory_covers(&map,strtoull(argv[2],0,0),strtoull(argv[3],0,0),strtoul(argv[4],0,0));
        largest=s21_memory_largest(&map,strtoull(argv[5],0,0),&base,&size);
    }
    printf("{\"valid\":%d,\"covered\":%d,\"largest\":%d,\"base\":%llu,\"size\":%llu}\n",
        valid,covered,largest,(unsigned long long)base,(unsigned long long)size);
    return 0;
}
'''


def descriptor(base=0x40000000, size=0x4000000, kind=7, attributes=8, stride=48, pages=None):
    raw = struct.pack("<II4Q", kind, 0xdecafbad, base, 0, size // 4096 if pages is None else pages, attributes)
    return raw + b'\xa5' * (stride - 40)


def transcript(raw, stride=48, stage=0):
    lines = [f"S21 UEFI MAP {stage} {len(raw):x} 123 {stride:x} 1"]
    for i in range(len(raw) // stride):
        lines.append(f"S21 UEFI DESC {stage} {i:x} {raw[i*stride:(i+1)*stride].hex()}")
    lines.append(f"S21 UEFI END {stage}")
    return ('\r\n'.join(lines) + '\r\n').encode()


class MemoryGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="efi-memory-")
        cls.work = Path(cls.temp.name)
        (cls.work / "probe.c").write_text(PROBE)
        cls.probe = cls.work / "probe"
        subprocess.run(["cc", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-I", str(ROOT / "lab/xnu"),
                        str(cls.work / "probe.c"), str(ROOT / "lab/xnu/efi_memory.c"), "-o", str(cls.probe)],
                       check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, raw, *, stride=48, version=1, base=0x40000000, size=0x4000000, kind=7, limit=0x180000000):
        path = self.work / "input.bin"
        path.write_bytes(struct.pack("<II", stride, version) + raw)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1")
        result = json.loads(subprocess.check_output([str(self.probe), str(path), *map(str, (base, size, kind, limit))],
                                                   env=env, text=True, timeout=10))
        # Independent host decoder must agree on structural validity and coverage.
        try:
            decoded = m.Snapshot(raw, stride, version)
        except ValueError:
            self.assertEqual(result["valid"], 0)
        else:
            self.assertEqual(result["valid"], 1)
            if kind in (2, 7) and size and size <= (1 << 64) - 1 - base:
                self.assertEqual(bool(result["covered"]), decoded.covers(c.Span(base, size), kind))
        return result

    def test_descriptor_stride_and_extension_bytes(self):
        for stride in (40, 48, 64, 256):
            with self.subTest(stride=stride):
                self.assertEqual(self.check(descriptor(stride=stride), stride=stride)["covered"], 1)

    def test_unsorted_adjacent_owned_descriptors(self):
        raw = descriptor(0x42000000, 0x2000000, 2) + descriptor(0x40000000, 0x2000000, 2)
        self.assertEqual(self.check(raw, kind=2)["covered"], 1)

    def test_holes_and_wrong_types_are_not_covered(self):
        for tail in (descriptor(0x42001000, 0x1fff000), descriptor(0x42000000, 0x2000000, 4)):
            self.assertEqual(self.check(descriptor(size=0x2000000) + tail)["covered"], 0)

    def test_attributes_not_safe_for_our_allocations(self):
        for flag in (0, 0x1000, 0x2000, 0x20000, 1 << 63):
            attrs = 0 if flag == 0 else 8 | flag
            with self.subTest(attributes=attrs):
                result = self.check(descriptor(attributes=attrs))
                self.assertEqual((result["valid"], result["covered"], result["largest"]), (1, 0, 0))

    def test_overlapping_and_duplicate_descriptors(self):
        for other in (descriptor(), descriptor(0x41000000)):
            self.assertEqual(self.check(descriptor() + other)["valid"], 0)

    def test_zero_pages_alignment_type_and_address_overflow(self):
        for raw in (descriptor(pages=0), descriptor(base=0x40000001), descriptor(kind=16),
                    descriptor(pages=1 << 52), descriptor(base=0xfffffffffffff000, pages=1)):
            self.assertEqual(self.check(raw)["valid"], 0)

    def test_map_metadata_and_empty_input(self):
        for stride, version in ((0, 1), (32, 1), (41, 1), (264, 1), (48, 2)):
            self.assertEqual(self.check(descriptor(), stride=stride, version=version)["valid"], 0)
        self.assertEqual(self.check(b'')["valid"], 0)

    def test_every_truncated_descriptor(self):
        raw = descriptor()
        for n in range(len(raw)):
            self.assertEqual(self.check(raw[:n])["valid"], 0)

    def test_descriptor_count_and_buffer_limit(self):
        raw = b''.join(descriptor(0x40000000 + i * 4096, 4096) for i in range(1025))
        self.assertEqual(self.check(raw)["valid"], 0)
        self.assertEqual(self.check(b'\0' * 65536)["valid"], 0)

    def test_coverage_empty_overflow_or_unsupported_type(self):
        for base, size, kind in ((0x40000000, 0, 7), (0xfffffffffffff000, 0x2000, 7), (0x40000000, 4096, 4)):
            self.assertEqual(self.check(descriptor(), base=base, size=size, kind=kind)["covered"], 0)

    def test_selection_aligns_inward_and_respects_limit(self):
        result = self.check(descriptor(0x40001000, 0x7ffe000), limit=0x2000000)
        self.assertEqual((result["largest"], result["base"], result["size"]), (1, 0x42000000, 0x2000000))

    def test_selection_does_not_reclaim_reserved_or_loader_memory(self):
        for kind in (0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15):
            self.assertEqual(self.check(descriptor(kind=kind))["largest"], 0)

    def test_selection_tie_and_tiny_fragments(self):
        raw = descriptor(0x50000000) + descriptor(0x40000000)
        self.assertEqual(self.check(raw)["base"], 0x40000000)
        self.assertEqual(self.check(descriptor(size=4096))["largest"], 0)
        self.assertEqual(self.check(descriptor(), limit=4096)["largest"], 0)

    def test_lossless_serial_map_reconstruction(self):
        raw = descriptor() + descriptor(0x50000000, kind=2)
        snapshots, claims = m.parse_serial(transcript(raw))
        self.assertEqual(snapshots[0].raw, raw)
        self.assertEqual(claims, {})

    def test_serial_missing_duplicate_or_misnumbered_records(self):
        raw = transcript(descriptor())
        for bad in (raw + raw, raw.rsplit(b'S21 UEFI END', 1)[0],
                    raw.replace(b'DESC 0 0', b'DESC 0 1'), raw.replace(b'MAP 0 30', b'MAP 0 60'),
                    raw.replace(b'MAP 0', b'MAP -1'), raw.replace(b' 123 ', b' 10000000000000000 ')):
            with self.assertRaises(ValueError): m.parse_serial(bad)

    def test_cannot_infer_ownership_from_only_a_loader_descriptor(self):
        snapshot = m.Snapshot(descriptor(kind=2), 48, 1)
        with self.assertRaises(ValueError): m.verify({3: snapshot}, {}, None, None, 0, b'')


class OwnershipEvidence(unittest.TestCase):
    def fixture(self):
        args, tree, kernel = contract_fixture.fixture()
        payload_free = descriptor(m.PAYLOAD.base, m.PAYLOAD.size)
        payload_owned = descriptor(m.PAYLOAD.base, m.PAYLOAD.size, 2)
        window_free = descriptor(args.phys_base, args.mem_size)
        window_owned = descriptor(args.phys_base, args.mem_size, 2)
        maps = {i: m.Snapshot(raw, 48, 1) for i, raw in enumerate((payload_free + window_free,
            payload_owned + window_free, payload_owned + window_owned, payload_owned + window_owned))}
        claims = {name: {"base": base, "size": size, "status": 0, "returned": base}
                  for name, base, size in (("payload", m.PAYLOAD.base, m.PAYLOAD.size),
                                          ("window", args.phys_base, args.mem_size))}
        return maps, claims, args, tree, contract_fixture.BOOT_PA, kernel

    def test_complete_transition_and_boot_contract(self):
        profile, evidence = m.verify(*self.fixture())
        self.assertTrue(evidence["verified"])
        self.assertEqual(set(evidence["placements_checked"]), {"boot_args", "Apple DT", "__TEXT", "RAMDisk"})
        self.assertFalse(profile["hardware_ready"])

    def test_claim_status_or_returned_address_cannot_be_fabricated(self):
        for role, key, value in (("payload", "status", 1 << 63), ("window", "returned", 0),
                                  ("window", "size", 4096)):
            values = list(self.fixture()); values[1][role][key] = value
            with self.assertRaises(ValueError): m.verify(*values)

    def test_missing_stage_or_nonconventional_prior_window(self):
        values = list(self.fixture()); del values[0][0]
        with self.assertRaises(ValueError): m.verify(*values)
        values = list(self.fixture()); values[0][1] = values[0][2]
        with self.assertRaises(ValueError): m.verify(*values)

    def test_dropped_ownership_in_either_postclaim_map(self):
        for stage in (2, 3):
            values = list(self.fixture()); values[0][stage] = values[0][1]
            with self.assertRaises(ValueError): m.verify(*values)

    def test_boot_placement_must_match_uefi_owned_window(self):
        values = list(self.fixture()); values[4] = m.PAYLOAD.base
        with self.assertRaises(ValueError): m.verify(*values)

    def test_coalesced_loader_descriptor_is_accepted(self):
        # The real run merged these two adjacent claims into one descriptor.
        merged = m.Snapshot(descriptor(0xf0000000, 0xce000000, 2), 48, 1)
        self.assertTrue(merged.covers(m.PAYLOAD, 2))
        self.assertTrue(merged.covers(c.Span(0xf4000000, 0xca000000), 2))


if __name__ == '__main__':
    unittest.main(verbosity=1)
