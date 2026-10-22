"""Project explicit FDT resources into Apple DT; never allocate or boot.

The unchanged R10 C parser supplies RAM/reservations and resource ranges.
The existing bounded FDT reader supplies property provenance and PSCI/the
virtual timer binding. Independent views must agree before projection.
"""
import copy
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from . import boot_contract as c
from scripts.inspect_proton import fdt_nodes

ROOT = Path(__file__).resolve().parents[2]
MAX_FDT = 2 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise c.ContractError(message)


def build_probe(directory):
    probe = Path(directory) / "xnu-fdt-probe"
    subprocess.run(["cc", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", str(ROOT / "lab/xnu/fdt_probe.c"),
                    str(ROOT / "r8/r10_payload/fdt.c"), "-o", str(probe)],
                   check=True, timeout=30)
    return probe


def inspect_c(data, probe):
    require(40 <= len(data) <= MAX_FDT, "FDT size outside 2 MiB bound")
    with tempfile.TemporaryDirectory(prefix="xnu-fdt-input-") as directory:
        path = Path(directory) / "input.dtb"
        path.write_bytes(data)
        # LeakSanitizer cannot inspect threads under this traced host. ASan
        # address checks and UBSan remain enabled, as in the existing FDT tests.
        env = dict(os.environ,
                   ASAN_OPTIONS=os.environ.get("ASAN_OPTIONS", "") + ":detect_leaks=0",
                   UBSAN_OPTIONS=os.environ.get("UBSAN_OPTIONS", "") + ":halt_on_error=1")
        result = subprocess.run([str(probe), str(path)], check=True, timeout=10,
                                capture_output=True, text=True, env=env)
    output = json.loads(result.stdout)
    require(output["parse"] == 0, "production C parser: " + output["message"])
    return output


def strings(raw):
    require(isinstance(raw, bytes) and raw.endswith(b"\0"), "unterminated FDT string list")
    parts = raw[:-1].split(b"\0")
    require(all(parts), "empty FDT string-list member")
    try:
        return [part.decode("ascii") for part in parts]
    except UnicodeError as exc:
        raise c.ContractError("non-ASCII resource string") from exc


def be_cells(raw, count):
    require(isinstance(raw, bytes) and len(raw) == count * 4, "wrong FDT cell count")
    return struct.unpack(">" + "I" * count, raw)


def unpack_ranges(raw, address_cells, size_cells):
    width = 4 * (address_cells + size_cells)
    require(raw and len(raw) % width == 0, "incomplete FDT reg tuple")
    return [c.Span(int.from_bytes(raw[i:i + 4 * address_cells], "big"),
                   int.from_bytes(raw[i + 4 * address_cells:i + width], "big"))
            for i in range(0, len(raw), width)]


def le64(*values):
    return struct.pack("<" + "Q" * len(values), *values)


def node(name, properties=None, children=()):
    return c.Node({"name": name.encode("ascii") + b"\0", **(properties or {})}, list(children))


