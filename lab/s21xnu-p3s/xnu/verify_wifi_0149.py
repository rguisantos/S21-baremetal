#!/usr/bin/env python3
"""Confere o patch XNU 0149: enumeração do Wi-Fi BCM4389 do p3s no PCIe canal 0.

  verify_wifi_0149.py --s21xnu CLONE [--json r.json]

CLONE: s21xnu no commit fixado (a128f07). O 0149 altera bsd/dev/sweet_wifi.c,
que o script 0142-s21-wifi.sh escreve num heredoc com delimitador entre aspas
(texto literal, sem expansão do shell). **O script não é executado** (ele baixa
código do z3sios): o heredoc é lido como texto e gravado numa árvore
temporária, onde o 0149 passa por `git apply --check` e é aplicado.

Depois:
- confere a estrutura: o S21/S21+ (14e4:4475) continua chegando a
  redwood_bcm4375_run; o p3s (14e4:4441) para antes do pool DMA e do driver;
  a leitura do chipid só acontece com sweetwifi>=3;
- extrai as funções puras sweet_wifi_radio/sweet_wifi_chip/sweet_wifi_chiprev
  e compila um teste de host com -Wall -Wextra -Werror.
O XNU não é compilado aqui; o build real é o workflow xnu do fork.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PATCH = HERE / "0149-s21-p3s-wifi-enumerate.patch"
S21XNU_COMMIT = "a128f07b04987e60f5e13e2ce67b19ae009672cd"
SCRIPT = "xnu/patches/0142-s21-wifi.sh"
OPEN = "cat > bsd/dev/sweet_wifi.c <<'EOF_SWEET_SRC'\n"
CLOSE = "\nEOF_SWEET_SRC\n"

HOST_TEST = r'''
#include <stdio.h>
#include <stdint.h>
%s
int main(void)
{
	struct { uint32_t id; int want; } c[] = {
		{0x447514e4U, SWEET_WIFI_BCM4375}, {0x444114e4U, SWEET_WIFI_BCM4389},
		{0xffffffffU, SWEET_WIFI_NONE}, {0x00000001U, SWEET_WIFI_NONE},
		{0x14e44441U, SWEET_WIFI_NONE}, {0x447614e4U, SWEET_WIFI_NONE}, {0x444114e5U, SWEET_WIFI_NONE},
	};
	int bad = 0;
	for (unsigned i = 0; i < sizeof(c) / sizeof(c[0]); i++)
		bad += (int)sweet_wifi_radio(c[i].id) != c[i].want;
	printf("radio_bad=%%d", bad);
	printf(" chip=%%x rev=%%u", sweet_wifi_chip(0x15334389U), sweet_wifi_chiprev(0x15334389U));
	printf(" chip_ff=%%x rev_ff=%%u\n", sweet_wifi_chip(0xffffffffU), sweet_wifi_chiprev(0xffffffffU));
	return 0;
}
'''
EXPECT = {"radio_bad": "0", "chip": "4389", "rev": "3", "chip_ff": "ffff", "rev_ff": "15"}


def git(*args, cwd, check=True):
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, check=check)


def extract(text, start, end_marker="\n}\n"):
    i = text.index(start)
    return text[i:text.index(end_marker, i) + len(end_marker)]


def heredoc(script):
    i = script.index(OPEN) + len(OPEN)
    return script[i:script.index(CLOSE, i) + 1]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--s21xnu", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    report = {"schema": "s21xnu-p3s-wifi-0149/1", "checks": []}
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        report["checks"].append({"check": name, "ok": bool(cond), "detail": str(detail)})
        print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))

    got = git("rev-parse", "HEAD", cwd=a.s21xnu).stdout.strip()
    check("s21xnu fixado", got == S21XNU_COMMIT, got[:12])
    script = pathlib.Path(a.s21xnu, SCRIPT).read_text()
    check("0142: heredoc literal (delimitador entre aspas)", OPEN in script and CLOSE in script)
    if not ok:
        return 1
    with tempfile.TemporaryDirectory() as t:
        tree = pathlib.Path(t)
        src = tree / "bsd" / "dev" / "sweet_wifi.c"
        src.parent.mkdir(parents=True)
        src.write_text(heredoc(script))
        git("init", "-q", cwd=tree)
        r = git("apply", "--check", str(PATCH), cwd=tree, check=False)
        check("0149 aplica sobre o sweet_wifi.c do 0142", r.returncode == 0, r.stderr.strip()[:200])
        if r.returncode:
            report["result"] = "FAIL"
            return 1
        files = git("apply", "--numstat", str(PATCH), cwd=tree).stdout.split()[2::3]
        check("0149 muda só bsd/dev/sweet_wifi.c", files == ["bsd/dev/sweet_wifi.c"], files)
        git("apply", str(PATCH), cwd=tree)
        c = src.read_text()
        thread = extract(c, "static void\nwifi_thread(")
        link = extract(c, "static int\npower_and_link(void)")
        i_link = thread.index("power_and_link()")
        i_p3s = thread.index("radio == SWEET_WIFI_BCM4389")
        i_pool = thread.index("dma_pool()")
        i_drv = thread.index("redwood_bcm4375_run(&bus)")
        p3s_block = thread[i_p3s:i_pool]
        check("ordem: enlace → ramo p3s → pool DMA → driver 4375", i_link < i_p3s < i_pool < i_drv)
        check("p3s: sai antes do pool DMA e do driver", "return;" in p3s_block and "W4 SKIP" in p3s_block)
        check("p3s: chipid só com sweetwifi>=3", re.search(r"wifi_level >= 3\)\s*\{\s*bcm4389_chipid\(\);", p3s_block))
        check("enlace: rejeita endpoint desconhecido", "radio == SWEET_WIFI_NONE" in link and "return -1;" in link)
        check("enlace: log cita 14e4:4475 e 14e4:4441", "14e4:4475" in link and "14e4:4441" in link)
        chipid = extract(c, "static void\nbcm4389_chipid(void)")
        check("chipid: janela BAR0 na base de enumeração 0x18000000", "wr(cfgw, 0x80, 0x18000000U)" in chipid)
        check("chipid: só lê o chip (nenhuma escrita no BAR mapeado)", not re.search(r"wr\(m,|rmw\(m,", chipid))
        check("S21/S21+: chamada do driver 4375 preservada", c.count("redwood_bcm4375_run(&bus);") == 1)
        pure = (extract(c, "enum sweet_wifi_radio {", "};\n") +
                extract(c, "static inline enum sweet_wifi_radio\nsweet_wifi_radio") +
                extract(c, "static inline uint32_t\nsweet_wifi_chip(") +
                extract(c, "static inline uint32_t\nsweet_wifi_chiprev("))
        (tree / "t.c").write_text(HOST_TEST % pure)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", str(tree / "t.c"), "-o",
                        str(tree / "t")], check=True)
        out = subprocess.run([str(tree / "t")], capture_output=True, text=True, check=True).stdout.split()
        vals = dict(kv.split("=", 1) for kv in out)
        report["host_test"] = vals
        for k, want in EXPECT.items():
            check("host: %s = %s" % (k, want), vals.get(k) == want, vals.get(k))
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"])
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
