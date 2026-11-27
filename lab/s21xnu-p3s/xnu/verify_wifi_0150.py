#!/usr/bin/env python3
"""Confere o patch XNU 0150: firmware do BCM4389 (ARM CA7 + SYSMEM) no driver do 0142.

  verify_wifi_0150.py --s21xnu CLONE --z3sios CLONE_Z3SIOS [--json r.json]

CLONE: s21xnu no commit fixado (a128f07). CLONE_Z3SIOS: N1709/z3sios no commit
que o 0142 fixa (Z3S_SHA). O 0142 baixa redwood_bcm4375.c desse commit e confere
o SHA-256; aqui o arquivo vem do clone e o hash é conferido contra a lista do
próprio script. **O script não é executado.**

Árvore temporária: sweet_wifi.c (heredoc do 0142, como texto) + 0149, e
redwood_bcm4375.c do z3sios; o 0150 passa por `git apply --check` e é aplicado.
Depois confere a estrutura do caminho CA7 (seguindo dhdpcie_bus_download_state()
do bcmdhd_101_18 Samsung) e que o caminho do BCM4375 continua igual, e compila
no host a decodificação de bancos do SYSMEM. O XNU não é compilado aqui.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
P0149 = HERE / "0149-s21-p3s-wifi-enumerate.patch"
P0150 = HERE / "0150-s21-p3s-wifi-bcm4389-firmware.patch"
S21XNU_COMMIT = "a128f07b04987e60f5e13e2ce67b19ae009672cd"
SCRIPT = "xnu/patches/0142-s21-wifi.sh"
OPEN = "cat > bsd/dev/sweet_wifi.c <<'EOF_SWEET_SRC'\n"
CLOSE = "\nEOF_SWEET_SRC\n"
DRV = "kernel/xnu/files/bsd/dev/redwood_bcm4375.c"

HOST_TEST = r'''
#include <stdio.h>
#include <stdint.h>
%s
int main(void)
{
	uint32_t r, n;
	/* rev < 12: ROM banks bits 5..9, RAM banks bits 0..4 */
	sysmem_banks((3u << 5) | 17u, 11, &r, &n);
	printf("old=%%u,%%u", r, n);
	/* rev >= 12: ROM banks bits 24..31, RAM banks bits 16..23 */
	sysmem_banks((5u << 24) | (40u << 16) | 0x3ffu, 12, &r, &n);
	printf(" new=%%u,%%u", r, n);
	sysmem_banks(0xffffffffu, 20, &r, &n);
	printf(" ones=%%u,%%u\n", r, n);
	return 0;
}
'''
EXPECT = {"old": "3,17", "new": "5,40", "ones": "255,255"}


def git(*args, cwd, check=True):
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, check=check)


def extract(text, start, end_marker="\n}\n"):
    i = text.index(start)
    return text[i:text.index(end_marker, i) + len(end_marker)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--s21xnu", required=True)
    ap.add_argument("--z3sios", required=True)
    ap.add_argument("--json")
    ap.add_argument("--save-driver", help="grava o redwood_bcm4375.c com 0150 (para sim_wifi_0150.py)")
    a = ap.parse_args(argv)
    report = {"schema": "s21xnu-p3s-wifi-0150/1", "checks": []}
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        report["checks"].append({"check": name, "ok": bool(cond), "detail": str(detail)})
        print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))

    got = git("rev-parse", "HEAD", cwd=a.s21xnu).stdout.strip()
    check("s21xnu fixado", got == S21XNU_COMMIT, got[:12])
    script = pathlib.Path(a.s21xnu, SCRIPT).read_text()
    z3s = re.search(r"^Z3S_SHA=([0-9a-f]{40})$", script, re.M)
    want_sum = re.search(r"^([0-9a-f]{64}) bsd/dev/redwood_bcm4375\.c$", script, re.M)
    zgot = git("rev-parse", "HEAD", cwd=a.z3sios).stdout.strip()
    check("z3sios no commit do 0142", z3s and zgot == z3s.group(1), zgot[:12])
    drv_bytes = pathlib.Path(a.z3sios, DRV).read_bytes()
    drv_sum = hashlib.sha256(drv_bytes).hexdigest()
    check("redwood_bcm4375.c com o SHA-256 do 0142", want_sum and drv_sum == want_sum.group(1), drv_sum[:16])
    if not ok:
        return 1
    with tempfile.TemporaryDirectory() as t:
        tree = pathlib.Path(t)
        dev = tree / "bsd" / "dev"
        dev.mkdir(parents=True)
        i = script.index(OPEN) + len(OPEN)
        (dev / "sweet_wifi.c").write_text(script[i:script.index(CLOSE, i) + 1])
        (dev / "redwood_bcm4375.c").write_bytes(drv_bytes)
        git("init", "-q", cwd=tree)
        r = git("apply", str(P0149), cwd=tree, check=False)
        check("0149 aplica", r.returncode == 0, r.stderr.strip()[:200])
        r = git("apply", "--check", str(P0150), cwd=tree, check=False)
        check("0150 aplica sobre 0142 + 0149 + redwood_bcm4375.c", r.returncode == 0, r.stderr.strip()[:200])
        if not ok:
            report["result"] = "FAIL"
            return 1
        files = git("apply", "--numstat", str(P0150), cwd=tree).stdout.split()[2::3]
        check("0150 muda só sweet_wifi.c e redwood_bcm4375.c",
              files == ["bsd/dev/sweet_wifi.c", "bsd/dev/redwood_bcm4375.c"], files)
        git("apply", str(P0150), cwd=tree)
        sw = (dev / "sweet_wifi.c").read_text()
        d = (dev / "redwood_bcm4375.c").read_text()
        if a.save_driver:
            pathlib.Path(a.save_driver).write_text(d)

        thread = extract(sw, "static void\nwifi_thread(")
        blk = thread[thread.index("radio == SWEET_WIFI_BCM4389"):thread.index("dma_pool()")]
        check("sweet_wifi: p3s abaixo do nível 4 para com W4 SKIP",
              re.search(r"if \(wifi_level < 4\) \{[^}]*W4 SKIP[^}]*return;\s*\}", blk))
        check("sweet_wifi: p3s no nível 4 segue para pool e driver",
              blk.count("return;") == 1 and "redwood_bcm4375_run(&bus)" in thread)

        code = [l for l in d.splitlines() if "RAMBASE_4375" in l]
        check("driver: RAMBASE_4375 só no #define e no valor inicial de rambase",
              len(code) == 3 and all(l.startswith("#define") or "static uint32_t rambase = RAMBASE_4375" in l
                                     or l.lstrip().startswith("/*") for l in code), code)
        chip = extract(d, "static bool\nchip(void)")
        check("chip(): 0x4389 → CA7, RAM 0x200000, arquivos bcm4389-*",
              re.search(r"CID_ID\(id\) == 0x4389\) \{\s*ca7 = true;\s*rambase = RAMBASE_4389;\s*fwp = \"bcm4389\";", chip)
              and "#define RAMBASE_4389            0x200000" in d)
        check("chip(): CA7 0x847 e SYSMEM 0x849 do EROM",
              "core_find(ca7 ? CORE_ARM_CA7 : CORE_ARM_CR4, 0)" in chip and "core_find(CORE_SYSMEM, 0)" in chip
              and "#define CORE_ARM_CA7            0x847" in d and "#define CORE_SYSMEM             0x849" in d)
        check("chip(): RAM do SYSMEM no CA7, do CR4 no BCM4375",
              "ramsize = ca7 ? sysmem_ramsize() : cr4_ramsize();" in chip)
        check("chip(): BAR2 remapeado só se o BAR2 cobre rambase + ramsize",
              "rambase + ramsize <= bus->bar2_size" in chip)
        check("chip(): no CA7, RAM além do BAR2 fica para o tamanho declarado pela imagem",
              "(!ca7 && rambase + ramsize > tcm_size)" in chip and "left to the image's own RAM size" in chip)
        bars = extract(d, "static bool\nbars(void)")
        check("bars(): BAR2 grande demais para vir depois do BAR0 vai primeiro (só se alinhado)",
              "(bus->mem_phys & (s2 - 1)) == 0" in bars and "bar2 = bus->mem_phys;" in bars
              and bars.index("bar2 = (uint32_t)((bar0 + s0 + s2 - 1) & ~(s2 - 1));") < bars.index("bar2 = bus->mem_phys;"))
        pas = extract(d, "static void\nca7_passive(void)")
        check("ca7_passive: janela BAR1 = 0, CA7 parado, SYSMEM reset (download_state enter)",
              pas.index("w32(cfg, 0x84, 0)") < pas.index("core_reset(cr4, ARMCR4_CPUHALT, ARMCR4_CPUHALT, ARMCR4_CPUHALT)")
              < pas.index("core_reset(sysmem, 0, 0, 0)"))
        act = extract(d, "static bool\nca7_active(uint32_t rstvec)")
        check("ca7_active: vetor seguro (0xffffffff) recusado antes de escrever",
              act.index("0xffffffffU") < act.index("return false;") < act.index("tcm_w32(0, rstvec)")
              < act.index("core_reset(cr4, ARMCR4_CPUHALT, 0, 0)"))
        fw = extract(d, "static bool\nfirmware(void)")
        i_pas, i_copy = fw.index("ca7_passive();"), fw.index("*(volatile uint32_t *)(tcm + rambase + at) = word;")
        i_seed, i_act = fw.index("SEED_MAGIC"), fw.index("ca7_active(resetintr)")
        check("firmware(): parar → firmware → NVRAM/semente → soltar", i_pas < i_copy < i_seed < i_act)
        i_smar, i_fit = fw.index("RAMSIZE_MAGIC"), fw.index("if (rambase + ramsize > tcm_size)")
        check("firmware(): RAM (já com o SMAR) conferida contra o BAR2 antes de parar o ARM", i_smar < i_fit < i_pas)
        check("firmware(): BCM4375 mantém cr4_passive/cr4_active", "cr4_passive();" in fw and "cr4_active(resetintr);" in fw)
        check("firmware(): murata só fora do CA7", 'which == 1 && !ca7 ? "murata" : "semco"' in fw)
        clm = extract(d, "static int\nclm_load(void)")
        check("clm_load(): nome pelo prefixo do chip", 'snprintf(clmname, sizeof(clmname), "%s-clm.blob", fwp)' in clm)

        (tree / "t.c").write_text(HOST_TEST % extract(d, "static inline void\nsysmem_banks("))
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", str(tree / "t.c"), "-o",
                        str(tree / "t")], check=True)
        out = subprocess.run([str(tree / "t")], capture_output=True, text=True, check=True).stdout.split()
        vals = dict(kv.split("=", 1) for kv in out)
        report["host_test"] = vals
        for k, want in EXPECT.items():
            check("host: sysmem_banks %s = %s" % (k, want), vals.get(k) == want, vals.get(k))
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"])
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
