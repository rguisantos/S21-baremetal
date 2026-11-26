#!/usr/bin/env python3
"""Reproduz a série XNU do s21xnu e confere os patches p3s 0146 (toque), 0147 (tela) e 0148 (escala).

  verify_xnu_touch_patch.py --s21xnu CLONE --dxb CLONE_DXB --xnu CLONE_XNU [--json r.json]

CLONE_XNU: apple-oss-distributions/xnu na tag xnu-8796.141.3 (macOS 13.5).
CLONE_DXB: blacktop/darwin-xnu-build no commit fixado pelo workflow xnu.yml do
s21xnu. As árvores originais não mudam.

Reproduz o laço de patches do build.sh do dxb: cada *.patch em ordem de nome
(patches do dxb + do s21xnu) passa por `git apply --check` e é aplicado, ou
pulado. **Os scripts *.sh não são executados** (o build real roda todos antes
dos patches; alguns baixam código); pulos que dependem de arquivos gerados por
script são esperados aqui e ficam listados no relatório.

Depois aplica 0146, 0147 e 0148, extrai as funções puras (ts_panel_map,
sweet_hid_fit/geometry/visible/norm, sweet_present_fit, sweet_fb_scaled_blit)
e compila um teste de host que confere: S21+ (console 1080x2400) idêntico às
fórmulas originais em todos os valores; p3s-window igual ao S21+; p3s tela
cheia (1440x3200) com o iPhone X 1125x2436 centrado, e ida e volta toque→HID
coerente com o deslocamento que o SweetFramebuffer aplica às camadas; com
sweetfb_scale=1, iPhone X escalado para 1440x3118 (bordas de 41 linhas),
blit por vizinho mais próximo pixel a pixel e toque coerente com o blit.
O XNU não é compilado.
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PATCHES = [HERE / "0146-s21-touch-panel-geometry.patch", HERE / "0147-s21-p3s-letterbox-display.patch",
           HERE / "0148-s21-p3s-scaled-display.patch"]
XNU_TAG_COMMIT = "1b191cb58250d0705d8a51287127505aa4bc0789"   # xnu-8796.141.3
DXB_COMMIT = "663906528d1cd5ea8fde7de6f16de73db9511549"
S21XNU_COMMIT = "a128f07b04987e60f5e13e2ce67b19ae009672cd"

HOST_TEST = r'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef int32_t IOFixed;
%(touch)s
%(hid)s
%(fb)s

/* Fórmulas anteriores a 0146/0147 (a128f07), só para o S21+. */
static void old_touch(uint32_t r, uint32_t q, uint32_t f, int *x, int *y)
{
	*x = (int)((r * 1080u) >> 12);
	*y = (int)((q * 2400u) >> 12);
	if (f & 1)
		*x = S21_PANEL_MAXX - *x;
	if (f & 2)
		*y = S21_PANEL_MAXY - *y;
}
static IOFixed old_norm(int v, int panel, int logical)
{
	int off = (logical - panel) / 2;
	return (IOFixed)(((int64_t)(v + off) << 16) / logical);
}
static int old_edge(int x, int y)
{
	return x < 48 || x > 1079 - 48 || y < 48 || y > 2399 - 100;
}
static int new_edge(int pw, int ph, int lw, int lh, int ox, int oy, int x, int y)
{
	int l, r, t, b;
	sweet_hid_visible(pw, ph, lw, lh, ox, oy, &l, &r, &t, &b);
	return x < l + 48 || x > r - 48 || y < t + 48 || y > b - 100;
}

int main(void)
{
	long t2s_touch = 0, t2s_hid = 0, t2s_edge = 0, win_touch = 0, roundtrip = 0, clamp_bad = 0;
	int pw, ph, lw, lh, ox, oy;
	for (uint32_t f = 0; f < 4; f++)
		for (uint32_t r = 0; r < 4096; r++) {
			int x, y, a, b;
			ts_panel_map(r, r, f, 1080, 2400, 1080, 2400, &x, &y);
			old_touch(r, r, f, &a, &b);
			t2s_touch += (x != a) + (y != b);
		}
	sweet_hid_geometry(1080, 2400, 0, 0, &pw, &ph, &lw, &lh, &ox, &oy);
	printf("t2s_geom=%%dx%%d,%%dx%%d,%%d,%%d", pw, ph, lw, lh, ox, oy);
	for (int x = 0; x < 1080; x++)
		t2s_hid += sweet_hid_norm(x, ox, lw) != old_norm(x, 1080, 1125);
	for (int y = 0; y < 2400; y++)
		t2s_hid += sweet_hid_norm(y, oy, lh) != old_norm(y, 2400, 2436);
	for (int x = 0; x < 1080; x++)
		for (int y = 0; y < 2400; y++)
			t2s_edge += new_edge(pw, ph, lw, lh, ox, oy, x, y) != old_edge(x, y);
	for (uint32_t r = 0; r < 4096; r++) {
		int x, y;
		ts_panel_map(r, 4095 - r, 0, 1440, 3200, 1080, 2400, &x, &y);
		int px = (int)((r * 1440u) >> 12), py = (int)(((4095 - r) * 3200u) >> 12);
		int ex = px > 1079 ? 1079 : px, ey = py > 2399 ? 2399 : py;
		win_touch += (x != ex) + (y != ey);
	}
	sweet_hid_geometry(1440, 3200, 0, 0, &pw, &ph, &lw, &lh, &ox, &oy);
	printf(" p3s_geom=%%dx%%d,%%dx%%d,%%d,%%d", pw, ph, lw, lh, ox, oy);
	int l, r, t, b;
	sweet_hid_visible(pw, ph, lw, lh, ox, oy, &l, &r, &t, &b);
	printf(" p3s_visible=%%d..%%d,%%d..%%d", l, r, t, b);
	/* o ponto lógico L aparece no pixel L - off (SweetFramebuffer: dx -= fOffX);
	   tocar ali deve devolver L/lw */
	for (int L = 0; L < lw; L++) {
		int P = L - ox;
		uint32_t raw = (uint32_t)((((uint64_t)P << 12) + 1439) / 1440);
		int x, y;
		ts_panel_map(raw, 0, 0, 1440, 3200, 1440, 3200, &x, &y);
		IOFixed n = sweet_hid_norm(x, ox, lw), want = (IOFixed)(((int64_t)L << 16) / lw);
		if (x != P || n != want)
			roundtrip++;
	}
	for (int x = 0; x < 1440; x++) {
		IOFixed n = sweet_hid_norm(x, ox, lw);
		if (n < 0 || n > 0x10000)
			clamp_bad++;
	}
	printf(" outside_left=%%d outside_right=%%d", sweet_hid_norm(0, ox, lw), sweet_hid_norm(1439, ox, lw));
	sweet_hid_geometry(0, 0, 0, 0, &pw, &ph, &lw, &lh, &ox, &oy);
	printf(" fallback_geom=%%dx%%d,%%dx%%d,%%d,%%d", pw, ph, lw, lh, ox, oy);
	sweet_hid_geometry(1440, 3200, 1, 0, &pw, &ph, &lw, &lh, &ox, &oy);
	printf(" native_geom=%%dx%%d,%%dx%%d,%%d,%%d", pw, ph, lw, lh, ox, oy);
	/* 0148: escala */
	int fw, fh;
	sweet_present_fit(1440, 3200, 1125, 2436, &fw, &fh);
	printf(" fit=%%dx%%d", fw, fh);
	sweet_hid_geometry(1440, 3200, 0, 1, &pw, &ph, &lw, &lh, &ox, &oy);
	printf(" scaled_geom=%%dx%%d,%%dx%%d,%%d,%%d", pw, ph, lw, lh, ox, oy);
	sweet_hid_geometry(1080, 2400, 0, 1, &pw, &ph, &lw, &lh, &ox, &oy);
	printf(" t2s_scale_geom=%%dx%%d,%%dx%%d,%%d,%%d", pw, ph, lw, lh, ox, oy);
	sweet_hid_geometry(1440, 3200, 1, 1, &pw, &ph, &lw, &lh, &ox, &oy);
	printf(" native_scale_geom=%%dx%%d,%%dx%%d,%%d,%%d", pw, ph, lw, lh, ox, oy);
	/* fonte 1125x2436 com valor (y<<16)|x; blit da tela inteira */
	uint32_t *srcp = malloc((size_t)1125 * 2436 * 4), *pan = calloc((size_t)1440 * 3200, 4);
	for (int y = 0; y < 2436; y++)
		for (int x = 0; x < 1125; x++)
			srcp[y * 1125 + x] = ((uint32_t)y << 16) | (uint32_t)x | 0x80000000u;
	int px = (1440 - fw) / 2, py = (3200 - fh) / 2;
	int rows = sweet_fb_scaled_blit((const uint8_t *)srcp, (uint64_t)1125 * 2436 * 4, 1125 * 4, 0, 0, 0, 0, 1125, 2436,
	    (uint8_t *)pan, 1440 * 4, 1440, 3200, px, py, fw, fh, 1125, 2436);
	long blit_bad = 0, border_bad = 0, touch_blit_bad = 0;
	for (int Y = 0; Y < 3200; Y++)
		for (int X = 0; X < 1440; X++) {
			uint32_t v = pan[Y * 1440 + X];
			if (Y < py || Y >= py + fh) {
				border_bad += v != 0;
				continue;
			}
			uint32_t want = ((uint32_t)(((int64_t)(Y - py) * 2436) / fh) << 16) | (uint32_t)(((int64_t)X * 1125) / fw) | 0x80000000u;
			blit_bad += v != want;
		}
	/* toque no pixel (X,Y) deve apontar o mesmo pixel lógico que o blit desenhou ali */
	sweet_hid_geometry(1440, 3200, 0, 1, &pw, &ph, &lw, &lh, &ox, &oy);
	for (int X = 0; X < 1440; X++) {
		long lx = ((long)sweet_hid_norm(X, ox, lw) * 1125) >> 16;
		long want = ((long)X * 1125) / fw;
		touch_blit_bad += (lx < want - 1 || lx > want);
	}
	for (int Y = py; Y < py + fh; Y++) {
		long ly = ((long)sweet_hid_norm(Y, oy, lh) * 2436) >> 16;
		long want = ((long)(Y - py) * 2436) / fh;
		touch_blit_bad += (ly < want - 1 || ly > want);
	}
	/* retângulo parcial e fonte curta: só a área mapeada muda, sem ler além da fonte */
	memset(pan, 0, (size_t)1440 * 3200 * 4);
	int prow = sweet_fb_scaled_blit((const uint8_t *)srcp, (uint64_t)1125 * 2436 * 4, 1125 * 4, 0, 0, 100, 200, 300, 400,
	    (uint8_t *)pan, 1440 * 4, 1440, 3200, px, py, fw, fh, 1125, 2436);
	long outside = 0;
	int ax0 = px + 100 * fw / 1125, ax1 = px + 400 * fw / 1125, ay0 = py + 200 * fh / 2436, ay1 = py + 600 * fh / 2436;
	for (int Y = 0; Y < 3200; Y++)
		for (int X = 0; X < 1440; X++)
			if ((X < ax0 || X >= ax1 || Y < ay0 || Y >= ay1) && pan[Y * 1440 + X])
				outside++;
	memset(pan, 0, (size_t)1440 * 3200 * 4);
	sweet_fb_scaled_blit((const uint8_t *)srcp, 4096, 1125 * 4, 0, 0, 0, 0, 1125, 2436,
	    (uint8_t *)pan, 1440 * 4, 1440, 3200, px, py, fw, fh, 1125, 2436);
	long short_written = 0, short_beyond = 0;
	for (long i = 0; i < 1440L * 3200; i++)
		if (pan[i]) {
			short_written++;
			short_beyond += (pan[i] >> 16 & 0x7fff) != 0 || (pan[i] & 0xffff) >= 1024;
		}
	int zero_rows = sweet_fb_scaled_blit((const uint8_t *)srcp, 0, 1125 * 4, 0, 0, 0, 0, 0, 0,
	    (uint8_t *)pan, 1440 * 4, 1440, 3200, px, py, fw, fh, 1125, 2436);
	printf(" blit_rows=%%d blit_bad=%%ld border_bad=%%ld touch_blit_bad=%%ld partial_rows=%%d partial_outside=%%ld"
	    " short_src_pixels_ok=%%d empty_rect_rows=%%d",
	    rows, blit_bad, border_bad, touch_blit_bad, prow, outside, short_written > 0 && short_beyond == 0, zero_rows);
	free(srcp);
	free(pan);
	printf(" t2s_touch=%%ld t2s_hid=%%ld t2s_edge=%%ld win_touch=%%ld roundtrip=%%ld clamp_bad=%%ld\n",
	    t2s_touch, t2s_hid, t2s_edge, win_touch, roundtrip, clamp_bad);
	(void)ts_g_panel_w; (void)ts_g_panel_h; (void)ts_g_view_w; (void)ts_g_view_h;
	return 0;
}
'''

EXPECT = {
    "t2s_touch": "0", "t2s_hid": "0", "t2s_edge": "0",
    "t2s_geom": "1080x2400,1125x2436,22,18",
    "win_touch": "0",
    "p3s_geom": "1440x3200,1125x2436,-157,-382",
    "p3s_visible": "157..1281,382..2817",
    "roundtrip": "0", "clamp_bad": "0",
    "outside_left": "0", "outside_right": "65536",
    "fallback_geom": "1080x2400,1125x2436,22,18",
    "native_geom": "1440x3200,1440x3200,0,0",
    "fit": "1440x3118",
    "scaled_geom": "1440x3200,1440x3118,0,-41",
    "t2s_scale_geom": "1080x2400,1125x2436,22,18",
    "native_scale_geom": "1440x3200,1440x3200,0,0",
    "blit_rows": "3118", "blit_bad": "0", "border_bad": "0", "touch_blit_bad": "0",
    "partial_rows": str(((200 + 400) * 3118) // 2436 - (200 * 3118) // 2436), "partial_outside": "0",
    "short_src_pixels_ok": "1", "empty_rect_rows": "0",
}
LABELS = {
    "t2s_touch": "S21+: toque idêntico (4096 valores × 4 touch_flip)",
    "t2s_hid": "S21+: normalização HID idêntica em todas as linhas e colunas",
    "t2s_edge": "S21+: bordas de gesto idênticas em todos os pixels",
    "t2s_geom": "S21+: geometria HID = crop 22,18 como antes",
    "win_touch": "p3s-window: toque escalado ao painel e limitado à janela",
    "p3s_geom": "p3s tela cheia: iPhone X centrado, offsets -157,-382",
    "p3s_visible": "p3s tela cheia: região visível 157..1281 × 382..2817",
    "roundtrip": "p3s tela cheia: ida e volta pixel lógico → painel → HID",
    "clamp_bad": "p3s tela cheia: normalização sempre em [0, 1]",
    "outside_left": "p3s tela cheia: toque na borda preta esquerda = 0",
    "outside_right": "p3s tela cheia: toque na borda preta direita = 1",
    "fallback_geom": "console ausente: volta à geometria do S21+",
    "native_geom": "sweetfb_native=1: painel nativo sem offset",
    "fit": "0148: iPhone X escalado à largura do painel = 1440x3118",
    "scaled_geom": "0148: HID com escala mede 1440x3118 e borda -41",
    "t2s_scale_geom": "0148: sweetfb_scale no S21+ não muda nada",
    "native_scale_geom": "0148: sweetfb_native vence sweetfb_scale",
    "blit_rows": "0148: blit da tela inteira escreve 3118 linhas",
    "blit_bad": "0148: cada pixel do painel = vizinho mais próximo da fonte",
    "border_bad": "0148: bordas de 41 linhas intactas",
    "touch_blit_bad": "0148: toque aponta o pixel lógico que o blit desenhou (±1)",
    "partial_rows": "0148: retângulo parcial escreve só as linhas mapeadas",
    "partial_outside": "0148: nada fora do retângulo mapeado",
    "short_src_pixels_ok": "0148: fonte curta não é lida além do fim",
    "empty_rect_rows": "0148: retângulo vazio não escreve",
}


def git(*args, cwd, check=True):
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, check=check)


def head(path):
    return git("rev-parse", "HEAD", cwd=path).stdout.strip()


def extract(text, start, end_marker="\n}\n"):
    i = text.index(start)
    j = text.index(end_marker, i) + len(end_marker)
    return text[i:j]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--s21xnu", required=True)
    ap.add_argument("--dxb", required=True)
    ap.add_argument("--xnu", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    report = {"schema": "s21xnu-xnu-p3s-0146-0148/1", "checks": []}
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
        series = sorted(list(pathlib.Path(a.dxb, "patches").glob("*.patch")) +
                        list(pathlib.Path(a.s21xnu, "xnu", "patches").glob("*.patch")),
                        key=lambda p: p.name)
        applied, skipped = [], []
        for p in series:
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
        check("série: 0061 (apresentação iPhone X) aplicado", "0061-sweet-iphone-x-display-size.patch" in applied)
        check("série: 0060 (toque Goodix do Redmi) pulado", "0060-sweet-keys-touch-drivers.patch" not in applied)
        expected_files = {"0146": ["bsd/dev/sweet_touch.c"],
                          "0147": ["iokit/Kernel/arm/SweetFramebuffer.cpp", "iokit/Kernel/arm/hid/SweetHID.cpp"],
                          "0148": ["iokit/Kernel/arm/SweetFramebuffer.cpp", "iokit/Kernel/arm/hid/SweetHID.cpp"]}
        for p in PATCHES:
            tag = p.name[:4]
            r = git("apply", "--check", str(p), cwd=tree, check=False)
            check("%s aplica sobre a série" % tag, r.returncode == 0, r.stderr.strip()[:200])
            if r.returncode:
                report["result"] = "FAIL"
                return 1
            files = git("apply", "--numstat", str(p), cwd=tree).stdout.split()[2::3]
            check("%s muda só %s" % (tag, ", ".join(expected_files[tag])), files == expected_files[tag], files)
            git("apply", str(p), cwd=tree)
        touch = (tree / "bsd" / "dev" / "sweet_touch.c").read_text()
        hid = (tree / "iokit" / "Kernel" / "arm" / "hid" / "SweetHID.cpp").read_text()
        fb = (tree / "iokit" / "Kernel" / "arm" / "SweetFramebuffer.cpp").read_text()
        check("toque: boot-args touch_panel_w/h e console lidos",
              'PE_parse_boot_argn("touch_panel_w"' in touch and "PE_current_console(&v)" in touch)
        check("toque: fórmula fixa 1080/2400 fora do caminho de postagem", "t->x * 1080u" not in touch)
        check("HID: geometria vinda do console", "PE_current_console(&video)" in hid and "1079 ?" not in hid)
        check("FB: letterbox habilitado para painel maior",
              "fWidth >= SWEET_FB_LOGICAL_W && fHeight >= SWEET_FB_LOGICAL_H" in fb)
        check("FB/HID: sweetfb_scale lido nos dois lados",
              'PE_parse_boot_argn("sweetfb_scale"' in fb and 'PE_parse_boot_argn("sweetfb_scale"' in hid)
        src = HOST_TEST % {
            "touch": extract(touch, "#define S21_PANEL_MAXX"),
            "hid": "\n".join(extract(hid, "static inline %s\nsweet_hid_%s" % (rt, n))
                             for rt, n in (("void", "fit"), ("void", "geometry"), ("void", "visible"),
                                           ("IOFixed", "norm"))),
            "fb": extract(fb, "static inline void\nsweet_present_fit") + "\n" +
                  extract(fb, "static int32_t\nsweet_fb_scaled_blit"),
        }
        (tmp / "t.c").write_text(src)
        cc = shutil.which("cc") or shutil.which("gcc")
        subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", str(tmp / "t.c"), "-o",
                        str(tmp / "t")], check=True)
        out = subprocess.run([str(tmp / "t")], capture_output=True, text=True, check=True).stdout.strip()
        vals = dict(kv.split("=", 1) for kv in out.split())
        report["host_test"] = vals
        for key, want in EXPECT.items():
            check(LABELS[key], vals.get(key) == want, vals.get(key))
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"], "| série: %d aplicados, %d pulados" %
          (len(report["series"]["applied"]), len(report["series"]["skipped"])))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
