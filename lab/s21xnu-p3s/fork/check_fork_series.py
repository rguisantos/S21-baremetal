#!/usr/bin/env python3
"""Confere que a série para o fork do s21xnu bate com os patches do lab.

  check_fork_series.py CLONE_S21XNU

Aplica fork/000*.patch com `git am` numa cópia do clone fixado (a128f07) e
exige: árvore final igual à de 0001+0002 aplicados com `patch -p1` mais os
patches XNU 0146–0150 copiados em xnu/patches/ e o patch 0004 de NVRAM; nenhum outro arquivo
alterado. Evita que a série do fork e os patches do lab divirjam.
"""
import filecmp
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))
import verify_p3s_profile as vp  # noqa: E402

XNU = ["0146-s21-touch-panel-geometry.patch", "0147-s21-p3s-letterbox-display.patch",
       "0148-s21-p3s-scaled-display.patch", "0149-s21-p3s-wifi-enumerate.patch",
       "0150-s21-p3s-wifi-bcm4389-firmware.patch"]


def run(*a, cwd):
    return subprocess.run(list(a), cwd=cwd, check=True, capture_output=True, text=True).stdout


def main(argv):
    src = pathlib.Path(argv[1]).resolve()
    vp.pinned_clone(src)
    ok = True
    with tempfile.TemporaryDirectory() as t:
        a, b = pathlib.Path(t, "fork"), pathlib.Path(t, "lab")
        run("git", "clone", "-q", str(src), str(a), cwd=t)
        run("git", "-c", "user.name=t", "-c", "user.email=t@t", "am", "-q",
            *sorted(str(p) for p in HERE.glob("000*.patch")), cwd=a)
        shutil.copytree(src, b, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        for p in (vp.PATCH, LAB / "0002-probe-lk-handoff-facts.patch"):
            run("patch", "-p1", "--batch", "-s", "-i", str(p), cwd=b)
        for n in XNU:
            shutil.copy(LAB / "xnu" / n, b / "xnu" / "patches" / n)
        run("patch", "-p1", "--batch", "-s", "-i",
            str(HERE / "0004-mkpayload-align-nvram.patch"), cwd=b)
        run(sys.executable, "tools/test_mkpayload_nvram.py", cwd=a)
        changed = run("git", "diff", "--name-only", vp.PINNED_COMMIT, "HEAD", cwd=a).split()
        want = sorted(["shim/build-s21.sh", "shim/console.h", "shim/shim.c", "tools/mkadt.py",
                       "tools/mkpayload.py", "tools/test_mkpayload_nvram.py"] +
                      ["xnu/patches/" + n for n in XNU])
        print("arquivos alterados pela série:", len(changed))
        if sorted(changed) != want:
            ok = False
            print("FAIL lista de arquivos:", sorted(changed))
        for f in want:
            same = filecmp.cmp(a / f, b / f, shallow=False)
            ok &= same
            print("%s %s" % ("PASS" if same else "FAIL", f))
    print("RESULTADO", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
