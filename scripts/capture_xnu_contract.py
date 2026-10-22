#!/usr/bin/env python3
"""Read boot_args/Apple DT at arm_init in QEMU; resume and require lab PASS.

Requires a successful run_xnu_lab directory with matching source/artifact
hashes. QEMU arguments are constructed here, never executed from its JSON.
Creates fresh FAT/NVRAM and uses only GDB read commands and breakpoints.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
# _arm_init in the exact SHA-256 checked prebuilt; not a Samsung address.
ARM_INIT = 0xFFFFFFF007453994


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


lab = load("s21_xnu_lab", ROOT / "scripts/run_xnu_lab.py")
contract = load("s21_xnu_contract", ROOT / "lab/xnu/boot_contract.py")


class Reader:
    def __init__(self, process, timeout):
        self.process, self.deadline = process, time.monotonic() + timeout
        self.buffer = bytearray()
        self.command("?")

    def byte(self):
        if not self.buffer:
            left = self.deadline - time.monotonic()
            if left <= 0 or not select.select([self.process.stdout], [], [], left)[0]:
                raise TimeoutError("GDB read deadline")
            self.buffer.extend(os.read(self.process.stdout.fileno(), 4096))
            if not self.buffer:
                raise ValueError("GDB disconnected")
        result = self.buffer[0]
        del self.buffer[0]
        return result

    def send(self, text):
        data = text.encode("ascii")
        self.process.stdin.write(b"$" + data + b"#" + f"{sum(data) % 256:02x}".encode())
        self.process.stdin.flush()

    def packet(self):
        while self.byte() != ord("$"):
            pass
        out = bytearray()
        while (byte := self.byte()) != ord("#"):
            if len(out) >= 16384:
                raise ValueError("oversized GDB packet")
            out.append(byte)
        checksum = bytes((self.byte(), self.byte()))
        if int(checksum, 16) != sum(out) % 256:
            raise ValueError("GDB checksum mismatch")
        self.process.stdin.write(b"+")
        self.process.stdin.flush()
        return out.decode("ascii")

    def command(self, text):
        self.send(text)
        return self.packet()

    def memory(self, address, size):
        if not 0 < size <= contract.TREE_LIMIT:
            raise ValueError("GDB memory read limit")
        out = bytearray()
        for offset in range(0, size, 1024):
            count = min(1024, size - offset)
            text = self.command(f"m{address + offset:x},{count:x}")
            if len(text) != 2 * count:
                raise ValueError("GDB memory read failed")
            out.extend(bytes.fromhex(text))
        return bytes(out)


def samsung_snapshot(path, work):
    path = path.resolve(strict=True)
    if not 40 <= path.stat().st_size <= 2 * 1024 * 1024:
        raise ValueError("FDT size outside production parser limit")
    probe = work / "fdt-probe"
    subprocess.run(["cc", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", str(ROOT / "r8/tests/fdt_probe.c"),
                    str(ROOT / "r8/r10_payload/fdt.c"), "-o", str(probe)], check=True, timeout=30)
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0")
    output = subprocess.check_output([str(probe), str(path)], text=True, env=env, timeout=10)
    parsed = json.loads(output)
    if parsed["parse"] != 0:
        raise ValueError("Samsung FDT rejected by the production parser")
    blockers = []
    if not parsed["ram"]:
        blockers.append("no RAM banks in supplied FDT")
    if parsed["unresolved_reserved"]:
        blockers.append("unresolved reservations")
    blockers += ["owned load window not established", "entry EL/cache/ICC/timer permissions not observed",
                 "PSCI method and effective counter frequency need explicit evidence"]
    return {"bytes": path.stat().st_size, "sha256": lab.sha256(path),
            "production_parser": parsed, "candidate_handoff_generated": False,
            "hardware_ready": False, "blockers": blockers,
            "note": "Read-only inspection; default R10 policy addresses are test parameters, not allocation proposals."}


def run(args):
    source = args.lab_run.resolve(strict=True)
    previous = json.loads((source / "report.json").read_text())
    if not previous.get("passed") or previous.get("negative_fixture"):
        raise ValueError("a successful positive lab run is required")
    for name, expected in previous["own_sources_sha256"].items():
        lab.verified(ROOT / name, expected)
    reference = json.loads(lab.REFERENCE.read_text())
    verified_inputs = {}
    for name in ("prebuilt/mach.development.bcm2837", "prebuilt/loader.efi"):
        expected = next(item["sha256"] for item in reference["kernel_prebuilt_integrity"]["checks"]
                        if item["path"] == name)
        verified_inputs[name] = lab.verified(previous["inputs"][name]["path"], expected)
    kernel_path = Path(verified_inputs["prebuilt/mach.development.bcm2837"]["path"])
    code = lab.verified(args.efi_code, lab.EFI_HASHES["code"])
    lab.verified(args.efi_vars, lab.EFI_HASHES["vars"])
    lab.verified(source / "payload.bin", previous["artifacts"]["payload.bin"]["sha256"])
    work = args.out.resolve()
    if any("," in str(path) for path in (work, args.efi_code.resolve())):
        raise ValueError("QEMU image paths must not contain commas")
    work.mkdir(parents=True, exist_ok=False)
    (work / "esp/EFI/BOOT").mkdir(parents=True)
    shutil.copyfile(verified_inputs["prebuilt/loader.efi"]["path"], work / "esp/EFI/BOOT/BOOTAA64.EFI")
    shutil.copyfile(source / "payload.bin", work / "payload.bin")
    shutil.copyfile(args.efi_vars, work / "vars.fd")
    qemu = lab.tool_commands(args.tools.resolve())["qemu"]
    command = qemu.copy()
    qdata = args.tools.resolve() / "usr/share/qemu"
    if qdata.is_dir():
        command += ["-L", str(qdata)]
    command += ["-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-smp", "1", "-m", "6G",
                "-accel", "tcg,tb-size=128",
                "-drive", f"if=pflash,format=raw,readonly=on,file={code['path']}",
                "-drive", f"if=pflash,format=raw,file={work / 'vars.fd'}",
                "-drive", f"file=fat:rw:{work / 'esp'},format=raw,if=virtio",
                "-device", f"loader,file={work / 'payload.bin'},addr=0xF0000000,force-raw=on",
                "-display", "none", "-serial", f"file:{work / 'serial.log'}",
                "-monitor", "none", "-no-reboot", "-nic", "none", "-S", "-gdb", "stdio"]
    with (work / "qemu-stderr.log").open("wb") as err:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err)
        try:
            reader = Reader(process, args.timeout)
            if reader.command(f"Z1,{ARM_INIT:x},4") != "OK":
                raise ValueError("cannot install arm_init breakpoint")
            reader.send("c")
            stop = reader.packet()
            if not stop.startswith("T05"):
                raise ValueError("unexpected GDB stop")
            registers = bytes.fromhex(reader.command("g"))
            if len(registers) < 268:
                raise ValueError("short AArch64 register packet")
            x0, = struct.unpack_from("<Q", registers)
            pc, pstate = struct.unpack_from("<QI", registers, 256)
            if pc != ARM_INIT or (pstate & 0xC) != 4:
                raise ValueError("not arm_init in EL1")
            raw_args = reader.memory(x0, contract.BOOT_SIZE)
            boot = contract.BootArgs.decode(raw_args)
            raw_tree = reader.memory(boot.tree_va, boot.tree_size)
            tree = contract.decode_tree(raw_tree)
            if boot.encode() != raw_args or contract.encode_tree(tree) != raw_tree:
                raise ValueError("captured bytes do not round-trip exactly")
            boot_pa = boot.physical(x0, contract.BOOT_SIZE).base
            payload = contract.Span(0xF0000000, (work / "payload.bin").stat().st_size)
            checked = contract.validate_profile(
                boot, tree, boot_pa, kernel_path.read_bytes(),
                ram=[contract.Span(0x40000000, 6 << 30)], reserved=[],
                protected=[payload], complete=True)
            (work / "boot-args.bin").write_bytes(raw_args)
            (work / "apple-tree.bin").write_bytes(raw_tree)
            if reader.command(f"z1,{ARM_INIT:x},4") != "OK":
                raise ValueError("cannot remove breakpoint")
            reader.send("c")
            returncode = process.wait(timeout=args.timeout)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdin.close()
            process.stdout.close()
    data = (work / "serial.log").read_bytes()
    checks = lab.assess_log(data, returncode, False)
    if not all(checks.values()):
        raise ValueError("resumed diagnostic did not satisfy all 17 lab criteria")
    report = {
        "scope": "Read-only QEMU arm_init capture; not Samsung or initial MMU-off entry",
        "passed": True, "registers": {"pc": hex(pc), "x0_virtual": hex(x0), "pstate": hex(pstate)},
        "boot_args_pa_derived": hex(boot_pa), "boot_args": {
            "bytes": len(raw_args), "sha256": lab.sha256(work / "boot-args.bin"), "exact_roundtrip": True,
            "offsets": contract.OFFSETS, "cmdline": boot.cmdline},
        "apple_tree": {"bytes": len(raw_tree), "sha256": lab.sha256(work / "apple-tree.bin"),
                       "exact_roundtrip": True},
        "profile": checked,
        "memory_declaration": {"scope": "lab fixture consistency only; full UEFI reservation map not captured",
                               "guest_ram": ["0x40000000", "0x180000000"],
                               "reserved": [], "protected_payload": [hex(payload.base), hex(payload.size)],
                               "trust_established": False},
        "qemu_returncode": returncode, "resumed_lab_checks": checks,
        "serial_sha256": lab.sha256(work / "serial.log"),
        "inputs": verified_inputs, "efi_code": code,
        "source_sha256": {p: lab.sha256(ROOT / p) for p in
                          ("scripts/capture_xnu_contract.py", "lab/xnu/boot_contract.py")},
        "command": command,
    }
    if args.samsung_fdt:
        report["samsung_fdt"] = samsung_snapshot(args.samsung_fdt, work)
    (work / "contract-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: {len(raw_args)} boot_args bytes and {len(raw_tree)} Apple DT bytes round-trip; resumed lab PASS")
    print(work / "contract-report.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-run", type=Path, required=True)
    parser.add_argument("--efi-code", type=Path, required=True)
    parser.add_argument("--efi-vars", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    parser.add_argument("--tools", type=Path, default=ROOT / "tools/root")
    parser.add_argument("--samsung-fdt", type=Path, help="also inspect it using the existing production C parser")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 180:
        parser.error("--timeout must be between 10 and 180 seconds")
    try:
        run(args)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Contract capture failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
