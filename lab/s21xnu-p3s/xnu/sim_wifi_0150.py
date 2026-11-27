#!/usr/bin/env python3
"""Roda no host o código real do driver de Wi-Fi (0142 + 0150) contra um chip Broadcom simulado.

  sim_wifi_0150.py --driver redwood_bcm4375.c [--json r.json]

O driver vem de `verify_wifi_0150.py --save-driver` (z3sios fixado + 0150).
Deste arquivo são extraídas, sem mudança de lógica, as funções do caminho de
carga: bars(), chip(), firmware() e o que elas chamam (janela do BAR0, EROM,
reset de núcleos, tamanhos de RAM, NVRAM, semente). Só os acessos a
registradores (r32/w32/r16/w16) passam a ir para um modelo em C:

- espaço de configuração do endpoint, com a janela do BAR0 (0x80) e a do
  BAR1 do bcmdhd (0x84);
- backplane: ChipCommon (chipid, ponteiro do EROM), EROM gerado com os
  núcleos do cenário, wrappers com IOCTL/RESET_CTL, SYSMEM (coreinfo,
  bancos), ARM CR4 (cap, bancos), PCIe2;
- BAR2 como memória do host com páginas além do mapeado em PROT_NONE: uma
  escrita fora do que o driver mapeou derruba o processo, como derrubaria o
  kernel;
- "firmware": quando o ARM sai de reset sem CPUHALT, grava o endereço da
  área compartilhada na última palavra da RAM.

Cenários: o BCM4389 do p3s (RAM cabe; RAM do SYSMEM além do BAR2 com e sem
SMAR; BAR2 de 8 MiB com remapeamento; vetor de reset protegido), o BCM4375
do S21/S21+ (regressão) e um chip desconhecido. Cada um confere o resultado,
a ordem dos eventos e o conteúdo da RAM.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile

FUNCS = ["blog", "r32", "w32", "r16", "w16", "window", "bp_read", "bp_write", "pcie2_read", "pcie2_write",
         "tcm_r32", "tcm_w32", "in_ram", "erom_desc", "erom_regaddr", "erom_scan", "core_find", "core_disable",
         "core_reset", "cr4_ramsize", "cr4_passive", "cr4_active", "sysmem_banks", "sysmem_ramsize", "ca7_passive",
         "ca7_active", "le32", "nvram_make", "fw_file", "fw_release", "bars", "chip", "firmware"]

PRELUDE = r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include <sys/mman.h>
#include <unistd.h>
typedef uintptr_t vm_offset_t;
typedef size_t vm_size_t;
typedef void *thread_t;
typedef void *mbuf_t;
#define __printflike(a, b) __attribute__((format(printf, a, b)))
#define VM_WIMG_IO 0
#define Z_WAITOK 0
#define Z_ZERO 1
#define NSEC_PER_MSEC 1000000ULL
#define kalloc_data(n, f) calloc(1, (n))
#define kfree_data(p, n) free((void *)(p))
static size_t sl_strlcpy(char *d, const char *s, size_t n) { size_t l = strlen(s); if (n) { size_t c = l < n - 1 ? l : n - 1; memcpy(d, s, c); d[c] = 0; } return l; }
#define strlcpy sl_strlcpy
static void delay(int us) { (void)us; }
static uint64_t sim_clock;
static uint64_t mach_absolute_time(void) { return sim_clock += 1000; }
static void clock_interval_to_deadline(uint32_t n, uint64_t unit, uint64_t *d) { *d = sim_clock + n * 1000ULL; (void)unit; }
static void read_random(void *p, unsigned n) { for (unsigned i = 0; i < n; i++) ((uint8_t *)p)[i] = (uint8_t)(i * 37 + 11); }
static int PE_parse_boot_argn(const char *n, void *v, int s) { (void)n; (void)v; (void)s; return 0; }
static void loader_log_line(const char *line) { fputs(line, stdout); }
static uint32_t sim_r32(volatile uint8_t *base, uint32_t off);
static void sim_w32(volatile uint8_t *base, uint32_t off, uint32_t v);
static vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size, unsigned int flags);
static const uint8_t *redwood_image_file(const char *dir, const char *name, uint64_t *size, int *disk);
static const uint8_t *redwood_adsp_fw_file(const char *name, uint64_t *size);
static void redwood_adsp_fw_free(const uint8_t *data, uint64_t size) { (void)data; (void)size; }
'''

SIM = r'''
/* ---------------- the simulated chip ---------------- */
#define EROM_ADDR 0x18100000U
#define WRAP_OFF  0x100000U
struct simcore { uint16_t id; uint8_t rev; uint32_t base; uint32_t ioctl, resetctl; uint32_t regs[1024]; };
static struct simcore sc[8];
static unsigned nsc;
static uint32_t erom[256];
static unsigned nerom;
static uint8_t cfgspace[4096], dbispace[4096], bar0dummy[0x8000];
static uint8_t *chipmem;               /* BAR2: the chip's memory from its address 0 */
static size_t chipmem_size, mapped;
static uint32_t chipid_val, sysmem_banks_val[64], cr4_banks_val[64];
static bool arm_running, arm_halted_once;
static int ev_n;
static const uint8_t *fwimg; static uint64_t fwimg_size;
static const char *nvtext_s;
static char asked[4][40]; static int nasked;

static void ev(const char *what) { printf("EV %d %s\n", ev_n++, what); }

static struct simcore *core_at(uint32_t addr, bool *wrap, uint32_t *off)
{
	for (unsigned i = 0; i < nsc; i++) {
		if (addr >= sc[i].base && addr < sc[i].base + 0x1000) { *wrap = false; *off = addr - sc[i].base; return &sc[i]; }
		if (addr >= sc[i].base + WRAP_OFF && addr < sc[i].base + WRAP_OFF + 0x1000) {
			*wrap = true; *off = addr - sc[i].base - WRAP_OFF; return &sc[i];
		}
	}
	return NULL;
}

static uint32_t bp_r(uint32_t addr)
{
	bool w; uint32_t off; struct simcore *c;
	if (addr >= EROM_ADDR && addr < EROM_ADDR + sizeof(erom)) return erom[(addr - EROM_ADDR) / 4];
	c = core_at(addr, &w, &off);
	if (c == NULL) { printf("SIM bad backplane read %#x\n", addr); return 0xffffffffU; }
	if (w) return off == BCMA_IOCTL ? c->ioctl : off == BCMA_RESET_CTL ? c->resetctl : c->regs[off / 4];
	if (c->id == CORE_CC && off == 0) return chipid_val;
	if (c->id == CORE_CC && off == CC_EROMPTR) return EROM_ADDR;
	if (c->id == CORE_SYSMEM && off == SYSMEM_BANKINFO) return sysmem_banks_val[c->regs[SYSMEM_BANKIDX / 4] & 63];
	if (c->id == CORE_ARM_CR4 && off == ARMCR4_BANKINFO) return cr4_banks_val[c->regs[ARMCR4_BANKIDX / 4] & 63];
	return c->regs[off / 4];
}

static bool is_arm(struct simcore *c) { return c->id == CORE_ARM_CA7 || c->id == CORE_ARM_CR4; }

/*
 * What the firmware reads at start: the NVRAM's last word is its length in words with the complement above it,
 * the NVRAM (key=value strings, NUL each, then NUL padding) below it, and {count, 0xfeedc0de} with the seed below
 * that. The expected strings are the scenario text normalised by hand (comment and blanks dropped).
 */
static const char nv_expect[] = "boardrev=0x1103\0macaddr=00:90:4c:c5:12:38\0ccode=XZ\0";
static bool nvram_check(void)
{
	uint32_t top = rambase + ramsize, token = *(uint32_t *)(chipmem + top - 4), words = token & 0xffff;
	uint32_t len = words * 4, start = top - 4 - len, magic, count;
	bool ok = (token >> 16) == (~words & 0xffff) && len >= sizeof(nv_expect) - 1 && len < 4096 &&
	    memcmp(chipmem + start, nv_expect, sizeof(nv_expect) - 1) == 0;
	for (uint32_t i = sizeof(nv_expect) - 1; ok && i < len; i++) {
		ok = chipmem[start + i] == 0;
	}
	magic = *(uint32_t *)(chipmem + start - 4);
	count = *(uint32_t *)(chipmem + start - 8);
	ok = ok && magic == SEED_MAGIC && count == SEED_BYTES;
	printf("NVRAM token=%#x len=%u seed=%#x/%u nvram_ok=%d\n", token, len, magic, count, ok);
	return ok;
}

static void bp_w(uint32_t addr, uint32_t v)
{
	bool w; uint32_t off; struct simcore *c = core_at(addr, &w, &off);
	char line[96];
	if (c == NULL) { printf("SIM bad backplane write %#x\n", addr); return; }
	if (!w) { c->regs[off / 4] = v; return; }
	if (off == BCMA_RESET_CTL) {
		if ((c->resetctl & 1) != (v & 1)) { snprintf(line, sizeof(line), "reset %03x %u", c->id, v & 1); ev(line); }
		c->resetctl = v;
		return;
	}
	if (off != BCMA_IOCTL) { c->regs[off / 4] = v; return; }
	c->ioctl = v;
	if (is_arm(c) && (v & ARMCR4_CPUHALT) && !(v & BCMA_IOCTL_FGC) && c->resetctl == 0) {
		snprintf(line, sizeof(line), "arm-halted %03x", c->id); ev(line); arm_halted_once = true; arm_running = false;
	}
	if (is_arm(c) && !(v & ARMCR4_CPUHALT) && !(v & BCMA_IOCTL_FGC) && (v & BCMA_IOCTL_CLK) && c->resetctl == 0 &&
	    arm_halted_once && !arm_running) {
		arm_running = true;
		snprintf(line, sizeof(line), "arm-running %03x vector %#x", c->id, *(uint32_t *)chipmem); ev(line);
		/* the firmware: checks what it was handed, then puts the shared area's address in the RAM's last word */
		if (nvram_check()) {
			*(uint32_t *)(chipmem + rambase + ramsize - 4) = rambase + 0x1000;
		}
	}
}

static uint32_t sim_r32(volatile uint8_t *base, uint32_t off)
{
	if (base == cfgspace) return *(uint32_t *)(cfgspace + off);
	if (base == dbispace) return *(uint32_t *)(dbispace + off);
	if (base == bar0dummy) return bp_r(*(uint32_t *)(cfgspace + CFG_BAR0_WINDOW) + off);
	if (base == chipmem) return *(volatile uint32_t *)(chipmem + off);
	printf("SIM read from an unknown mapping\n"); exit(3);
}

static void sim_w32(volatile uint8_t *base, uint32_t off, uint32_t v)
{
	char line[64];
	if (base == cfgspace) {
		if (off == 0x84) { snprintf(line, sizeof(line), "cfg84 %#x", v); ev(line); }
		*(uint32_t *)(cfgspace + off) = v; return;
	}
	if (base == dbispace) { *(uint32_t *)(dbispace + off) = v; return; }
	if (base == bar0dummy) { bp_w(*(uint32_t *)(cfgspace + CFG_BAR0_WINDOW) + off, v); return; }
	if (base == chipmem) {
		if (off == 0) { snprintf(line, sizeof(line), "vector-write %#x", v); ev(line); }
		if (v == SEED_MAGIC) { snprintf(line, sizeof(line), "seed-magic %#x", off); ev(line); }
		*(volatile uint32_t *)(chipmem + off) = v; return;
	}
	printf("SIM write to an unknown mapping\n"); exit(3);
}

static vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size, unsigned int flags)
{
	(void)flags;
	if (phys == *(uint32_t *)(cfgspace + 0x10)) return (vm_offset_t)bar0dummy;
	if (size > chipmem_size) { printf("SIM map larger than BAR2\n"); return 0; }
	mprotect(chipmem, chipmem_size, PROT_NONE);
	mprotect(chipmem, size, PROT_READ | PROT_WRITE);
	mapped = size;
	printf("SIM BAR2 mapped %#zx\n", (size_t)size);
	return (vm_offset_t)chipmem;
}

static const uint8_t *redwood_image_file(const char *dir, const char *name, uint64_t *size, int *disk)
{ (void)dir; (void)name; (void)disk; *size = 0; return NULL; }

static const uint8_t *redwood_adsp_fw_file(const char *name, uint64_t *size)
{
	if (nasked < 4) snprintf(asked[nasked++], sizeof(asked[0]), "%s", name);
	if (strstr(name, "-sta.bin")) { *size = fwimg_size; return fwimg; }
	if (strstr(name, "-nvram-")) { *size = strlen(nvtext_s); return (const uint8_t *)nvtext_s; }
	*size = 0; return NULL;
}

static void add_core(uint16_t id, uint8_t rev, uint32_t base)
{
	sc[nsc].id = id; sc[nsc].rev = rev; sc[nsc].base = base; sc[nsc].resetctl = 1; nsc++;
	erom[nerom++] = 0x1u | ((uint32_t)id << 8);                          /* component A */
	erom[nerom++] = 0x1u | (1u << 19) | ((uint32_t)rev << 24);           /* component B: one slave port */
	erom[nerom++] = base | 0x5u;                                         /* address: slave, 4 KB */
	erom[nerom++] = (base + WRAP_OFF) | (2u << 6) | 0x5u;                /* address: slave wrapper */
}

static struct redwood_bcm_bus simbus;

int main(int argc, char **argv)
{
	const char *s = argc > 1 ? argv[1] : "";
	uint64_t bar2 = 0x400000;
	uint32_t sysmem_nb = 16, smar = 0, vec0 = 0;
	bool four375 = false;
	static uint8_t fwbuf[0x10000];
	int ok;

	if (!strcmp(s, "p3s-fits")) smar = 0x1c0000;
	else if (!strcmp(s, "p3s-past-bar2-smar")) { sysmem_nb = 20; smar = 0x1c0000; }
	else if (!strcmp(s, "p3s-past-bar2-nosmar")) sysmem_nb = 20;
	else if (!strcmp(s, "p3s-remap")) { sysmem_nb = 20; bar2 = 0x800000; }
	else if (!strcmp(s, "p3s-secured")) { smar = 0x1c0000; vec0 = 0xffffffffU; }
	else if (!strcmp(s, "s21-4375")) four375 = true;
	else if (!strcmp(s, "unknown-chip")) ;
	else { printf("unknown scenario\n"); return 2; }

	chipid_val = !strcmp(s, "unknown-chip") ? 0x00134377U : four375 ? 0x00124375U : 0x00134389U;
	add_core(CORE_CC, 70, 0x18000000U);
	add_core(CORE_PCIE2, 72, 0x18001000U);
	add_core(CORE_80211, 80, 0x18002000U);
	if (four375) {
		add_core(CORE_ARM_CR4, 13, 0x18003000U);
		sc[nsc - 1].regs[ARMCR4_CAP / 4] = (2u << 4) | 9u;   /* 9 + 2 banks */
		for (int i = 0; i < 11; i++) cr4_banks_val[i] = 0x0f; /* 128 KB each: 0x160000 */
	} else {
		add_core(CORE_ARM_CA7, 7, 0x18003000U);
		add_core(CORE_SYSMEM, 20, 0x18004000U);
		sc[nsc - 1].regs[SYSMEM_COREINFO / 4] = (3u << 24) | (sysmem_nb << 16);
		for (int i = 0; i < 3; i++) sysmem_banks_val[i] = 0x1f;            /* ROM banks, not counted */
		for (uint32_t i = 3; i < 3 + sysmem_nb; i++) sysmem_banks_val[i] = 0x0f;  /* 128 KB RAM banks */
	}
	erom[nerom++] = 0xf;                                                  /* EOT */

	chipmem_size = bar2;
	chipmem = mmap(NULL, chipmem_size, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	mprotect(chipmem, chipmem_size, PROT_READ | PROT_WRITE);
	*(uint32_t *)chipmem = vec0;
	mprotect(chipmem, chipmem_size, PROT_NONE);

	for (unsigned i = 0; i < sizeof(fwbuf); i += 4) *(uint32_t *)(fwbuf + i) = 0xa5000000U | i;
	*(uint32_t *)fwbuf = 0xea00002eU;
	if (smar) { *(uint32_t *)(fwbuf + RAMSIZE_OFFSET) = RAMSIZE_MAGIC; *(uint32_t *)(fwbuf + RAMSIZE_OFFSET + 4) = smar; }
	fwimg = fwbuf; fwimg_size = sizeof(fwbuf);
	nvtext_s = "# p3s\nboardrev=0x1103\nmacaddr=00:90:4c:c5:12:38\n  ccode=XZ  \n";

	simbus.cfg = cfgspace; simbus.dbi = dbispace; simbus.mem_phys = 0x20000000U; simbus.mem_size = 0xff0000U;
	simbus.bar0_size = 0x8000; simbus.bar2_size = bar2;
	bus = &simbus; cfg = cfgspace;
	ok = bars() && chip() && firmware();
	for (int i = 0; i < nasked; i++) printf("ASKED %s\n", asked[i]);
	printf("STATE rambase=%#x ramsize=%#x tcm_size=%#x ca7=%d mapped=%#zx bar0=%#x bar2=%#x\n", rambase, ramsize,
	    tcm_size, ca7, mapped, *(uint32_t *)(cfgspace + 0x10), *(uint32_t *)(cfgspace + 0x18));
	if (ok) {
		mprotect(chipmem, chipmem_size, PROT_READ);
		printf("RAM fw_match=%d\n", memcmp(chipmem + rambase, fwbuf, sizeof(fwbuf)) == 0);
	}
	printf("RESULT %s\n", ok ? "up" : "fail");
	return 0;
}
'''


def extract_fn(text, name):
    m = re.search(r"^(static [^\n]*\n)?%s\([^\n]*\)\n\{\n" % re.escape(name), text, re.M)
    if m is None:
        m = re.search(r"^static [^\n]*\b%s\([^\n]*\)\n\{\n" % re.escape(name), text, re.M)
    if m is None:
        raise SystemExit("função %s não encontrada" % name)
    end = text.index("\n}\n", m.end()) + 3
    return text[m.start():end]


def harness(driver):
    lines = driver.split("\n")
    i0 = next(i for i, l in enumerate(lines) if l.startswith("extern vm_offset_t ml_io_map_unmappable"))
    i1 = next(i for i, l in enumerate(lines) if l.startswith("static LCK_GRP_DECLARE"))
    head = "\n".join(l for l in lines[i0:i1] if not l.startswith("extern ") and not l.startswith("#include"))
    head += "\n" + "\n".join(l for l in lines[i1:] if l.startswith("#define"))
    fns = []
    for n in FUNCS:
        f = extract_fn(driver, n)
        if n in ("r32", "r16"):
            f = re.sub(r"\{\n\treturn .*;\n\}", "{\n\treturn sim_r32(base, off);\n}", f)
        if n in ("w32", "w16"):
            f = re.sub(r"\{\n\t\*\(volatile.*\n.*\n\}", "{\n\tsim_w32(base, off, value);\n}", f)
        fns.append(f)
    body = "\n".join(fns).replace('__asm__ volatile ("dsb sy" ::: "memory");', ";")
    return PRELUDE + head + "\n" + body + SIM


SCENARIOS = {
    "p3s-fits": dict(result="up", asked=["bcm4389-sta.bin", "bcm4389-nvram-semco.txt"], ramsize="0x1c0000",
                     order=["cfg84 0", "arm-halted 847", "reset 849 1", "reset 849 0", "seed-magic", "vector-write",
                            "reset 847 1", "reset 847 0", "arm-running 847 vector 0xea00002e"]),
    "p3s-past-bar2-smar": dict(result="up", log="left to the image's own RAM size", ramsize="0x1c0000"),
    "p3s-past-bar2-nosmar": dict(result="fail", log="W4 FAIL: RAM 0x200000 + 0x280000 is not within BAR2's 0x400000",
                                 absent=["arm-halted", "vector-write"]),
    "p3s-remap": dict(result="up", log="BAR2 mapped again: 0x480000 bytes", ramsize="0x280000", tcm="0x480000",
                      bars="bar0=0x20800000 bar2=0x20000000"),
    "p3s-secured": dict(result="fail", log="W4 FAIL: address 0 reads 0xffffffff", absent=["arm-running", "vector-write"]),
    "s21-4375": dict(result="up", asked=["bcm4375-sta.bin", "bcm4375-nvram-semco.txt"], ramsize="0x160000",
                     order=["arm-halted 83e", "seed-magic", "vector-write", "arm-running 83e"], absent=["cfg84"],
                     bars="bar0=0x20000000 bar2=0x20400000"),
    "unknown-chip": dict(result="fail", log="W4 FAIL: not the BCM4375 or BCM4389", absent=["arm-halted"]),
}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--driver", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    report = {"schema": "s21xnu-p3s-wifi-0150-sim/1", "checks": [], "scenarios": {}}
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        report["checks"].append({"check": name, "ok": bool(cond), "detail": str(detail)})
        print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))

    src = harness(pathlib.Path(a.driver).read_text())
    with tempfile.TemporaryDirectory() as t:
        c, exe = pathlib.Path(t, "sim.c"), pathlib.Path(t, "sim")
        c.write_text(src)
        r = subprocess.run(["cc", "-std=gnu11", "-O1", "-w", str(c), "-o", str(exe)], capture_output=True, text=True)
        check("o código do driver compila no host com o modelo", r.returncode == 0, r.stderr[:400])
        if r.returncode:
            report["result"] = "FAIL"
            return 1
        for name, want in SCENARIOS.items():
            p = subprocess.run([str(exe), name], capture_output=True, text=True)
            out = p.stdout
            report["scenarios"][name] = out.splitlines()
            check("%s: termina sem falha de memória" % name, p.returncode == 0, "rc %d" % p.returncode)
            res = re.search(r"^RESULT (\w+)$", out, re.M)
            check("%s: resultado %s" % (name, want["result"]), res and res.group(1) == want["result"],
                  res.group(1) if res else None)
            check("%s: nenhum acesso fora do modelo" % name, "SIM bad" not in out)
            evs = re.findall(r"^EV \d+ (.*)$", out, re.M)
            if "asked" in want:
                asked = re.findall(r"^ASKED (.*)$", out, re.M)
                check("%s: arquivos %s" % (name, ", ".join(want["asked"])), asked == want["asked"], asked)
            if "ramsize" in want:
                check("%s: RAM usada %s" % (name, want["ramsize"]), "ramsize=%s " % want["ramsize"] in out)
            if "tcm" in want:
                check("%s: BAR2 mapeado %s" % (name, want["tcm"]), "tcm_size=%s " % want["tcm"] in out)
            if "bars" in want:
                check("%s: BARs %s" % (name, want["bars"]), want["bars"] in out)
            if "log" in want:
                check("%s: log '%s'" % (name, want["log"][:50]), want["log"] in out)
            if "order" in want:
                pos, last = [], -1
                for w in want["order"]:
                    j = next((k for k, e in enumerate(evs) if e.startswith(w) and k > last), None)
                    pos.append(j)
                    last = j if j is not None else last
                check("%s: ordem %s" % (name, " → ".join(want["order"])), None not in pos and pos == sorted(pos),
                      evs)
            for w in want.get("absent", []):
                check("%s: sem '%s'" % (name, w), not any(e.startswith(w) for e in evs), evs)
            if want["result"] == "up":
                check("%s: firmware na RAM" % name, "fw_match=1" in out)
                check("%s: NVRAM, token e semente como o firmware lê" % name, "nvram_ok=1" in out,
                      re.findall(r"^NVRAM .*$", out, re.M))
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"])
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
