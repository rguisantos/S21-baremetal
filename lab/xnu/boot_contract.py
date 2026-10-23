"""Bounded host codec and consistency checks for the pinned XNU boot profile.

This is a specification component, not a loader or proof of memory ownership.
All physical RAM/reservations must come from an explicit caller declaration.
No FDT is converted automatically and no hardware is accessed.
"""
from dataclasses import dataclass
import struct

U64_MAX = (1 << 64) - 1
PAGE = 0x4000
BASE_ALIGNMENT = 0x2000000
BOOT_SIZE = 736
TREE_LIMIT = 65536
MAX_NODES = 256
MAX_PROPERTIES = 2048
MAX_DEPTH = 16
OFFSETS = {
    "Revision": 0, "Version": 2, "virtBase": 8, "physBase": 16,
    "memSize": 24, "topOfKernelData": 32, "Video": 40,
    "machineType": 88, "deviceTreeP": 96, "deviceTreeLength": 104,
    "CommandLine": 108, "bootFlags": 720, "memSizeActual": 728,
}


class ContractError(ValueError):
    pass


def integer(value, bits=64):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ContractError(f"unsigned {bits}-bit integer required")
    return value


def cstring(value, limit):
    if not isinstance(value, bytes) or not value or len(value) > limit:
        raise ContractError("invalid C string size")
    head, separator, tail = value.partition(b"\0")
    if not separator or any(tail):
        raise ContractError("unterminated string or nonzero suffix")
    try:
        return head.decode("ascii")
    except UnicodeError as exc:
        raise ContractError("ASCII string required") from exc


@dataclass(frozen=True)
class Span:
    base: int
    size: int

    def __post_init__(self):
        integer(self.base)
        integer(self.size)
        if not self.size or self.size > U64_MAX - self.base:
            raise ContractError("empty or overflowing interval")

    @property
    def end(self):
        return self.base + self.size

    def contains(self, other):
        return self.base <= other.base and other.end <= self.end

    def overlaps(self, other):
        return self.base < other.end and other.base < self.end


@dataclass(frozen=True)
class BootArgs:
    virt_base: int
    phys_base: int
    mem_size: int
    top: int
    video: tuple
    machine_type: int
    tree_va: int
    tree_size: int
    cmdline: str
    boot_flags: int
    mem_size_actual: int

    def encode(self):
        fields = (self.virt_base, self.phys_base, self.mem_size, self.top,
                  self.tree_va, self.boot_flags, self.mem_size_actual)
        for value in fields:
            integer(value)
        integer(self.machine_type, 32)
        integer(self.tree_size, 32)
        if len(self.video) != 6:
            raise ContractError("six video fields required")
        for value in self.video:
            integer(value)
        try:
            command = self.cmdline.encode("ascii")
        except (AttributeError, UnicodeError) as exc:
            raise ContractError("ASCII command line required") from exc
        if b"\0" in command or len(command) >= 608:
            raise ContractError("command line must fit 607 bytes without NUL")
        out = bytearray(BOOT_SIZE)
        struct.pack_into("<HH", out, 0, 2, 2)
        struct.pack_into("<4Q", out, 8, *fields[:4])
        struct.pack_into("<6Q", out, 40, *self.video)
        struct.pack_into("<I", out, 88, self.machine_type)
        struct.pack_into("<QI", out, 96, self.tree_va, self.tree_size)
        out[108:108 + len(command)] = command
        struct.pack_into("<QQ", out, 720, self.boot_flags, self.mem_size_actual)
        return bytes(out)

    @classmethod
    def decode(cls, data):
        if len(data) != BOOT_SIZE:
            raise ContractError("boot_args must contain exactly 736 bytes")
        if struct.unpack_from("<HH", data) != (2, 2):
            raise ContractError("only revision 2 / version 2 supported")
        if any(data[4:8] + data[92:96] + data[716:720]):
            raise ContractError("nonzero ABI padding is outside this profile")
        return cls(*struct.unpack_from("<4Q", data, 8),
                   struct.unpack_from("<6Q", data, 40),
                   struct.unpack_from("<I", data, 88)[0],
                   *struct.unpack_from("<QI", data, 96),
                   cstring(data[108:716], 608),
                   *struct.unpack_from("<QQ", data, 720))

    def physical(self, virtual, size):
        integer(virtual)
        if virtual < self.virt_base:
            raise ContractError("virtual pointer below the linear window")
        offset = virtual - self.virt_base
        if size <= 0 or offset >= self.mem_size or size > self.mem_size - offset:
            raise ContractError("virtual span outside the linear window")
        return Span(self.phys_base + offset, size)


