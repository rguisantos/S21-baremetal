#!/usr/bin/env python3
"""Reproduz a aplicação da série XNU do s21xnu e confere o patch 0146 (toque p3s).

  verify_xnu_touch_patch.py --s21xnu CLONE --dxb CLONE_DXB --xnu CLONE_XNU [--json r.json]

CLONE_XNU: apple-oss-distributions/xnu na tag xnu-8796.141.3 (macOS 13.5),
árvore limpa. CLONE_DXB: blacktop/darwin-xnu-build no commit fixado pelo
workflow xnu.yml do s21xnu. A árvore XNU é copiada para um diretório
temporário; os originais não mudam.

Reproduz o laço de patches do build.sh do dxb: para cada *.patch em ordem de
nome (patches do dxb + do s21xnu), `git apply --check` e aplica, ou pula.
**Os scripts *.sh não são executados** (o build real roda todos antes dos
patches; alguns baixam código). Por isso pulos que dependem de arquivos
gerados por scripts são esperados aqui; o relatório os lista.

Depois aplica 0146, confere que só bsd/dev/sweet_touch.c muda, extrai
ts_panel_map e compila um teste de host: com o painel padrão (1080x2400) o
mapeamento é idêntico ao original para todo valor bruto 0..4095 e todo
touch_flip; com 1440x3200 o toque cai na janela 1080x2400 do perfil
p3s-window.
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PATCH = HERE / "0146-s21-touch-panel-geometry.patch"
XNU_TAG_COMMIT = "1b191cb58250d0705d8a51287127505aa4bc0789"   # xnu-8796.141.3
DXB_COMMIT = "663906528d1cd5ea8fde7de6f16de73db9511549"
S21XNU_COMMIT = "a128f07b04987e60f5e13e2ce67b19ae009672cd"

HOST_TEST = r'''
#include <stdio.h>
#include <stdint.h>
%s
int main(void)
{
	long bad = 0;
	for (uint32_t f = 0; f < 4; f++)
		for (uint32_t r = 0; r < 4096; r++) {
			int x, y;
			ts_panel_map(r, r, f, 1080, 2400, &x, &y);
			int ox = (int)((r * 1080u) >> 12), oy = (int)((r * 2400u) >> 12);
			if (f & 1)
				ox = S21_PANEL_MAXX - ox;
			if (f & 2)
				oy = S21_PANEL_MAXY - oy;
			if (x != ox || y != oy)
				bad++;
		}
	int x, y, inside = 1;
	for (uint32_t r = 0; r < 4096; r++) {
		ts_panel_map(r, 4095 - r, 0, 1440, 3200, &x, &y);
		if (x < 0 || x > 1079 || y < 0 || y > 2399)
			inside = 0;
	}
	ts_panel_map(2048, 2048, 0, 1440, 3200, &x, &y);
	printf("t2s_mismatch=%%ld p3s_mid=%%d,%%d p3s_inside=%%d", bad, x, y, inside);
	ts_panel_map(2048, 2048, 3, 1440, 3200, &x, &y);
	printf(" p3s_mid_flip=%%d,%%d\n", x, y);
	(void)ts_g_panel_w; (void)ts_g_panel_h;
	return 0;
}
'''


def git(*args, cwd, check=True):
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, check=check)


def head(path):
    return git("rev-parse", "HEAD", cwd=path).stdout.strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--s21xnu", required=True)
    ap.add_argument("--dxb", required=True)
    ap.add_argument("--xnu", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    report = {"schema": "s21xnu-xnu-touch-0146/1", "checks": []}
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        report["checks"].append({"check": name, "ok": bool(cond), "detail": str(detail)})
        print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))

    pins = {"s21xnu": (a.s21xnu, S21XNU_COMMIT), "dxb": (a.dxb, DXB_COMMIT), "xnu": (a.xnu, XNU_TAG_COMMIT)}
    for name, (path, want) in pins.items():
        got = head(path)
        check("%s fixado" % name, got == want, got[:12])
    if not ok:
        return 1
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        tree = tmp / "xnu"
        shutil.copytree(a.xnu, tree, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        git("init", "-q", cwd=tree)
        patches = sorted(list(pathlib.Path(a.dxb, "patches").glob("*.patch")) +
                         list(pathlib.Path(a.s21xnu, "xnu", "patches").glob("*.patch")),
                         key=lambda p: p.name)
        applied, skipped = [], []
        for p in patches:
            r = git("apply", "--check", str(p), cwd=tree, check=False)
            if r.returncode == 0:
                git("apply", str(p), cwd=tree)
                applied.append(p.name)
            else:
                skipped.append({"patch": p.name, "reason": (r.stderr.strip().splitlines() or [""])[0]})
        report["series"] = {"applied": applied, "skipped": skipped,
                            "scripts_not_run": sorted(p.name for p in
                                                      pathlib.Path(a.s21xnu, "xnu", "patches").glob("*.sh"))}
        check("série: 0094 (toque sec_ts S21) aplicado", "0094-sweet-touch-sec-ts.patch" in applied)
        check("série: 0139 (poll do toque S21) aplicado", "0139-s21-touch-precise-poll.patch" in applied)
        check("série: 0060 (toque Goodix do Redmi) pulado", "0060-sweet-keys-touch-drivers.patch" not in applied)
        touch = tree / "bsd" / "dev" / "sweet_touch.c"
        before = touch.read_bytes()
        r = git("apply", "--check", str(PATCH), cwd=tree, check=False)
        check("0146 aplica sobre a série", r.returncode == 0, r.stderr.strip()[:200])
        if r.returncode:
            report["result"] = "FAIL"
            return 1
        stat = git("apply", "--numstat", str(PATCH), cwd=tree).stdout.split()
        check("0146 muda só sweet_touch.c", stat[2::3] == ["bsd/dev/sweet_touch.c"], stat)
        git("apply", str(PATCH), cwd=tree)
        after = touch.read_text()
        check("0146 alterou o arquivo", touch.read_bytes() != before)
        check("boot-args touch_panel_w/h lidos",
              'PE_parse_boot_argn("touch_panel_w"' in after and 'PE_parse_boot_argn("touch_panel_h"' in after)
        check("fórmula fixa 1080/2400 removida do caminho de postagem",
              "t->x * 1080u" not in after and "ts_panel_map((uint32_t)t->x" in after)
        m = re.search(r"#define S21_PANEL_MAXX.*?\n}\n", after, re.S)
        check("ts_panel_map extraída", m is not None)
        src = tmp / "t.c"
        src.write_text(HOST_TEST % m.group(0))
        cc = shutil.which("cc") or shutil.which("gcc")
        subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", str(src), "-o", str(tmp / "t")],
                       check=True)
        out = subprocess.run([str(tmp / "t")], capture_output=True, text=True, check=True).stdout.strip()
        vals = dict(kv.split("=") for kv in out.split())
        report["host_test"] = vals
        check("t2s: idêntico ao original (4096 valores × 4 flips)", vals["t2s_mismatch"] == "0", vals["t2s_mismatch"])
        check("p3s: centro do painel físico = pixel 720,1600 da janela", vals["p3s_mid"] == "720,1600")
        check("p3s: todo toque fica dentro da janela 1080x2400", vals["p3s_inside"] == "1")
        check("p3s: espelhamento no painel físico", vals["p3s_mid_flip"] == "719,1599", vals["p3s_mid_flip"])
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"], "| série: %d aplicados, %d pulados" %
          (len(report["series"]["applied"]), len(report["series"]["skipped"])))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
