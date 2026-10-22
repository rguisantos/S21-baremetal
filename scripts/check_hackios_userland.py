#!/usr/bin/env python3
"""Reproduce the reported HackiOS build defects with synthetic host inputs.

Requires the pinned external userland tree. Writes a patch and isolated
fixtures into a new directory; never patches the supplied checkout, builds
iOS images, downloads firmware or runs launchd/SpringBoard.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REVISION = "906425b75e02b4f99eb5d7bb1ef7c9583472d772"
HASHES = {
    "userland/mkjobs.py": "b5d297070abd74cdef8faec4a9600bbc41702a05ce884681f61cb6fb205ad88f",
    "userland/build.sh": "a4268a3f68931c00c48ee14c4f58cb20997c71eef37a12debc42c286991ae02d",
    "tools/apfs/mkapfs.py": "c14a81ae9286c69a77673552fcf240de84d37e8fde16f617b2d2efc84d758bdc",
}
COPY_LINE = "cp obj/hello_dyn obj/svc_test obj/surf_test obj/drawable_test obj/rwtouch obj/mg_test root/bin/"
COPY_FIXED = "cp obj/hello_dyn obj/svc_test obj/surf_test obj/rwtouch obj/mg_test root/bin/\n\tif [ -f obj/drawable_test ]; then cp obj/drawable_test root/bin/; fi"
ZONE_LINE = "zone=$(timedatectl show -p Timezone --value 2>/dev/null); zone=${zone:-UTC}"
ZONE_FIXED = "zone=$(timedatectl show -p Timezone --value 2>/dev/null || true); zone=${zone:-UTC}"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replacements(jobs, build):
    edits = [("for name in ('RWA_PACKED16',):", "for env_name in ('RWA_PACKED16',):"),
             ("os.environ.get(name)", "os.environ.get(env_name)"),
             ("[name] = os.environ[name]", "[env_name] = os.environ[env_name]")]
    for before, after in edits:
        require(jobs.count(before) == 2, "unexpected mkjobs source")
        jobs = jobs.replace(before, after)
    for before, after in [(COPY_LINE, COPY_FIXED), (ZONE_LINE, ZONE_FIXED),
                          ("\nset -e\n", "\nset -e\numask 022\n")]:
        require(build.count(before) == 1, "unexpected build source")
        build = build.replace(before, after)
    return jobs, build


def check_jobs(source, directory, umask, packed, apfs):
    ios, dest = directory / "rootfs", directory / "jobs"
    daemons = ios / "System/Library/LaunchDaemons"
    daemons.mkdir(parents=True)
    (ios / "bin").mkdir()
    expected = []
    for name in ("named", "rest-a", "rest-b"):
        label = "org.s21.fixture." + name
        expected.append(label + ".plist")
        (ios / "bin" / name).write_bytes(b"synthetic fixture, not an iOS executable\n")
        with (daemons / (label + ".plist")).open("wb") as out:
            plistlib.dump({"Label": label, "Program": "/bin/" + name,
                           "MachServices": {label: True}, "RunAtLoad": True}, out)
    env = dict(os.environ)
    env.pop("RWA_PACKED16", None)
    if packed:
        env["RWA_PACKED16"] = "1"  # tests propagation, does not exercise Metal
    result = subprocess.run([sys.executable, str(source), "--rest", str(ios), str(dest),
                             "org.s21.fixture.named"], env=env, umask=umask,
                            check=True, capture_output=True, text=True, timeout=10)
    files = sorted(p.name for p in dest.iterdir())
    metadata = {name: {"mode": oct(item.mode & 0o777), "uid": item.uid, "gid": item.gid}
                for name, item in apfs.read_tree(str(dest)).children.items()}
    jobs = {p.name: plistlib.loads(p.read_bytes()) for p in dest.iterdir()}
    return {"umask": oct(umask), "packed_env_test": packed, "files": files,
            "expected_files": sorted(expected), "names_preserved": files == sorted(expected),
            "apfs_input_metadata": metadata, "all_files_mode_0644": all(x["mode"] == "0o644" for x in metadata.values()),
            "all_directories_mode_0755": (dest.stat().st_mode & 0o777) == 0o755,
            "env_propagated": all(job.get("EnvironmentVariables", {}).get("RWA_PACKED16") == "1"
                                  for job in jobs.values()) if packed else None,
            "generator_stdout": result.stdout}


def shell_case(work, name, code, *, copies=False):
    directory = work / name
    directory.mkdir()
    if copies:
        (directory / "obj").mkdir()
        (directory / "root/bin").mkdir(parents=True)
        for filename in ("hello_dyn", "svc_test", "surf_test", "rwtouch", "mg_test"):
            (directory / "obj" / filename).write_text("synthetic fixture\n")
    command = directory / "timedatectl"
    command.write_text("#!/bin/sh\nexit 1\n")
    command.chmod(0o755)
    env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ.get("PATH", ""))
    result = subprocess.run(["bash", "-c", "set -e\n" + code], cwd=directory,
                            env=env, capture_output=True, text=True, timeout=10)
    return {"returncode": result.returncode, "stdout": result.stdout,
            "copied_files": sorted(p.name for p in (directory / "root/bin").iterdir()) if copies else []}


def run(args):
    tree = args.userland_tree.resolve(strict=True)
    revision = subprocess.check_output(["git", "-C", str(tree), "rev-parse", "HEAD"], text=True, timeout=10).strip()
    require(revision == REVISION, "userland revision differs from pinned audit")
    sources = {path: (tree / path).read_bytes() for path in HASHES}
    for path, data in sources.items():
        require(sha(data) == HASHES[path], "source SHA mismatch: " + path)
    work = args.out.resolve()
    work.mkdir(parents=True, exist_ok=False)
    originals = {path: sources[path].decode() for path in ("userland/mkjobs.py", "userland/build.sh")}
    fixed_jobs, fixed_build = replacements(*originals.values())
    fixed = {"userland/mkjobs.py": fixed_jobs, "userland/build.sh": fixed_build}
    patch = "".join("".join(difflib.unified_diff(originals[path].splitlines(keepends=True),
                           content.splitlines(keepends=True), fromfile="a/" + path, tofile="b/" + path))
                    for path, content in fixed.items())
    (work / "hackios-userland-portability.patch").write_text(patch)
    patched_jobs = work / "mkjobs-fixed.py"
    patched_jobs.write_text(fixed_jobs)
    patched_build = work / "build-fixed.sh"
    patched_build.write_text(fixed_build)
    subprocess.run(["bash", "-n", str(patched_build)], check=True, timeout=10)
    spec = importlib.util.spec_from_file_location("hackios_apfs_audit", tree / "tools/apfs/mkapfs.py")
    apfs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(apfs)
    cases = {}
    for name, source, mask, packed in (
        ("original_umask002", tree / "userland/mkjobs.py", 0o002, False),
        ("original_umask022", tree / "userland/mkjobs.py", 0o022, False),
        ("fixed_umask002", patched_jobs, 0o002, False),
        ("fixed_umask022", patched_jobs, 0o022, False),
        ("original_umask022_env1", tree / "userland/mkjobs.py", 0o022, True),
        ("fixed_umask022_env1", patched_jobs, 0o022, True)):
        cases[name] = check_jobs(source, work / name, mask, packed, apfs)
    require(not cases["original_umask002"]["names_preserved"], "expected original collision not observed")
    require(not cases["original_umask002"]["all_files_mode_0644"], "expected umask effect not observed")
    require(not cases["original_umask022"]["names_preserved"], "collision unexpectedly depends on umask")
    require(not cases["original_umask022_env1"]["names_preserved"], "collision unexpectedly depends on env absence")
    require(cases["fixed_umask002"]["names_preserved"], "rename did not preserve files")
    require(not cases["fixed_umask002"]["all_files_mode_0644"], "rename must not be mistaken for a permissions fix")
    for name in ("fixed_umask022", "fixed_umask022_env1"):
        require(cases[name]["names_preserved"] and cases[name]["all_files_mode_0644"]
                and cases[name]["all_directories_mode_0755"], "corrected fixture failed")
    require(cases["fixed_umask022_env1"]["env_propagated"], "environment propagation lost")
    fragments = {
        "copy_original": shell_case(work, "copy-original", COPY_LINE, copies=True),
        "copy_fixed": shell_case(work, "copy-fixed", COPY_FIXED, copies=True),
        "zone_original": shell_case(work, "zone-original", ZONE_LINE + '\nprintf "%s\\n" "$zone"'),
        "zone_fixed": shell_case(work, "zone-fixed", ZONE_FIXED + '\nprintf "%s\\n" "$zone"'),
    }
    require(fragments["copy_original"]["returncode"] != 0 and fragments["copy_fixed"]["returncode"] == 0,
            "optional drawable copy control failed")
    require(fragments["zone_original"]["returncode"] != 0 and fragments["zone_fixed"]["stdout"] == "UTC\n",
            "timezone set-e control failed")
    patch_path = ROOT / "lab/xnu/patches/hackios-userland-portability.patch"
    if patch_path.exists():
        require(patch_path.read_text() == patch, "committed patch differs from audited patch")
    report = {"schema_version": 1, "upstream_revision": REVISION, "source_sha256": HASHES,
              "scope": "Six synthetic job-generation fixtures and four isolated Bash fragments; no iOS files or GUI run",
              "passed": True, "jobs_cases": cases, "shell_fragments": fragments,
              "patch_sha256": sha(patch.encode()), "patch_applied_to_upstream_checkout": False,
              "fixed_files_sha256": {p: sha(v.encode()) for p, v in fixed.items()},
              "script_sha256": sha(Path(__file__).read_bytes()),
              "full_apfs_built": False, "launchd_executed": False, "springboard_observed": False}
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: collision and umask reproduced; corrected job fixtures and isolated shell controls passed")
    print(work / "report.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--userland-tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"check_hackios_userland: {exc}\n")


if __name__ == "__main__":
    main()
