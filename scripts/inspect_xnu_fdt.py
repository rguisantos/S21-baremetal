#!/usr/bin/env python3
"""Read a raw FDT into a resource-only Apple DT; no boot_args or load plan."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.xnu import boot_contract as c
from lab.xnu import fdt_adapter as adapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fdt", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="new inspection directory")
    args = parser.parse_args()
    try:
        with args.fdt.open("rb") as stream:
            data = stream.read(adapter.MAX_FDT + 1)
        adapter.require(40 <= len(data) <= adapter.MAX_FDT, "FDT size outside 2 MiB bound")
        args.out.mkdir(parents=True, exist_ok=False)
        resources = adapter.extract(data, adapter.build_probe(args.out))
        raw = c.encode_tree(resources.project())
        adapter.require(c.encode_tree(c.decode_tree(raw)) == raw, "resource tree round-trip failed")
        (args.out / "apple-resources.adt").write_bytes(raw)
        report = resources.report()
        report["apple_resource_tree"] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                                         "exact_roundtrip": True, "bootable": False}
        report["source_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            "lab/xnu/fdt_adapter.py", "lab/xnu/fdt_probe.c", "r8/r10_payload/fdt.c", "r8/r10_payload/fdt.h",
            "lab/xnu/boot_contract.py", "scripts/inspect_proton.py", "tools/mkpayload.py", "scripts/inspect_xnu_fdt.py")}
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"inspect_xnu_fdt: {exc}\n")
    print(f"RESOURCE PROJECTION PASS: {len(resources.cpus)} CPUs; {len(resources.ram)} RAM banks; no load plan")
    print(args.out / "report.json")


if __name__ == "__main__":
    main()
