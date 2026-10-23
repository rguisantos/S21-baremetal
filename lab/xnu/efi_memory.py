"""Decode complete UEFI snapshots emitted by our loader; no guessed RAM banks."""
from dataclasses import dataclass
import hashlib
import re
import struct
from . import boot_contract as c

CAPACITY = 65536
STAGES = ("payload-free", "window-free", "before-copy", "handoff")
PAYLOAD = c.Span(0xf0000000, 0x4000000)
FORBIDDEN = 0x8000000000023000  # runtime, RO, RP, WP


def require(value, message):
    if not value:
        raise c.ContractError(message)


@dataclass(frozen=True)
class Descriptor:
    kind: int
    physical: c.Span
    virtual: int
    attributes: int

    def usable(self, kind):
        return self.kind == kind and self.attributes & 8 and not self.attributes & FORBIDDEN


@dataclass
class Snapshot:
    raw: bytes
    stride: int
    version: int
    key: int = 0

    def __post_init__(self):
        require(self.version == 1 and 40 <= self.stride <= 256 and self.stride % 8 == 0,
                "unsupported UEFI descriptor version/stride")
        require(0 < len(self.raw) <= CAPACITY and len(self.raw) % self.stride == 0
                and len(self.raw) // self.stride <= 1024, "invalid UEFI map length/count")
        self.descriptors = []
        for offset in range(0, len(self.raw), self.stride):
            kind, _, base, virtual, pages, attribute = struct.unpack_from("<II4Q", self.raw, offset)
            require(kind <= 15 and base % 4096 == 0, "unsupported UEFI descriptor")
            self.descriptors.append(Descriptor(kind, c.Span(base, pages * 4096), virtual, attribute))
        ordered = sorted(self.descriptors, key=lambda d: d.physical.base)
        require(all(a.physical.end <= b.physical.base for a, b in zip(ordered, ordered[1:])),
                "overlapping UEFI descriptors")

    def covers(self, span, kind):
        cursor = span.base
        for descriptor in sorted(self.descriptors, key=lambda d: d.physical.base):
            region = descriptor.physical
            if region.end <= cursor:
                continue
            if cursor >= span.end:
                return True
            if region.base > cursor or not descriptor.usable(kind):
                return False
            cursor = region.end
        return cursor >= span.end

    def report(self):
        return {"bytes": len(self.raw), "descriptor_size": self.stride,
                "descriptor_version": self.version, "map_key": hex(self.key),
                "sha256": hashlib.sha256(self.raw).hexdigest(),
                "descriptor_count": len(self.descriptors),
                "descriptors": [{"type": d.kind, "physical": hex(d.physical.base),
                                 "size": hex(d.physical.size), "virtual": hex(d.virtual),
                                 "attributes": hex(d.attributes)} for d in self.descriptors]}


def parse_serial(serial):
    """Strict framing and full raw bytes, including firmware extension/padding."""
    require(len(serial) <= 4 * 1024 * 1024, "serial exceeds memory-audit limit")
    snapshots, claims, pending = {}, {}, None
    def hex_value(value):
        require(re.fullmatch(r"[0-9a-f]{1,16}", value) is not None, "invalid unsigned UEFI field")
        return int(value, 16)
    for line in serial.splitlines():
        if not line.startswith((b"S21 UEFI MAP ", b"S21 UEFI DESC ", b"S21 UEFI END ", b"S21 UEFI CLAIM ")):
            continue
        fields = line.decode("ascii").split()
        if fields[2] == "CLAIM":
            require(len(fields) == 8 and fields[3] in ("payload", "window") and fields[3] not in claims,
                    "invalid/duplicate UEFI claim record")
            claims[fields[3]] = dict(zip(("base", "size", "status", "returned"), (hex_value(x) for x in fields[4:])))
        elif fields[2] == "MAP":
            require(len(fields) == 8 and pending is None, "nested/invalid UEFI map")
            stage, size, key, stride, version = (hex_value(x) for x in fields[3:])
            require(stage < 4 and stage not in snapshots and 0 < size <= CAPACITY,
                    "duplicate/oversized UEFI map")
            require(40 <= stride <= 256 and stride % 8 == 0 and size % stride == 0 and version == 1,
                    "invalid UEFI map header")
            pending = (stage, size, key, stride, version, bytearray())
        elif fields[2] == "DESC":
            require(len(fields) == 6 and pending is not None, "orphan UEFI descriptor")
            stage, size, _, stride, _, raw = pending
            require(hex_value(fields[3]) == stage and hex_value(fields[4]) == len(raw) // stride
                    and len(fields[5]) == 2 * stride and len(raw) + stride <= size,
                    "invalid UEFI descriptor index/length")
            raw.extend(bytes.fromhex(fields[5]))
        else:
            require(len(fields) == 4 and pending is not None, "orphan UEFI map end")
            stage, size, key, stride, version, raw = pending
            require(hex_value(fields[3]) == stage and len(raw) == size, "incomplete UEFI snapshot")
            snapshots[stage] = Snapshot(bytes(raw), stride, version, key)
            pending = None
    require(pending is None, "missing UEFI map end")
    return snapshots, claims


def verify(snapshots, claims, args, tree, boot_pa, kernel, *, video_claim=None, resident_claim=None):
    require(set(snapshots) == set(range(4)) and set(claims) == {"payload", "window"},
            "all four UEFI stages and both allocation records are required")
    window = c.Span(args.phys_base, args.mem_size)
    for name, expected in (("payload", PAYLOAD), ("window", window)):
        claim = claims[name]
        require(claim == {"base": expected.base, "size": expected.size, "status": 0, "returned": expected.base},
                "UEFI allocation does not match the captured boot contract: " + name)
    require(not window.overlaps(PAYLOAD), "window overlaps payload")
    require(snapshots[0].covers(PAYLOAD, 7), "payload was not conventional before allocation")
    require(snapshots[1].covers(PAYLOAD, 2), "payload was not reserved before window selection")
    require(snapshots[1].covers(window, 7), "window was not conventional before allocation")
    for stage in (2, 3):
        require(snapshots[stage].covers(PAYLOAD, 2) and snapshots[stage].covers(window, 2),
                "UEFI ownership missing at " + STAGES[stage])
    # This complete GetMemoryMap snapshot supplies the declaration for the
    # existing contract checker. Do not reuse the synthetic FDT's RAM claim.
    before = snapshots[1]
    ram = [d.physical for d in before.descriptors if d.usable(7)]
    reserved = [d.physical for d in before.descriptors if not d.usable(7)]
    frame = None
    if video_claim is not None:
        from .video import verify_maps
        frame = verify_maps(args.video,snapshots,video_claim,window,PAYLOAD)
    profile = c.validate_profile(args, tree, boot_pa, kernel, ram=ram, reserved=reserved,
                                 protected=[PAYLOAD], complete=True,
                                 framebuffer=frame.allocation if frame else None)
    if frame:
        profile["video"] = {"base":hex(frame.allocation.base),"pixels_bytes":frame.pixels.size,
                            "allocation_bytes":frame.allocation.size,"width":frame.width,
                            "height":frame.height,"stride":frame.stride,"format":"XR24"}
    two_disks="RAMDisk1" in tree.at("/chosen/memory-map").properties
    require(two_disks == (resident_claim is not None), "resident declaration required for two-disk profile")
    if resident_claim is not None:
        from . import resident
        image=resident.allocation(resident_claim)
        require(image.base==window.base+resident.OFFSET and window.contains(image),
                "resident image outside canonical window")
        require(profile["placements"]["RAMDisk"]==[hex(image.base),hex(image.size)],
                "resident image is not the declared md0")
        require(snapshots[1].covers(image,7) and all(snapshots[i].covers(image,2) for i in (2,3)),
                "resident ownership missing")
        profile["resident"]={"base":hex(image.base),"bytes":resident_claim["size"],"allocation_bytes":image.size,
                             "root":"RAMDisk/md0","small_disk":"RAMDisk1/md1"}
    placements = {name: c.Span(*(int(x, 16) for x in values)) for name, values in profile["placements"].items()}
    for name, span in placements.items():
        require(all(snapshots[stage].covers(span, 2) for stage in (2, 3)),
                "placement not covered by loader-owned memory: " + name)
    profile["note"] = "Consistent with complete UEFI snapshots and successful exact-address allocations in this QEMU run."
    return profile, {"verified": True, "window": [hex(window.base), hex(window.size)],
                     "payload": [hex(PAYLOAD.base), hex(PAYLOAD.size)],
                     "claims": claims, "placements_checked": list(placements),
                     "snapshots": {STAGES[i]: snapshot.report() for i, snapshot in snapshots.items()},
                     "boot_services_resident": True, "exit_boot_services_called": False,
                     "scope": "UEFI-reported map and allocations during this QEMU execution; not Samsung RAM or CPU permissions",
                     "hardware_ready": False}