@dataclass
class Resources:
    source: dict
    ram: list
    reserved: list
    unresolved_reserved: bool
    initrd: list
    cpus: list
    frequency: int
    method: str
    gic: list
    provenance: dict
    timer: dict
    redist_stride: int

    def project(self):
        """A resource fragment, deliberately without DRAM/window/ramdisk/identity."""
        io_base = min(item.base for item in self.gic)
        io_size = max(item.end for item in self.gic) - io_base
        cpus = [node(f"cpu{index}", {"device_type": b"cpu\0",
                     "reg": struct.pack("<I", mpidr), "timebase-frequency": le64(self.frequency)})
                for index, mpidr in enumerate(self.cpus)]
        return node("device-tree", children=[
            node("chosen", {"psci-method": self.method.encode() + b"\0"}),
            node("cpus", children=cpus),
            node("arm-io", {"ranges": le64(0, io_base, io_size)}, [
                node("gic", {"device_type": b"interrupt-controller\0", "compatible": b"arm,gic-v3\0",
                              "reg": le64(self.gic[0].base - io_base, self.gic[0].size,
                                          self.gic[1].base - io_base, self.gic[1].size)})]),
        ])

    def report(self):
        blockers = []
        if not self.ram:
            blockers.append("no RAM banks in FDT")
        if self.unresolved_reserved:
            blockers.append("unresolved reserved-memory layout")
        return {"source": self.source, "resource_projection": True,
                "ram": [[hex(x.base), hex(x.size)] for x in self.ram],
                "reserved": [[hex(x.base), hex(x.size)] for x in self.reserved],
                "unresolved_reserved": self.unresolved_reserved,
                "initrd": [[hex(x.base), hex(x.size)] for x in self.initrd],
                "initrd_interpretation": "Linux end-exclusive declaration; no rounding or off-by-one correction",
                "cpus": [hex(x) for x in self.cpus], "psci_method": self.method,
                "counter_frequency_from_fdt": self.frequency,
                "gic": [[hex(x.base), hex(x.size)] for x in self.gic],
                "redist_stride_from_fdt": hex(self.redist_stride),
                "timer": self.timer, "provenance": self.provenance,
                "memory_description_blockers": blockers,
                "memory_ownership_verified": False, "load_plan_generated": False, "hardware_ready": False,
                "runtime_requirements": ["owned RAM window and complete effective reservations",
                    "Samsung load path, entry state and cache coherence",
                    "ICC access, virtual timer permissions and effective CNTFRQ",
                    "redistributor discovery by affinity, not inferred stride", "recoverable output channel"],
                "scope": "Static resources from supplied FDT; frequency is nominal; no MMIO or SMC/HVC executed"}


