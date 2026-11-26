#!/usr/bin/env python3
"""Aplica o perfil p3s ao s21xnu fixado e confere shim e ADT gerados.

Uso: verify_p3s_profile.py CLONE_S21XNU [--json saida.json]

CLONE_S21XNU deve estar no commit fixado (PINNED_COMMIT), com árvore limpa.
O script copia a árvore para um diretório temporário, compila o shim sem o
patch e com ele (BOARD=t2s, p3s, p3s-window) e gera o ADT com semente fixa.
Critérios: t2s com patch reproduz byte a byte o original (shim e ADT); p3s e
p3s-window anunciam a geometria esperada no nó sweet-fbcon e nos boot_args
compilados. Nada é executado no aparelho; XNU não é compilado aqui.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

PINNED_COMMIT = "a128f07b04987e60f5e13e2ce67b19ae009672cd"
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
PATCH = HERE / "0001-board-p3s-framebuffer.patch"
EXPECTED = {"t2s": (1080, 2400, 4320), "p3s": (1440, 3200, 5760), "p3s-window": (1080, 2400, 5760)}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned_clone(src):
    """Exige o clone do s21xnu no commit fixado e sem alterações rastreadas; devolve o commit."""
    src = pathlib.Path(src).resolve()
    head = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    if head != PINNED_COMMIT:
        raise SystemExit("clone em %s, esperado %s" % (head, PINNED_COMMIT))
    dirty = subprocess.run(["git", "-C", str(src), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout
    if dirty.strip():
        raise SystemExit("clone com alterações locais:\n" + dirty)
    return head


def cross_env(tmp):
    """aarch64-linux-gnu-* no PATH; usa tools/root deste repositório se existir."""
    env = dict(os.environ)
    root = REPO / "tools" / "root"
    gcc = root / "usr" / "bin" / "aarch64-linux-gnu-gcc"
    if not gcc.exists():
        if not shutil.which("aarch64-linux-gnu-gcc"):
            raise SystemExit("cross-compilador aarch64-linux-gnu-gcc ausente")
        return env
    xbin = pathlib.Path(tmp) / "xbin"
    xbin.mkdir()
    run = "exec bash %s %s %%s \"$@\"\n" % (REPO / "scripts" / "cross-run.sh", root)
    # gcc procura as/ld em -B; os links de tools/root/usr/aarch64-linux-gnu/bin
    # não preservam o bit de execução no checkout.
    tools = {"as": "aarch64-linux-gnu-as", "ld": "aarch64-linux-gnu-ld"}
    for t in ("objcopy", "readelf", "nm"):
        tools["aarch64-linux-gnu-" + t] = "aarch64-linux-gnu-" + t
    for name, real in tools.items():
        p = xbin / name
        p.write_text("#!/bin/bash\n" + run % (root / "usr" / "bin" / real))
        p.chmod(0o755)
    p = xbin / "aarch64-linux-gnu-gcc"
    p.write_text("#!/bin/bash\n" + run % ("%s -B%s/" % (gcc, xbin)))
    p.chmod(0o755)
    env["PATH"] = "%s:%s" % (xbin, env.get("PATH", ""))
    return env


def build_shim(tree, board, env):
    shim = tree / "shim"
    shutil.rmtree(shim / "out", ignore_errors=True)
    e = dict(env)
    if board is not None:
        e["BOARD"] = board
    r = subprocess.run(["bash", "build-s21.sh"], cwd=shim, env=e, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("build do shim falhou (%s):\n%s%s" % (board, r.stdout, r.stderr))
    return (shim / "out" / "Image").read_bytes()


def build_adt(tree, board):
    """mkadt.build com semente fixa; devolve (blob, (w, h, stride, base, size))."""
    argv = ["mkadt.py", "x"] + (["--board=" + board] if board else [])
    saved_argv, saved_path = sys.argv, list(sys.path)
    sys.argv = argv
    sys.path.insert(0, str(tree / "tools"))
    try:
        for m in ("adt", "mkadt_under_test"):
            sys.modules.pop(m, None)
        spec = importlib.util.spec_from_file_location("mkadt_under_test", tree / "tools" / "mkadt.py")
        mod = importlib.util.module_from_spec(spec)
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            spec.loader.exec_module(mod)
            root = mod.build(seed=b"\0" * 64, highmem=True)
        adt = sys.modules["adt"]
        blob = adt.serialize(root)
        geom = None
        stack = [adt.parse(blob)[0]]
        while stack:
            n = stack.pop()
            d = {k: v for k, f, v in n.props}
            if d.get("name") == b"sweet-fbcon\0":
                w, h, s = (struct.unpack("<I", d[k])[0] for k in ("width", "height", "stride"))
                base, size = struct.unpack("<QQ", d["reg"])
                geom = (w, h, s, base, size)
            stack.extend(n.children)
        return blob, geom
    finally:
        sys.argv, sys.path[:] = saved_argv, saved_path


BOARD_FLAGS = {"t2s": [], "p3s": ["-DSWEET_BOARD_P3S"], "p3s-window": ["-DSWEET_BOARD_P3S_WINDOW"]}


def header_geometry(tree, board, env):
    """FB_W/FB_H/FB_STRIDE de shim/console.h como o compilador os vê (loader.c os
    copia para boot_args.Video)."""
    r = subprocess.run(["aarch64-linux-gnu-gcc", "-E", "-P", "-ffreestanding", "-x", "c", "-include",
                        str(tree / "shim" / "console.h")] + BOARD_FLAGS[board] + ["-"],
                       input="FB_W FB_H FB_STRIDE\n", env=env, capture_output=True, text=True,
                       check=True)
    expr = r.stdout.strip().splitlines()[-1]
    vals = expr.replace("(", " ( ").replace(")", " ) ")
    # avalia apenas inteiros, espaços, parênteses e '*'
    if not set(vals) <= set("0123456789 ()*"):
        raise SystemExit("expansão inesperada: %r" % expr)
    parts, depth, cur = [], 0, ""
    for tok in vals.split():
        cur += tok
        depth += tok.count("(") - tok.count(")")
        if depth == 0:
            parts.append(cur)
            cur = ""
    return tuple(eval(p, {"__builtins__": {}}) for p in parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("clone")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    src = pathlib.Path(a.clone).resolve()
    head = pinned_clone(src)
    report = {"schema": "s21xnu-p3s-profile/1", "s21xnu_commit": head,
              "patch_sha256": sha(PATCH.read_bytes()), "checks": [], "builds": {}}
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        report["checks"].append({"check": name, "ok": bool(cond), "detail": detail})
        print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))

    with tempfile.TemporaryDirectory() as tmp:
        env = cross_env(tmp)
        orig, patched = pathlib.Path(tmp) / "orig", pathlib.Path(tmp) / "patched"
        for t in (orig, patched):
            shutil.copytree(src, t, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        r = subprocess.run(["patch", "-p1", "--batch", "-i", str(PATCH)], cwd=patched,
                           capture_output=True, text=True)
        check("patch -p1 aplica", r.returncode == 0, r.stderr.strip())
        if r.returncode:
            return 1
        base_img = build_shim(orig, None, env)
        base_adt, base_geom = build_adt(orig, None)
        report["builds"]["original"] = {"shim": sha(base_img), "adt": sha(base_adt)}
        check("ADT original anuncia 1080x2400", base_geom[:3] == EXPECTED["t2s"], str(base_geom))
        images = {}
        for board, (w, h, s) in EXPECTED.items():
            img = build_shim(patched, board, env)
            blob, geom = build_adt(patched, board)
            images[board] = img
            report["builds"][board] = {"shim": sha(img), "adt": sha(blob), "fbcon": list(geom)}
            check("ADT %s geometria" % board, geom[:3] == (w, h, s), str(geom[:3]))
            check("ADT %s base/tamanho preservados" % board, geom[3:] == base_geom[3:],
                  "%#x+%#x" % geom[3:])
            check("ADT %s cabe em FB_SIZE" % board, s * h <= geom[4], "%d <= %d" % (s * h, geom[4]))
            hg = header_geometry(patched, board, env)
            check("console.h %s (boot_args.Video)" % board, hg == (w, h, s), str(hg))
            if board == "t2s":
                check("shim t2s idêntico ao original", img == base_img, sha(img)[:16])
                check("ADT t2s idêntico ao original", blob == base_adt, sha(blob)[:16])
        check("shim p3s difere do t2s", images["p3s"] != images["t2s"])
        check("shim p3s-window difere do p3s", images["p3s-window"] != images["p3s"])
        default_img = build_shim(patched, None, env)
        check("BOARD ausente = t2s", default_img == images["t2s"])
        r = subprocess.run(["bash", "build-s21.sh"], cwd=patched / "shim",
                           env=dict(env, BOARD="zz"), capture_output=True, text=True)
        check("BOARD inválido recusado", r.returncode != 0 and "unknown BOARD" in r.stderr)
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"])
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