@dataclass
class Node:
    properties: dict
    children: list

    @property
    def name(self):
        if "name" not in self.properties:
            raise ContractError("node without a name property")
        name = cstring(self.properties["name"], 64)
        if not name or "/" in name:
            raise ContractError("invalid node name")
        return name

    def at(self, path):
        node = self
        for part in path.strip("/").split("/") if path.strip("/") else ():
            matches = [child for child in node.children if child.name == part]
            if len(matches) != 1:
                raise ContractError(f"missing or ambiguous Apple DT node: {path}")
            node = matches[0]
        return node


def decode_tree(data):
    if not 8 <= len(data) <= TREE_LIMIT or len(data) % 4:
        raise ContractError("Apple DT size/alignment outside bounded profile")
    cursor = nodes = properties = 0

    def take(size):
        nonlocal cursor
        if size < 0 or size > len(data) - cursor:
            raise ContractError("truncated Apple DT")
        value = data[cursor:cursor + size]
        cursor += size
        return value

    def visit(depth):
        nonlocal nodes, properties
        if depth > MAX_DEPTH:
            raise ContractError("Apple DT depth limit")
        nodes += 1
        if nodes > MAX_NODES:
            raise ContractError("Apple DT node limit")
        count, children = struct.unpack("<II", take(8))
        if not count or count > MAX_PROPERTIES - properties or children > MAX_NODES - nodes:
            raise ContractError("Apple DT count limit")
        properties += count
        props = {}
        for _ in range(count):
            header = take(36)
            key = cstring(header[:32], 32)
            if not key or key in props:
                raise ContractError("empty or duplicate Apple DT property")
            size = struct.unpack_from("<I", header, 32)[0]
            value = take(size)
            if any(take(-size % 4)):
                raise ContractError("nonzero property padding outside canonical profile")
            props[key] = value
        node = Node(props, [visit(depth + 1) for _ in range(children)])
        node.name
        names = [child.name for child in node.children]
        if len(names) != len(set(names)):
            raise ContractError("duplicate child names")
        return node

    result = visit(1)
    if cursor != len(data):
        raise ContractError("trailing data after Apple DT")
    return result


def encode_tree(node):
    """Encode a canonical tree; the bounded decoder checks the full result."""
    pieces = []
    total = nodes = properties = 0

    def emit(value):
        nonlocal total
        total += len(value)
        if total > TREE_LIMIT:
            raise ContractError("Apple DT size limit")
        pieces.append(value)

    def visit(item, depth):
        nonlocal nodes, properties
        nodes += 1
        properties += len(item.properties)
        if depth > MAX_DEPTH or nodes > MAX_NODES or properties > MAX_PROPERTIES:
            raise ContractError("Apple DT construction limit")
        emit(struct.pack("<II", len(item.properties), len(item.children)))
        for key, value in item.properties.items():
            try:
                name = key.encode("ascii")
            except (AttributeError, UnicodeError) as exc:
                raise ContractError("invalid property name") from exc
            if not 1 <= len(name) <= 31 or b"\0" in name or not isinstance(value, bytes):
                raise ContractError("invalid property name/value")
            emit(struct.pack("<32sI", name, len(value)))
            emit(value)
            emit(b"\0" * (-len(value) % 4))
        for child in item.children:
            visit(child, depth + 1)

    visit(node, 1)
    data = b"".join(pieces)
    decode_tree(data)
    return data


