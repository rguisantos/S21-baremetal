#!/usr/bin/env python3
"""Confere no QEMU as marcas da sonda cega (patch 0003) sob o handoff LK modelado.

  blind_marks.py CLONE_S21XNU [--json r.json]

Aplica 0001, 0002 e 0003 ao clone fixado e compila o shim BOARD=p3s com o
PMU redirecionado para RAM (BLIND_PMU=0xBF000000), porque o QEMU virt não
tem PMU Exynos em 0x15860000. Para cada variante, carrega a sonda como o LK
faria (KASLR 0x8000), espera e lê pelo monitor os quatro registradores que a
sonda escreve:

  INFORM2 +0x808  0x51nn: última etapa (01 entrada ... 0f reset; 8s exceção)
  INFORM3 +0x80c  0x12345604: pedido de recovery (SEC_RESET_REASON_RECOVERY)
  SWRESET +0x3c00 2: reset por software (exynos-reboot.c)

e, na variante 4, o DECON0 falso (BLIND_DECON=0xBF008000, semeado com
TRIG_CON=0x11 e GLOBAL_CON=0x113 como num modo comando com trigger
mascarado): TRIG_CON tem de virar 0x01 e SHD_REG_UP_REQ ganhar o bit 31.

Também confere o patch 0004 (sonda com tela no p3s, sem 0003): logo na
entrada o TRIG_CON do DECON0 falso vira 0x01 e o SHD_REG_UP_REQ ganha o bit
31; no fim (25 s de pausa + diagnóstico + 40 s), o reset vai pelo PMU com o
pedido de recovery, sem PSCI.

SHIM_BLIND=1 tem de parar em 01 e pedir o reset logo; SHIM_BLIND=2 tem de
passar por todas as etapas até 0f; SHIM_BLIND=3 marca 11 (CNTFRQ não zero)
durante a espera de 30 s e depois reinicia por PSCI, o que encerra o QEMU. Também confere que SHIM_BLIND=0 não toca
nesses endereços. O QEMU não é o Exynos: cobre a lógica das marcas, não se o
S-Boot as preserva ou as imprime.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(LAB))
import run_handoff as rh  # noqa: E402
import mk_sboot_bootimg as mk  # noqa: E402
import verify_p3s_profile as vp  # noqa: E402
import probe_screenshot as ps  # noqa: E402
from capture_a0_formats import layout  # noqa: E402

PATCHES = [vp.PATCH, LAB / "0002-probe-lk-handoff-facts.patch", LAB / "0003-probe-blind-pmu-marks.patch"]
PATCH4 = LAB / "0004-p3s-decon-trigger-and-pmu-reset.patch"
PMU = 0xBF000000
DECON = PMU + 0x8000
SEED_TRIG, SEED_GLOB = 0x11, 0x113
KASLR = 0x8000
EXPECT = {
    "0": None,
    "1": {"inform2": 0x5101, "inform3": 0x12345604, "sysip0": 0, "swreset": 2},
    "2": {"inform2": 0x510F, "inform3": 0x12345604, "sysip0": 0, "swreset": 2},
    # no meio da espera de 30 s: CNTFRQ do QEMU é não zero; nada de reset ainda
    "3": {"inform2": 0x5111, "inform3": 0x12345604, "sysip0": 0, "swreset": 0},
    # durante o vermelho: código 0x6TTG de TRIG_CON 0x11 e GLOBAL_CON 0x113
    "4": {"inform2": 0x6000 | (SEED_TRIG & 0x3f) << 6 | 0xF, "inform3": 0x12345604, "sysip0": 0,
          "swreset": 0, "decon_trig": 0x01, "decon_shd": 1 << 31, "decon_glob": SEED_GLOB},
}
WORDS = {"1": 3, "2": 3, "3": 2, "4": 2}
WAIT = {"0": 6, "1": 4, "2": 14, "3": 4, "4": 5, "p3s": 4}


def fake_mmio():
    """PMU (0x0000-0x3fff) zerado e DECON0 falso em +0x8000 com TRIG_CON/GLOBAL_CON semeados."""
    b = bytearray(0x10000)
    struct.pack_into("<I", b, 0x8020, SEED_GLOB)
    struct.pack_into("<I", b, 0x8030, SEED_TRIG)
    return bytes(b)


def run(tmp, env, tree, blind, late=None):
    if blind == "p3s":
        e = dict(env, P3S_MMIO_CFLAGS="-DP3S_PMU=%#xUL -DP3S_DECON0=%#xUL" % (PMU, DECON))
    else:
        e = dict(env, SHIM_BLIND=blind, BLIND_PMU=hex(PMU), BLIND_DECON=hex(DECON))
    shim = vp.build_shim(tree, "p3s", e)
    vrd = rh.vendor_ramdisk(rh.HZC2_VENDOR_RD)
    boot, vboot = rh.stock_headers(vrd)
    img, _ = mk.build(boot, vboot, shim, None)
    parts = {p["name"]: p for p in layout(img)["parts"]}
    kernel = img[parts["kernel"]["start"]:parts["kernel"]["end"]]
    initrd = vrd + img[parts["ramdisk"]["start"]:parts["ramdisk"]["end"]]
    d = tmp / ("run" + blind)
    d.mkdir()
    image_pa = mk.KERNEL_BASE + KASLR
    stub = bytearray(rh.cc(env, tmp, "lk_stub" + blind, [HERE / "lk_stub.S"], None))
    struct.pack_into("<QQ", stub, 8, image_pa, mk.FDT_X0)
    # PMU falso zerado: um bloco de 16 KiB de zeros carregado em RAM
    files = {"stub.bin": (bytes(stub), rh.STUB_PA), "Image": (kernel, image_pa),
             "initrd.bin": (initrd, mk.INITRD_BASE), "pmu.bin": (fake_mmio(), PMU),
             "fdt.dtb": (rh.fdt_chosen(mk.INITRD_BASE, mk.INITRD_BASE + len(initrd)), mk.FDT_X0)}
    argv_q, qenv = rh.qemu_cmd()
    mon = d / "mon.sock"
    args = argv_q + ["-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-m", "3G", "-smp", "1",
                     "-nodefaults", "-audio", "none", "-display", "none",
                     "-monitor", "unix:%s,server,nowait" % mon, "-no-reboot"]
    for fn, (data, addr) in files.items():
        (d / fn).write_bytes(data)
        ld = "loader,file=%s,addr=%#x,force-raw=on" % (d / fn, addr)
        if fn == "stub.bin":
            ld += ",cpu-num=0"
        args += ["-device", ld]
    proc = subprocess.Popen(args, env=qenv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dump = d / "pmu.raw"
    try:
        for _ in range(100):
            if mon.exists():
                break
            time.sleep(0.1)
        time.sleep(WAIT[blind])
        ps.monitor(mon, "pmemsave %#x %d \"%s\"" % (PMU, 0x10000, dump))
        if late:                   # segunda leitura, depois do reset pedido no fim
            for _ in range(100):
                if dump.exists() and dump.stat().st_size == 0x10000:
                    break
                time.sleep(0.1)
            early = dump.read_bytes()
            dump.unlink()
            time.sleep(late)
            ps.monitor(mon, "pmemsave %#x %d \"%s\"" % (PMU, 0x10000, dump))
        for _ in range(100):
            if dump.exists() and dump.stat().st_size == 0x10000:
                break
            time.sleep(0.1)
        exited = None
        if blind == "3":           # PSCI SYSTEM_RESET com -no-reboot encerra o QEMU
            try:
                proc.wait(timeout=60)
                exited = True
            except subprocess.TimeoutExpired:
                exited = False
    finally:
        proc.kill()
        proc.wait()
    raw = dump.read_bytes()
    rd = lambda o: struct.unpack_from("<I", raw, o)[0]  # noqa: E731
    if late:
        rde = lambda o: struct.unpack_from("<I", early, o)[0]  # noqa: E731
        return hashlib.sha256(shim).hexdigest(), {
            "early_trig": rde(0x8030), "early_shd": rde(0x8050), "early_swreset": rde(0x3c00),
            "late_inform3": rd(0x80c), "late_swreset": rd(0x3c00), "late_inform2": rd(0x808),
            "nonzero_words": sum(1 for o in range(0, 0x4000, 4) if rd(o))}
    return hashlib.sha256(shim).hexdigest(), {"inform2": rd(0x808), "inform3": rd(0x80c),
                                              "sysip0": rd(0x810), "swreset": rd(0x3c00),
                                              "decon_glob": rd(0x8020), "decon_trig": rd(0x8030),
                                              "decon_shd": rd(0x8050),
                                              "nonzero_words": sum(1 for o in range(0, 0x4000, 4) if rd(o)),
                                              "psci_reset_exited_qemu": exited}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("clone")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    src = pathlib.Path(a.clone).resolve()
    head = vp.pinned_clone(src)
    report = {"schema": "s21xnu-blind-marks-qemu/1", "s21xnu_commit": head, "pmu_redirect": hex(PMU),
              "patches_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in PATCHES},
              "runs": {}, "checks": []}
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        report["checks"].append({"check": name, "ok": bool(cond), "detail": str(detail)})
        print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))

    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        env = vp.cross_env(t)
        tree = tmp / "s21xnu"
        shutil.copytree(src, tree, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        for p in PATCHES:
            subprocess.run(["patch", "-p1", "--batch", "-s", "-i", str(p)], cwd=tree, check=True)
        for blind in ("0", "1", "2", "3", "4"):
            shim_sha, regs = run(tmp, env, tree, blind)
            report["runs"][blind] = {"shim_sha256": shim_sha, **{k: (hex(v) if isinstance(v, int) and not isinstance(v, bool) else v) for k, v in regs.items()}}
            want = EXPECT[blind]
            if want is None:
                check("SHIM_BLIND=0 não escreve no PMU nem no DECON", regs["nonzero_words"] == 0
                      and regs["decon_trig"] == SEED_TRIG and regs["decon_shd"] == 0, regs)
                continue
            if blind in ("1", "2", "3"):
                check("SHIM_BLIND=%s não toca no DECON" % blind,
                      regs["decon_trig"] == SEED_TRIG and regs["decon_shd"] == 0)
            for k, v in want.items():
                check("SHIM_BLIND=%s %s" % (blind, k), regs[k] == v, "%#x" % regs[k])
            n = WORDS[blind]
            check("SHIM_BLIND=%s só %d registradores" % (blind, n), regs["nonzero_words"] == n,
                  regs["nonzero_words"])
            if blind == "3":
                check("SHIM_BLIND=3 reset por PSCI encerra o QEMU", regs["psci_reset_exited_qemu"] is True)
        tree4 = tmp / "s21xnu-p3s"
        shutil.copytree(src, tree4, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        for p in PATCHES[:2] + [PATCH4]:
            subprocess.run(["patch", "-p1", "--batch", "-s", "-i", str(p)], cwd=tree4, check=True)
        shim_sha, regs = run(tmp, env, tree4, "p3s", late=75)
        report["runs"]["p3s-0004"] = {"shim_sha256": shim_sha, **{k: hex(v) for k, v in regs.items()}}
        check("0004: trigger desmascarado na entrada (TRIG_CON 0x11 -> 0x01)", regs["early_trig"] == 0x01,
              "%#x" % regs["early_trig"])
        check("0004: SHD_REG_UP_REQ bit 31 na entrada", regs["early_shd"] == 1 << 31, "%#x" % regs["early_shd"])
        check("0004: sem reset antes do fim", regs["early_swreset"] == 0)
        check("0004: reset pelo PMU no fim", regs["late_swreset"] == 2, "%#x" % regs["late_swreset"])
        check("0004: pedido de recovery no fim", regs["late_inform3"] == 0x12345604, "%#x" % regs["late_inform3"])
        check("0004: INFORM2 intacto e só dois registradores", regs["late_inform2"] == 0 and regs["nonzero_words"] == 2,
              regs["nonzero_words"])
    report["patches_sha256"][PATCH4.name] = hashlib.sha256(PATCH4.read_bytes()).hexdigest()
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"])
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
