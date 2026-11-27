#!/usr/bin/env python3
"""Compara o decodificador da S Pen (sweet_wacom.h) com o driver Samsung, pacote a pacote.

  test_spen_decode.py --wacom-src wacom_i2c.c [--json r.json]

wacom_i2c.c: drivers/input/sec_input/wacom/wacom_i2c.c do FlopKernel no
commit fixado (SHA-256 conferido). Do arquivo são extraídas, sem mudança,
epen_location_detect(), wacom_i2c_coord_modify() e wacom_i2c_coord_handler();
as chamadas input_report_abs/key/input_sync passam a gravar eventos. O
sweet_wacom.h é traduzido para a mesma lista de eventos Linux por um
adaptador e os dois são comparados em cada pacote:

- sequência roteirizada: aproximação → movimento sem tocar → contato com
  pressão → botão lateral → solta a ponta → borracha → saída, mais pacotes
  fora do painel e um "não pronto" com a caneta longe;
- os quatro cantos e o centro, com inclinação, conferidos também contra a
  orientação esperada do p3s (x invertido, eixos trocados);
- 20 000 pacotes aleatórios (semente fixa), metade dentro e metade fora do
  painel.

Compilado com -funsigned-char: no arm64 o `char *data` do driver é sem sinal.
"""
import argparse
import hashlib
import json
import pathlib
import random
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
WACOM_SHA256 = "1f5090001c57b3e33cd5f9ba3937a3386b81fa8df07874cf5f4ec2c3667c147d"
MAX_X, MAX_Y = 15776, 7099          # brutos; o Android mostra ABS_X 0..7099 e ABS_Y 0..15776 (eixos trocados)

PRELUDE = r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#include <stdlib.h>
typedef uint8_t u8; typedef int8_t s8; typedef uint16_t u16; typedef int16_t s16; typedef uint32_t u32;
#define unlikely(x) (x)
#define IS_ENABLED(x) 0
#define WACOM_PRODUCT_SHIP 1
#define WACOM_DEBUG_PRINT_COORDEVENT 0x04
#define WACOM_DEBUG_PRINT_ALLEVENT 0x08
#define input_info(...) ((void)0)
#define input_raw_info(...) ((void)0)
#define ABS_X 0x00
#define ABS_Y 0x01
#define ABS_PRESSURE 0x18
#define ABS_DISTANCE 0x19
#define ABS_TILT_X 0x1a
#define ABS_TILT_Y 0x1b
#define BTN_TOOL_PEN 0x140
#define BTN_TOOL_RUBBER 0x141
#define BTN_TOUCH 0x14a
#define BTN_STYLUS 0x14b
static char evs[2][512];
static int evw;
static void rec(const char *k, int code, int v) { char b[32]; snprintf(b, sizeof(b), "%s%x=%d ", k, code, v); strcat(evs[evw], b); }
#define input_report_abs(dev, code, v) rec("A", (code), (v))
#define input_report_key(dev, code, v) rec("K", (code), (v))
#define input_sync(dev) strcat(evs[evw], "S ")
struct i2c_client { int dev; };
struct wacom_g5_platform_data { u32 origin[2]; int x_invert, y_invert, xy_switch, max_x, max_y;
	u32 area_indicator, area_navigation, area_edge; };
struct wacom_i2c { struct wacom_g5_platform_data *pdata; struct i2c_client *client; void *input_dev; int nb;
	u16 hi_x, hi_y, p_x, p_y, x, y; s8 tilt_x, tilt_y; u16 pressure, height; int tool; u32 mcount;
	int pen_prox, pen_pressed, side_pressed; u8 debug_flag; };