def cells(node, key, count, bits=64):
    data = node.properties.get(key)
    if not isinstance(data, bytes) or len(data) != count * (bits // 8):
        raise ContractError(f"wrong size or missing property: {key}")
    return struct.unpack("<" + ("Q" if bits == 64 else "I") * count, data)


def kernel_segments(data, args):
    if len(data) < 32 or len(data) > 32 * 1024 * 1024:
        raise ContractError("kernel Mach-O size limit")
    magic, cpu, _, kind, count, length, _, _ = struct.unpack_from("<8I", data)
    if (magic, cpu, kind) != (0xFEEDFACF, 0x100000C, 2) or not 1 <= count <= 256:
        raise ContractError("not a supported arm64 kernel Mach-O")
    if length > len(data) - 32:
        raise ContractError("truncated Mach-O commands")
    cursor, result = 32, []
    for _ in range(count):
        if cursor + 8 > 32 + length:
            raise ContractError("truncated Mach-O command")
        command, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or size % 8 or size > 32 + length - cursor:
            raise ContractError("invalid Mach-O command size")
        if command == 0x19:
            if size < 72:
                raise ContractError("short segment command")
            name, va, memory, offset, file_size, _, _, sections, _ = struct.unpack_from(
                "<16s4Q4I", data, cursor + 8)
            if 72 + sections * 80 != size or file_size > memory or offset > len(data) or file_size > len(data) - offset:
                raise ContractError("invalid Mach-O segment bounds")
            if memory:
                span = args.physical(va, memory)
                if any(span.overlaps(other) for _, other in result):
                    raise ContractError("overlapping Mach-O segments")
                try:
                    label = name.rstrip(b"\0").decode("ascii")
                except UnicodeError as exc:
                    raise ContractError("non-ASCII segment name") from exc
                if not label or any(label == other for other, _ in result):
                    raise ContractError("empty or duplicate segment name")
                result.append((label, span))
        cursor += size
    if cursor != 32 + length or not result:
        raise ContractError("incomplete Mach-O segment list")
    return result


def validate_profile(args, tree, boot_args_pa, kernel, *, ram, reserved,
                     protected, complete, framebuffer=None):
    """Check one declared linear window. Never establishes physical trust."""
    args.encode()
    if complete is not True or not ram:
        raise ContractError("RAM/reservations declaration is incomplete")
    if args.machine_type or args.boot_flags:
        raise ContractError("unsupported machine/boot flags")
    if any(args.video):
        if framebuffer is None:
            raise ContractError("explicit framebuffer declaration required")
        from .video import decode
        if framebuffer != decode(args.video).allocation:
            raise ContractError("explicit framebuffer declaration required")
    elif framebuffer is not None:
        raise ContractError("framebuffer declaration with headless arguments")
    window = Span(args.phys_base, args.mem_size)
    if args.phys_base % BASE_ALIGNMENT or args.virt_base % BASE_ALIGNMENT or args.mem_size % PAGE:
        raise ContractError("linear window alignment")
    Span(args.virt_base, args.mem_size)
    if not any(bank.contains(window) for bank in ram):
        raise ContractError("window crosses a hole or lies outside declared RAM")
    for i, bank in enumerate(ram):
        if any(bank.overlaps(other) for other in ram[i + 1:]):
            raise ContractError("overlapping RAM banks")
    if framebuffer is not None and (window.overlaps(framebuffer) or
            any(framebuffer.overlaps(item) for item in protected)):
        raise ContractError("framebuffer overlaps window or protected input")
    if any(window.overlaps(item) for item in tuple(reserved) + tuple(protected)):
        raise ContractError("window overlaps reservations or protected input")
    if args.mem_size_actual < args.mem_size:
        raise ContractError("memSizeActual smaller than window")
    if args.top % PAGE or not window.base < args.top <= window.end:
        raise ContractError("invalid topOfKernelData")
    if boot_args_pa % 8 or not 8 <= args.tree_size <= TREE_LIMIT:
        raise ContractError("boot_args or tree size/alignment")
    encoded_tree = encode_tree(tree)
    if len(encoded_tree) != args.tree_size:
        raise ContractError("deviceTreeLength mismatch")
    tree_span = args.physical(args.tree_va, args.tree_size)
    if tree_span.base % 4:
        raise ContractError("Apple DT pointer alignment")
    placed = [("boot_args", Span(boot_args_pa, BOOT_SIZE)), ("Apple DT", tree_span)]
    placed += kernel_segments(kernel, args)
    memory_map = tree.at("/chosen/memory-map")
    allowed = {"name", "RAMDisk", "RAMDisk1"}
    if set(memory_map.properties) - allowed or "RAMDisk" not in memory_map.properties:
        raise ContractError("unsupported memory-map profile")
    for name in ("RAMDisk", "RAMDisk1"):
        if name in memory_map.properties:
            span = Span(*cells(memory_map, name, 2))
            if span.base % PAGE or span.size % PAGE:
                raise ContractError("RAM disk alignment")
            placed.append((name, span))
    if len({name for name, _ in placed}) != len(placed):
        raise ContractError("duplicate placement roles")
    for i, (name, span) in enumerate(placed):
        if not window.contains(span) or span.end > args.top:
            raise ContractError(f"{name} outside window or above topOfKernelData")
        if any(span.overlaps(other) for _, other in placed[i + 1:]):
            raise ContractError(f"{name} overlaps another placement")
    chosen = tree.at("/chosen")
    if cells(chosen, "dram-base", 1)[0] != args.phys_base or cells(chosen, "dram-size", 1)[0] != args.mem_size:
        raise ContractError("Apple DT DRAM differs from boot_args")
    method = cstring(chosen.properties.get("psci-method", b""), 4)
    if method not in ("smc", "hvc"):
        raise ContractError("unsupported PSCI method")
    io = tree.at("/arm-io")
    child, io_base, io_size = cells(io, "ranges", 3)
    if child != 0:
        raise ContractError("nonzero child I/O base unsupported")
    io_span = Span(io_base, io_size)
    gic_node = tree.at("/arm-io/gic")
    if cstring(gic_node.properties.get("compatible", b""), 64) != "arm,gic-v3":
        raise ContractError("GICv3 compatible required")
    dist, dist_size, redist, redist_size = cells(gic_node, "reg", 4)
    gic = [Span(io_base + dist, dist_size), Span(io_base + redist, redist_size)]
    if any(not io_span.contains(item) or window.overlaps(item) for item in gic) or gic[0].overlaps(gic[1]):
        raise ContractError("GIC ranges conflict with I/O window or RAM window")
    if any(bank.overlaps(io_span) for bank in ram):
        raise ContractError("declared I/O window overlaps RAM")
    cpus = []
    for cpu in tree.at("/cpus").children:
        mpidr, = cells(cpu, "reg", 1, bits=32)
        frequency, = cells(cpu, "timebase-frequency", 1)
        if not frequency or mpidr in cpus:
            raise ContractError("missing counter frequency or duplicate MPIDR")
        cpus.append(mpidr)
    if not 1 <= len(cpus) <= 8:
        raise ContractError("CPU count outside pinned loader profile")
    return {"profile_consistent": True, "hardware_ready": False,
            "window": [hex(window.base), hex(window.size)],
            "placements": {name: [hex(span.base), hex(span.size)] for name, span in placed},
            "gic": [[hex(span.base), hex(span.size)] for span in gic],
            "cpus": [hex(mpidr) for mpidr in cpus], "psci_method": method,
            "note": "Consistency with supplied declarations; no allocation, firmware or ownership proof."}
