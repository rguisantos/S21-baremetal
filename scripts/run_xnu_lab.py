#!/usr/bin/env python3
"""Build a tiny Darwin init and boot pinned HackiOS prebuilt in QEMU only.

No downloads, phone commands, raw disks, iOS images or SDK are used. External
repositories and tested UEFI inputs are required explicitly. Every run owns
a new directory, fresh NVRAM, an APFS fixture and its serial log/report.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs/references/hackios-xnu-20261022.json"
FIXTURE = b"S21-XNU-LAB-FIXTURE-v1\n"
CMDLINE = "cpus=1 loader_return_after=30"
MARKERS = (
    b"S21 XNU LAB: identity PASS pid=1 uid=0",
    b"S21 XNU LAB: APFS fixture PASS",
    b"S21 XNU LAB: timer PASS select=200ms elapsed=100ms..10s",
    b"S21 XNU LAB: ALL PASS; requesting RB_HALT",
)
EFI_HASHES = {
    "code": "5d3147294c56ce8cb636c57c181776a89bc7ba254274c35698dc5795758052d3",
    "vars": "b3b855c5a80310168051164986855692d1bdb06e67619856177965cd87c6774f",
}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified(path, expected):
    path = Path(path).resolve(strict=True)
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": actual}


def upstream_inputs(kernel, userland):
    reference = json.loads(REFERENCE.read_text())
    inputs = {}
    for tree, full_name in ((kernel, "oosexgang/hackios-xnu-kernel"),
                            (userland, "oosexgang/hackios-xnu-userland")):
        source = next(s for s in reference["sources"] if s["repository"] == full_name)
        head = subprocess.check_output(["git", "-C", str(tree), "rev-parse", "HEAD"],
                                       text=True, timeout=10).strip()
        if head != source["revision"]:
            raise ValueError(f"Wrong revision for {full_name}: {head}")
        wanted = ("xnuloader/mkpayload.py",) if tree == kernel else ("tools/apfs/mkapfs.py",)
        for path in wanted:
            expected = next(f["sha256"] for f in source["files_hashed_for_traceability"]
                            if f["path"] == path)
            inputs[path] = verified(tree / path, expected)
    for path in ("prebuilt/mach.development.bcm2837", "prebuilt/loader.efi"):
        expected = next(f["sha256"] for f in reference["kernel_prebuilt_integrity"]["checks"]
                        if f["path"] == path)
        inputs[path] = verified(kernel / path, expected)
    return inputs


def tool_commands(tools):
    def choose(name):
        local = tools / "usr/bin" / name
        if local.is_file():
            return local
        system = shutil.which(name)
        if system is None:
            raise ValueError(f"Missing {name}; supply --tools or add it to PATH")
        return Path(system)

    commands = {}
    for name in ("aarch64-linux-gnu-as", "aarch64-linux-gnu-objcopy"):
        binary = choose(name)
        commands[name] = (["bash", str(ROOT / "scripts/cross-run.sh"), str(tools), str(binary)]
                          if binary == tools / "usr/bin" / name else [str(binary)])
    qemu = choose("qemu-system-aarch64")
    loader = tools / "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
    if qemu == tools / "usr/bin/qemu-system-aarch64" and loader.is_file():
        libs = f"{tools}/usr/lib/x86_64-linux-gnu:{tools}/usr/lib"
        commands["qemu"] = [str(loader), "--library-path", libs, str(qemu)]
    else:
        commands["qemu"] = [str(qemu)]
    return commands


def assess_log(data, returncode, timed_out):
    positions = [data.find(marker) for marker in MARKERS]
    return {
        "qemu_exit_zero": returncode == 0,
        "no_timeout": not timed_out,
        "darwin_kernel": b"Darwin Kernel Version 22.5.0:" in data,
        "gic_virtual_timer": b"virtual timer on PPI 27" in data,
        "apfs_root": b'"S21Lab" of container 0' in data,
        "user_pid1_uid0": positions[0] >= 0,
        "user_apfs_fixture": positions[1] >= 0,
        "user_sleep_and_clock": positions[2] >= 0,
        "user_all_pass": positions[3] >= 0,
        "ordered_user_checks": all(p >= 0 for p in positions) and positions == sorted(positions),
        "cpu_halted": b"CPU halted" in data,
        "loader_returned_normally": re.search(rb"(?m)^returned [0-9]+ 0\r?$", data) is not None,
        "complete_return_log": b"== END OF LOG ==" in data,
        "no_failure_marker": b"S21 XNU LAB: FAIL" not in data,
        "no_panic": re.search(rb"(?m)^panic\(", data) is None,
        "no_user_trap": b"usertrap:" not in data and b"userabort:" not in data,
        "no_early_exception": b"early-exception" not in data,
    }


def run(args):
    kernel, userland = args.kernel_tree.resolve(), args.userland_tree.resolve()
    if kernel == userland:
        raise ValueError("Use separate pinned kernel and userland clones")
    inputs = upstream_inputs(kernel, userland)
    inputs["efi_code"] = verified(args.efi_code, EFI_HASHES["code"])
    inputs["efi_vars_template"] = verified(args.efi_vars, EFI_HASHES["vars"])
    commands = tool_commands(args.tools.resolve())
    if args.out is None:
        (ROOT / "build").mkdir(exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="xnu-lab-", dir=ROOT / "build"))
    else:
        work = args.out.resolve()
        if work.is_relative_to(kernel) or work.is_relative_to(userland):
            raise ValueError("Output must be outside the external source clones")
        work.mkdir(parents=True, exist_ok=False)
    print(f"XNU lab directory: {work}", flush=True)
    setup_log = work / "setup.log"
    raw_text = work / "init.text"
    root = work / "root"
    esp = work / "esp"
    for path in (root / "sbin", root / "dev", root / "etc", esp / "EFI/BOOT"):
        path.mkdir(parents=True)
    module = importlib.util.spec_from_file_location("s21_lab_macho", ROOT / "lab/xnu/macho.py")
    macho = importlib.util.module_from_spec(module)
    module.loader.exec_module(macho)
    with setup_log.open("wb") as log:
        subprocess.run(commands["aarch64-linux-gnu-as"] + ["-march=armv8-a", "-o",
                       str(work / "init.o"), str(ROOT / "lab/xnu/init.S")],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=30)
        subprocess.run(commands["aarch64-linux-gnu-objcopy"] + ["-O", "binary", "-j", ".text",
                       str(work / "init.o"), str(raw_text)], check=True,
                       stdout=log, stderr=subprocess.STDOUT, timeout=30)
        init = root / "sbin/launchd"
        init.write_bytes(macho.build_init(raw_text.read_bytes()))
        init.chmod(0o755)
        fixture = b"X" + FIXTURE[1:] if args.negative_fixture else FIXTURE
        (root / "etc/s21-lab.txt").write_bytes(fixture)
        shutil.copyfile(kernel / "prebuilt/loader.efi", esp / "EFI/BOOT/BOOTAA64.EFI")
        shutil.copyfile(args.efi_vars, work / "vars.fd")
        subprocess.run([sys.executable, str(userland / "tools/apfs/mkapfs.py"),
                       "-o", str(work / "root.apfs"), "S21Lab=" + str(root)],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=30)
        subprocess.run([sys.executable, str(kernel / "xnuloader/mkpayload.py"),
                       "-o", str(work / "payload.bin"),
                       "kernel=" + str(kernel / "prebuilt/mach.development.bcm2837"),
                       "ramdisk=" + str(work / "root.apfs"), "--cmdline", CMDLINE],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=30)
    qemu = commands["qemu"]
    argv = qemu.copy()
    qdata = args.tools.resolve() / "usr/share/qemu"
    if qdata.is_dir():
        argv += ["-L", str(qdata)]
    argv += ["-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-smp", "1", "-m", "6G",
             "-accel", "tcg,tb-size=128",
             "-drive", f"if=pflash,format=raw,readonly=on,file={args.efi_code.resolve()}",
             "-drive", f"if=pflash,format=raw,file={work / 'vars.fd'}",
             "-drive", f"file=fat:rw:{esp},format=raw,if=virtio",
             "-device", f"loader,file={work / 'payload.bin'},addr=0xF0000000,force-raw=on",
             "-display", "none", "-serial", "stdio", "-monitor", "none", "-no-reboot", "-nic", "none"]
    # QEMU drive options use comma separators; reject ambiguous input paths.
    if any("," in str(p) for p in (work, args.efi_code.resolve())):
        raise ValueError("QEMU image paths must not contain commas")
    started = time.monotonic()
    timed_out = False
    with (work / "serial.log").open("wb") as log:
        try:
            proc = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL, timeout=args.timeout)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out, returncode = True, None
    serial = (work / "serial.log").read_bytes()
    checks = assess_log(serial, returncode, timed_out)
    passed = all(checks.values())
    artifacts = {}
    for path in (raw_text, root / "sbin/launchd", root / "etc/s21-lab.txt",
                 work / "root.apfs", work / "payload.bin", work / "serial.log"):
        artifacts[str(path.relative_to(work))] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    report = {
        "schema_version": 1, "scope": "QEMU virt; one CPU; external prebuilt XNU; own Darwin init",
        "passed": passed, "negative_fixture": args.negative_fixture,
        "inputs": inputs,
        "own_sources_sha256": {p: sha256(ROOT / p) for p in
                               ("lab/xnu/init.S", "lab/xnu/macho.py", "scripts/run_xnu_lab.py")},
        "qemu_version": subprocess.check_output(qemu + ["--version"], text=True, timeout=10).splitlines()[0],
        "command": argv, "kernel_cmdline": CMDLINE,
        "duration_seconds": round(time.monotonic() - started, 3),
        "qemu_returncode": returncode, "timed_out": timed_out,
        "checks": checks, "artifacts": artifacts,
        "not_demonstrated": ["XNU build from source", "iOS userland/SpringBoard",
                             "Samsung boot/dual boot", "Exynos or Mali hardware", "SMP"],
    }
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'PASS' if passed else 'FAIL'}: {sum(checks.values())}/{len(checks)} criteria; {work / 'report.json'}")
    if not passed:
        print("Unsatisfied: " + ", ".join(k for k, v in checks.items() if not v))
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-tree", type=Path, required=True)
    parser.add_argument("--userland-tree", type=Path, required=True)
    parser.add_argument("--efi-code", type=Path, required=True)
    parser.add_argument("--efi-vars", type=Path, required=True)
    parser.add_argument("--tools", type=Path, default=ROOT / "tools/root")
    parser.add_argument("--out", type=Path, help="new directory only (default: unique build/xnu-lab-*)")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--negative-fixture", action="store_true",
                        help="corrupt fixture contents; the harness must report failure and exit 1")
    args = parser.parse_args()
    if not 10 <= args.timeout <= 180:
        parser.error("--timeout must be between 10 and 180 seconds")
    try:
        return run(args)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"XNU lab setup error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
