#!/usr/bin/env python3
"""Captura a tela da sonda do shim (BOARD=p3s) sob o handoff LK modelado no QEMU.

  probe_screenshot.py CLONE_S21XNU --png sonda.png [--json r.json]

Exige o clone do s21xnu no commit fixado e sem alterações rastreadas (como
verify_p3s_profile.py), aplica 0001 (perfil p3s) e 0002 (linhas
ENTRY/IMAGE/INITRD/FB), monta o boot.img de sonda com mk_sboot_bootimg.py e o carrega como
o LK faria (run_handoff.py), com KASLR 0x8000. Durante a pausa de ~25 s em
que o shim mantém o resultado do loader na tela, copia o framebuffer
0xfa000000 (1440x3200 BGRA) pelo monitor do QEMU e grava um PNG do topo da
tela (480 linhas, metade da resolução).

Confere também, sem OCR, que a tela saiu do vermelho de fundo nas linhas de
texto esperadas. O QEMU virt não é o Exynos: mostra o que o shim desenharia
com o handoff modelado, não o que o painel do S21 Ultra exibirá.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zlib

HERE = pathlib.Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(LAB))
import run_handoff as rh  # noqa: E402
import mk_sboot_bootimg as mk  # noqa: E402
import verify_p3s_profile as vp  # noqa: E402
from capture_a0_formats import layout  # noqa: E402

PATCH2 = LAB / "0002-probe-lk-handoff-facts.patch"
PATCH4 = LAB / "0004-p3s-decon-trigger-and-pmu-reset.patch"   # como no kit; no QEMU o DECON é um buraco
FB, W, H, STRIDE = 0xFA000000, 1440, 3200, 5760
KASLR = 0x8000


def png(path, rgb_rows, w, h):
    raw = b"".join(b"\0" + row for row in rgb_rows)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    pathlib.Path(path).write_bytes(data)


def monitor(sock_path, cmd, timeout=10):
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(timeout)
    s.connect(str(sock_path))
    buf = b""
    while not buf.rstrip().endswith(b"(qemu)"):
        buf += s.recv(4096)
    s.sendall(cmd.encode() + b"\n")
    buf = b""
    while not buf.rstrip().endswith(b"(qemu)"):
        buf += s.recv(4096)
    s.close()
    return buf.decode(errors="replace")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("clone")
    ap.add_argument("--png", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    src = pathlib.Path(a.clone).resolve()
    head = vp.pinned_clone(src)          # commit fixado e árvore limpa, como os demais verificadores
    report = {"schema": "s21xnu-probe-screenshot/1", "s21xnu_commit": head,
              "patches_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (vp.PATCH, PATCH2, PATCH4)},
              "checks": []}
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
        for p in (vp.PATCH, PATCH2, PATCH4):
            subprocess.run(["patch", "-p1", "--batch", "-s", "-i", str(p)], cwd=tree, check=True)
        shim = vp.build_shim(tree, "p3s", env)
        vrd = rh.vendor_ramdisk(rh.HZC2_VENDOR_RD)
        boot, vboot = rh.stock_headers(vrd)
        img, rep = mk.build(boot, vboot, shim, None)
        parts = {p["name"]: p for p in layout(img)["parts"]}
        kernel = img[parts["kernel"]["start"]:parts["kernel"]["end"]]
        ramdisk = img[parts["ramdisk"]["start"]:parts["ramdisk"]["end"]]
        initrd = vrd + ramdisk
        report["bootimg_sha256"] = rep["sha256"]
        report["shim_sha256"] = hashlib.sha256(shim).hexdigest()
        check("boot.img de sonda montado", rep["mode"] == "probe")

        d = tmp / "run"
        d.mkdir()
        image_pa = mk.KERNEL_BASE + KASLR
        stub = bytearray(rh.cc(env, tmp, "lk_stub", [HERE / "lk_stub.S"], None))
        struct.pack_into("<QQ", stub, 8, image_pa, mk.FDT_X0)
        files = {"stub.bin": (bytes(stub), rh.STUB_PA), "Image": (kernel, image_pa),
                 "initrd.bin": (initrd, mk.INITRD_BASE),
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
        raw = d / "fb.raw"
        try:
            for _ in range(100):
                if mon.exists():
                    break
                time.sleep(0.1)
            time.sleep(4)          # sonda já desenhou e está na pausa de ~25 s
            report["monitor"] = monitor(mon, "pmemsave %#x %d \"%s\"" % (FB, STRIDE * H, raw))[-300:]
            for _ in range(100):
                if raw.exists() and raw.stat().st_size == STRIDE * H:
                    break
                time.sleep(0.1)
        finally:
            proc.kill()
            proc.wait()
        fb = raw.read_bytes()
        check("framebuffer copiado", len(fb) == STRIDE * H, len(fb))
        if len(fb) != STRIDE * H:
            return 1
        # fundo: vermelho do shim; contar linhas com pixels diferentes do fundo
        bg = fb[0:4]
        text_rows = [y for y in range(H) if fb[y * STRIDE:(y + 1) * STRIDE] != bg * W]
        bands, prev = [], -10
        for y in text_rows:
            if y != prev + 1:
                bands.append([y, y])
            bands[-1][1] = y
            prev = y
        report["background_bgra"] = bg.hex()
        report["text_bands"] = bands
        check("fundo vermelho (BGRA 0000ff..)", bg[2] > 0x80 and bg[0] < 0x40 and bg[1] < 0x40, bg.hex())
        # SHIM, INITRD (do loader), LOADER, ENTRY, IMAGE, INITRD, FB = 7 linhas
        check("sete linhas de texto desenhadas", len(bands) == 7, len(bands))
        check("texto só no topo (sonda parada na pausa do loader)", bands and bands[-1][1] < 480, bands[-1:])
        scale, crop = 2, 480                     # topo da tela, metade da resolução
        rows = []
        for y in range(0, crop, scale):
            line = fb[y * STRIDE:(y + 1) * STRIDE]
            rows.append(b"".join(line[x * 4 + 2:x * 4 + 3] + line[x * 4 + 1:x * 4 + 2] + line[x * 4:x * 4 + 1]
                                 for x in range(0, W, scale)))
        png(a.png, rows, W // scale, crop // scale)
        report["png"] = {"path": str(a.png), "scale": scale, "crop_rows": crop}
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"])
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