'''

MAIN = r'''
#include "sweet_wacom.h"
static void ours_events(const struct sweet_wacom_ev *e)
{
	if (e->kind == SWEET_PEN_REPORT) {
		rec("A", ABS_X, e->x); rec("A", ABS_Y, e->y);
		rec("K", BTN_STYLUS, e->side); rec("K", BTN_TOUCH, e->touch);
		rec("A", ABS_PRESSURE, e->pressure); rec("A", ABS_DISTANCE, e->height);
		rec("A", ABS_TILT_X, e->tilt_x); rec("A", ABS_TILT_Y, e->tilt_y);
		rec("K", e->eraser ? BTN_TOOL_RUBBER : BTN_TOOL_PEN, 1); strcat(evs[1], "S ");
	} else if (e->kind == SWEET_PEN_OUT) {
		rec("A", ABS_PRESSURE, 0); rec("K", BTN_STYLUS, 0); rec("K", BTN_TOUCH, 0); strcat(evs[1], "S ");
		rec("A", ABS_DISTANCE, 0); rec("K", BTN_TOOL_RUBBER, 0); rec("K", BTN_TOOL_PEN, 0); strcat(evs[1], "S ");
	}
}
int main(void)
{
	struct wacom_g5_platform_data pd = { { 0, 0 }, 1, 0, 1, %MAX_X%, %MAX_Y%, 0, 0, 0 };
	struct i2c_client cl = { 0 };
	struct wacom_i2c w = { 0 };
	struct sweet_wacom_cfg cfg = { 0, 0, %MAX_X%, %MAX_Y%, 1, 0, 1 };
	struct sweet_wacom_state st = { 0 };
	struct sweet_wacom_ev e;
	char line[128];
	unsigned b[16];
	w.pdata = &pd; w.client = &cl;
	while (fgets(line, sizeof(line), stdin)) {
		char data[17] = { 0 };
		uint8_t d[16];
		if (sscanf(line, "%x %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x", &b[0], &b[1], &b[2], &b[3], &b[4], &b[5],
		    &b[6], &b[7], &b[8], &b[9], &b[10], &b[11], &b[12], &b[13], &b[14], &b[15]) != 16) return 2;
		for (int i = 0; i < 16; i++) data[i] = (char)b[i], d[i] = (uint8_t)b[i];
		evs[0][0] = evs[1][0] = 0;
		evw = 0; wacom_i2c_coord_handler(&w, data);
		evw = 1; sweet_wacom_coord(&st, &cfg, d, &e); ours_events(&e);
		printf("SAMSUNG %s| prox=%d pressed=%d side=%d\n", evs[0], w.pen_prox, w.pen_pressed, w.side_pressed);
		printf("OURS %s| prox=%d pressed=%d side=%d kind=%d x=%u y=%u tx=%d ty=%d\n", evs[1], st.prox, st.pressed,
		    st.side, e.kind, e.x, e.y, e.tilt_x, e.tilt_y);
	}
	printf("PX %u %u %u\n", sweet_wacom_to_px(0, 7099, 1440), sweet_wacom_to_px(7099, 7099, 1440),
	    sweet_wacom_to_px(15776 / 2, 15776, 3200));
	return 0;
}
'''


def extract(src):
    i = src.index("#define EPEN_LOCATION_DETECT_SIZE")
    j = src.index("static void wacom_i2c_coord_handler(")
    k = src.index("\n}\n", j) + 3
    return src[i:k]


def pkt(flags, x, y, p=0, h=0, tx=0, ty=0):
    return [0x01 | flags, x >> 8 & 0xff, x & 0xff, y >> 8 & 0xff, y & 0xff, p >> 8 & 0x0f, p & 0xff, h,
            tx & 0xff, ty & 0xff, 0, 0, 0, 0, 0, 0]


RDY, TIP, SIDE, ERASER = 0x80, 0x10, 0x20, 0x40


def script():
    s = [pkt(0, 0, 0)]                                                 # longe, não pronto: nada
    s += [pkt(RDY, 8000, 3500, h=200)]                                 # aproximação: só marca
    s += [pkt(RDY, 8000 + i * 10, 3500 - i * 5, h=120 - i) for i in range(5)]  # movimento sem tocar
    s += [pkt(RDY | TIP, 8100, 3450, p=1200 + i * 300, h=0, tx=10, ty=-20) for i in range(4)]  # contato
    s += [pkt(RDY | TIP | SIDE, 8120, 3440, p=2000)]                   # botão lateral com a ponta
    s += [pkt(RDY | SIDE, 8130, 3430, h=30)]                           # solta a ponta, botão ainda
    s += [pkt(RDY, 8140, 3420, h=60)]                                  # solta o botão
    s += [pkt(RDY, 20000, 3420), pkt(RDY, 8140, 9000)]                 # fora do painel: descartados
    s += [pkt(RDY | ERASER | TIP, 8150, 3410, p=500)]                  # borracha
    s += [pkt(0, 8150, 3410)]                                          # saída
    s += [pkt(0, 8150, 3410)]                                          # de novo: nada (já fora)
    return s


CORNERS = [  # (bruto x, bruto y, inclinação) e o esperado no painel: (y, MAX_X - x), inclinação (ty, -tx)
    (0, 0, (5, 7)), (MAX_X, 0, (-63, 63)), (0, MAX_Y, (63, -63)), (MAX_X, MAX_Y, (-1, 1)),
    (MAX_X // 2, MAX_Y // 2, (12, -34)),
]


def corners():
    s = []
    for x, y, (tx, ty) in CORNERS:
        s += [pkt(RDY, x, y, tx=tx, ty=ty), pkt(RDY, x, y, h=10, tx=tx, ty=ty), pkt(0, x, y)]
    return s


def fuzz(n=20000, seed=20261127):
    r = random.Random(seed)
    flags = [0, RDY, RDY | TIP, RDY | SIDE, RDY | TIP | SIDE, RDY | ERASER, RDY | ERASER | TIP, ERASER, TIP]
    s = []
    for _ in range(n):
        inside = r.random() < 0.5
        x = r.randint(0, MAX_X) if inside else r.randint(0, 0xFFFF)
        y = r.randint(0, MAX_Y) if inside else r.randint(0, 0xFFFF)
        p = pkt(r.choice(flags), x, y, p=r.randint(0, 0xFFF), h=r.randint(0, 255),
                tx=r.randint(-128, 127), ty=r.randint(-128, 127))
        p[5] |= r.randint(0, 15) << 4                                  # nibble alto do byte 5: ignorado
        s.append(p)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--wacom-src", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    report = {"schema": "s21xnu-p3s-spen-decode/1", "checks": []}
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        report["checks"].append({"check": name, "ok": bool(cond), "detail": str(detail)[:300]})
        print("%s %s %s" % ("PASS" if cond else "FAIL", name, str(detail)[:160]))

    src = pathlib.Path(a.wacom_src).read_bytes()
    check("wacom_i2c.c do FlopKernel dc17ad0", hashlib.sha256(src).hexdigest() == WACOM_SHA256)
    if not ok:
        return 1
    c = PRELUDE + extract(src.decode()) + MAIN.replace("%MAX_X%", str(MAX_X)).replace("%MAX_Y%", str(MAX_Y))
    with tempfile.TemporaryDirectory() as t:
        cf, exe = pathlib.Path(t, "spen.c"), pathlib.Path(t, "spen")
        cf.write_text(c)
        r = subprocess.run(["cc", "-std=gnu11", "-O1", "-funsigned-char", "-Wall", "-Wno-unused-function",
                            "-Wno-unused-variable", "-Wno-parentheses", "-I", str(HERE), str(cf), "-o", str(exe)],
                           capture_output=True, text=True)
        check("Samsung + sweet_wacom.h compilam juntos", r.returncode == 0, r.stderr)
        if r.returncode:
            return 1

        def run(pkts):
            inp = "".join(" ".join("%02x" % b for b in p) + "\n" for p in pkts)
            out = subprocess.run([str(exe)], input=inp, capture_output=True, text=True, check=True).stdout
            lines = out.splitlines()
            sam = [l[8:] for l in lines if l.startswith("SAMSUNG ")]
            our = [l[5:] for l in lines if l.startswith("OURS ")]
            return sam, our, lines

        for name, pk in (("roteiro", script()), ("cantos", corners()), ("aleatório", fuzz())):
            sam, our, lines = run(pk)
            mism = [i for i, (s, o) in enumerate(zip(sam, our)) if s != o.split(" kind=")[0]]
            check("%s: %d pacotes, eventos e estado iguais aos do driver Samsung" % (name, len(pk)),
                  len(sam) == len(pk) and not mism, mism[:3] and (sam[mism[0]], our[mism[0]]))
            if name == "roteiro":
                kinds = [int(o.split("kind=")[1].split()[0]) for o in our]
                report["script_kinds"] = kinds
                check("roteiro: nada / entra / 5 movimentos / 4 contatos / lateral / solta / solta botão / "
                      "2 descartes / borracha / sai / nada",
                      kinds == [0, 1] + [2] * 5 + [2] * 4 + [2, 2, 2] + [4, 4] + [2, 3, 0], kinds)
                check("roteiro: o pacote de aproximação não publica nada", sam[1].startswith("| prox=1"), sam[1])
                check("roteiro: saída solta ponta, botão e ferramenta",
                      "K14a=0" in sam[-2] and "K140=0" in sam[-2] and "K141=0" in sam[-2], sam[-2])
            if name == "cantos":
                got = []
                for i, (x, y, (tx, ty)) in enumerate(CORNERS):
                    o = our[3 * i + 1]
                    v = dict(kv.split("=") for kv in o.split("| ")[1].split() if "=" in kv)
                    got.append((int(v["x"]), int(v["y"]), int(v["tx"]), int(v["ty"])))
                want = [(y, MAX_X - x, ty, -tx) for x, y, (tx, ty) in CORNERS]
                check("cantos: x do painel = y bruto, y do painel = máx − x bruto, inclinação (ty, −tx)",
                      got == want, got)
            report[name] = {"packets": len(pk), "mismatches": len(mism)}
        px = run([])[2][-1].split()[1:]
        check("pixels: 0 → 0, 7099 → 1439, meio de 15776 → 1600", px == ["0", "1439", "1600"], px)
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"])
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