def extract(data, probe):
    parsed = inspect_c(data, probe)
    try:
        nodes = fdt_nodes(data)
    except (ValueError, struct.error) as exc:
        raise c.ContractError("bounded FDT reader: " + str(exc)) from exc
    require(len(nodes) <= 4096 and sum(len(v) for v in nodes.values()) <= 32768,
            "FDT node/property limit")
    root = nodes["/"]
    ac, = be_cells(root.get("#address-cells"), 1)
    sc, = be_cells(root.get("#size-cells"), 1)
    require(ac in (1, 2) and sc in (1, 2), "explicit root cells 1 or 2 required")

    def active(path):
        parts = path.strip("/").split("/")
        return all(nodes["/" + "/".join(parts[:i])].get("status", b"okay\0") in (b"ok\0", b"okay\0")
                   for i in range(len(parts) + 1))

    def one_compatible(names):
        matches = [(path, props) for path, props in nodes.items() if "compatible" in props
                   and active(path) and set(strings(props["compatible"])) & set(names)]
        require(len(matches) == 1, "missing/ambiguous compatible: " + ",".join(names))
        path, props = matches[0]
        require(path.count("/") == 1, "resource must be at root: " + path)
        return path, props

    # Do not use a platform default for the calling convention or frequency.
    psci_path, psci = one_compatible(("arm,psci-0.2", "arm,psci-1.0"))
    method_parts = strings(psci.get("method", b""))
    require(len(method_parts) == 1 and method_parts[0] in ("smc", "hvc"), "unsupported PSCI method")
    gic_path, gic = one_compatible(("arm,gic-v3",))
    gic_ranges = unpack_ranges(gic.get("reg", b""), ac, sc)
    require(len(gic_ranges) == 2 and parsed["have_gic"], "two GIC ranges required")
    c_gic = [c.Span(int(a, 16), int(n, 16)) for a, n in parsed["gic"]]
    require(gic_ranges == c_gic, "GIC ranges disagree with production parser")
    require(not gic_ranges[0].overlaps(gic_ranges[1]), "GIC ranges overlap")
    ram = [c.Span(int(a, 16), int(n, 16)) for a, n in parsed["ram"]]
    io = c.Span(min(x.base for x in gic_ranges), max(x.end for x in gic_ranges) - min(x.base for x in gic_ranges))
    require(not any(bank.overlaps(io) for bank in ram), "GIC covering I/O range overlaps RAM")
    timer_path, timer = one_compatible(("arm,armv8-timer",))
    raw_interrupts = timer.get("interrupts", b"")
    require(len(raw_interrupts) >= 36 and len(raw_interrupts) % 12 == 0, "timer requires virtual PPI tuple")
    kind, irq, flags = struct.unpack_from(">III", raw_interrupts, 24)
    require(kind == 1 and irq == 11 and (flags & 15) in (4, 8), "pinned XNU requires virtual timer INTID 27, level")
    require(parsed["have_timer"] and parsed["timer_parent"] == parsed["gic_phandle"],
            "timer parent differs from GIC")
    frequency, = be_cells(timer.get("clock-frequency"), 1)
    require(frequency and frequency == parsed["timer_frequency"], "explicit nonzero counter frequency required")
    require(timer.get("use-physical-timer", b"") == b"", "invalid use-physical-timer flag")
    cpu_paths, cpus = [], []
    cpu_root = nodes.get("/cpus", {})
    cac, = be_cells(cpu_root.get("#address-cells"), 1)
    csc, = be_cells(cpu_root.get("#size-cells"), 1)
    require(cac in (1, 2) and csc == 0, "unsupported CPU cells")
    for path, props in nodes.items():
        if path.rsplit("/", 1)[0] != "/cpus" or not active(path) or props.get("device_type") != b"cpu\0":
            continue
        be_cells(props.get("reg"), cac)
        mpidr = int.from_bytes(props["reg"], "big")
        c.integer(mpidr, 32)
        require(props.get("enable-method") == b"psci\0", "explicit CPU enable-method=psci required")
        cpu_paths.append(path)
        cpus.append(mpidr)
    require(1 <= len(cpus) <= 8 and len(cpus) == len(set(cpus)), "unsupported CPU count/duplicate MPIDR")
    require(cpus == [int(x, 16) for x in parsed["cpus"]], "CPU order/MPIDR differs from production parser")
    provenance = {"/chosen/psci-method": {"node": psci_path, "property": "method"},
        "/arm-io/gic/reg": {"node": gic_path, "property": "reg", "parent_address_cells": ac,
                            "parent_size_cells": sc, "endianness": "big to little"},
        "/cpus/*/reg": {"nodes_in_order": cpu_paths, "property": "reg", "parent_address_cells": cac,
                         "endianness": "big to little, require u32"},
        "/cpus/*/timebase-frequency": {"node": timer_path, "property": "clock-frequency",
                                       "interpretation": "nominal FDT value, not measured CNTFRQ"}}
    return Resources({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}, ram,
        [c.Span(int(a, 16), int(n, 16)) for a, n in parsed["reserved"]],
        bool(parsed["unresolved_reserved"]), [c.Span(int(a, 16), int(n, 16)) for a, n in parsed["initrd"]],
        cpus, frequency, method_parts[0], gic_ranges, provenance,
        {"node": timer_path, "physical_intid": parsed["timer_irq"], "virtual_intid": irq + 16,
         "virtual_flags_from_fdt": hex(flags), "linux_use_physical_timer": "use-physical-timer" in timer},
        int(parsed["redist_stride"], 16))


def validate_candidate(resources, args, template, boot_args_pa, kernel, *, complete, protected):
    """Host fixture only: caller supplies placements and completeness, never inferred.

    No raw output is written. Resources replace old CPU/I/O bindings; other
    template nodes remain the caller's responsibility. Original Linux initrd
    is protected in addition to reservations and explicit live inputs.
    """
    require(resources.ram, "cannot build a candidate without FDT RAM banks")
    require(not resources.unresolved_reserved, "cannot build a candidate with unresolved reservations")
    tree = copy.deepcopy(template)
    projection = resources.project()
    for name in ("cpus", "arm-io"):
        tree.children = [child for child in tree.children if child.name != name]
        tree.children.append(projection.at("/" + name))
    tree.at("/chosen").properties["psci-method"] = resources.method.encode() + b"\0"
    args = replace(args, tree_size=len(c.encode_tree(tree)))
    checked = c.validate_profile(args, tree, boot_args_pa, kernel, ram=resources.ram,
        reserved=resources.reserved, protected=[*resources.initrd, *protected], complete=complete)
    return args, tree, checked
