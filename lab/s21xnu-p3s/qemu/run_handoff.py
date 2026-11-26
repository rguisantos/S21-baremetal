#!/usr/bin/env python3
"""Executa no QEMU o shim s21xnu (BOARD=p3s) sob o handoff LK HZC2 modelado.

  run_handoff.py CLONE_S21XNU [--json saida.json]

Passos: aplica o perfil p3s ao clone fixado, compila o shim e um kernel
falso (fake_xnu), empacota um payload SWEETXNU, monta o boot.img com
mk_sboot_bootimg.py e então reproduz o que o LK faz: Image em
0x80080000+KASLR, ramdisk vendor (12.017.257 bytes, tamanho HZC2) seguido
do ramdisk de boot em 0x84080000, FDT com /chosen initrd em células u32 em
0x8b080000 e salto em EL1 com x0=FDT. O kernel falso imprime boot_args na
PL011. Um controle negativo usa o payload sem padding de alinhamento.

QEMU virt não é o Exynos: o teste cobre o loader do shim e o contrato de
memória modelado, não DECON, uH, PSCI ou o FDT real do aparelho.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
LAB = HERE.parent
REPO = LAB.parent.parent
sys.path.insert(0, str(LAB))
sys.path.insert(0, str(REPO / "scripts"))
import mk_sboot_bootimg as mk  # noqa: E402
import verify_p3s_profile as vp  # noqa: E402
from capture_a0_formats import layout  # noqa: E402

VIRT_BASE = 0xFFFFFE0007004000
PHYS_BASE, MEM_SIZE = 0xA0000000, 0x10000000
ADT = b"FAKEADT!" + bytes(range(56))
CMDLINE = b"s21xnu-p3s-handoff debug=0x8"
HZC2_VENDOR_RD = 12017257
HZC2_CMDLINE = b"androidboot.selinux=permissive loop.max_part=7"
KASLR_CASES = (0, 0x8000, 0x1F8000)
STUB_PA = 0x80000000


def qemu_cmd():
    """(argv, env). O QEMU de tools/root precisa dos próprios módulos: sem
    QEMU_MODULE_DIR ele carrega os do QEMU do host e falha (audio-alsa)."""
    root = REPO / "tools" / "root"
    q = root / "usr" / "bin" / "qemu-system-aarch64"
    env = dict(os.environ)
    if q.exists():
        lib = root / "usr" / "lib" / "x86_64-linux-gnu"
        env["QEMU_MODULE_DIR"] = str(lib / "qemu")
        return [str(lib / "ld-linux-x86-64.so.2"), "--library-path", "%s:%s" % (lib, root / "usr" / "lib"),
                str(q), "-L", str(root / "usr" / "share" / "qemu")], env
    if shutil.which("qemu-system-aarch64"):
        return ["qemu-system-aarch64"], env
    raise SystemExit("qemu-system-aarch64 ausente")


def cc(env, tmp, out, sources, ld):
    objs = []
    for s in sources:
        o = tmp / (s.stem + s.suffix.replace(".", "_") + ".o")
        subprocess.run(["aarch64-linux-gnu-gcc", "-O2", "-ffreestanding", "-nostdlib", "-fno-pic",
                        "-mgeneral-regs-only", "-mstrict-align", "-fno-stack-protector", "-Wall",
                        "-Werror", "-c", str(s), "-o", str(o)], env=env, check=True)
        objs.append(o)
    rel = subprocess.run(["aarch64-linux-gnu-readelf", "-r"] + [str(o) for o in objs],
                         env=env, capture_output=True, text=True, check=True).stdout
    if "ABS64" in rel:
        raise SystemExit("relocação absoluta em %s" % out)
    elf = tmp / (out + ".elf")
    link = ["aarch64-linux-gnu-gcc", "-nostdlib", "-static", "-Wl,--build-id=none", "-Wl,-N",
            "-Wl,--no-warn-rwx-segments"]
    link += ["-T", str(ld)] if ld else ["-Wl,-Ttext=0"]
    subprocess.run(link + [str(o) for o in objs] + ["-o", str(elf)], env=env, check=True)
    binf = tmp / (out + ".bin")
    subprocess.run(["aarch64-linux-gnu-objcopy", "-O", "binary", str(elf), str(binf)], env=env, check=True)
    return binf.read_bytes()


def make_payload(code):
    vmsize = (len(code) + 0x3FFF) & ~0x3FFF
    data_off = 0x1000
    blob = bytearray(data_off) + code
    adt_off = (len(blob) + 7) & ~7
    blob += b"\0" * (adt_off - len(blob)) + ADT
    blob[:8] = mk.PAYLOAD_MAGIC
    struct.pack_into("<II", blob, 8, 1, 1)
    struct.pack_into("<7Q", blob, 0x10, VIRT_BASE, VIRT_BASE, adt_off, len(ADT),
                     VIRT_BASE + vmsize, PHYS_BASE, MEM_SIZE)
    blob[0x48:0x48 + len(CMDLINE)] = CMDLINE
    struct.pack_into("<4Q", blob, mk.PAYLOAD_HDR, VIRT_BASE, vmsize, data_off, len(code))
    return bytes(blob)


def vendor_ramdisk(n):
    out, h = bytearray(), b"s21-vendor-ramdisk"
    while len(out) < n:
        h = hashlib.sha256(h).digest()
        out += h
    out = bytes(out[:n])
    assert mk.PAYLOAD_MAGIC[:4] not in out
    return out


def stock_headers(vrd):
    hdr = bytearray(mk.BOOT_V3_HEADER)
    hdr[:8] = b"ANDROID!"
    struct.pack_into("<4I", hdr, 8, 4096, 4096, 0x16000000, mk.BOOT_V3_HEADER)
    struct.pack_into("<I", hdr, 40, 3)
    hdr[44:44 + len(HZC2_CMDLINE)] = HZC2_CMDLINE
    boot = bytes(hdr) + b"\0" * (4096 - len(hdr)) + b"K" * 4096 + b"R" * 4096
    v = bytearray(mk.VENDOR_V3_HEADER)
    v[:8] = b"VNDRBOOT"
    struct.pack_into("<5I", v, 8, 3, 4096, 0x80008000, 0x84000000, len(vrd))
    struct.pack_into("<II", v, 2096, mk.VENDOR_V3_HEADER, 0)
    vb = bytes(v) + b"\0" * (4096 - len(v)) + vrd
    return boot, vb + b"\0" * (-len(vb) % 4096)


def fdt_chosen(start, end):
    """FDT mínimo: /chosen com initrd em células de 32 bits, como o LK grava."""
    strings, offs, st = bytearray(), {}, bytearray()

    def so(k):
        if k not in offs:
            offs[k] = len(strings)
            strings.extend(k.encode() + b"\0")
        return offs[k]

    def node(name):
        n = name.encode() + b"\0"
        st.extend(struct.pack(">I", 1) + n + b"\0" * (-len(n) % 4))

    def prop(k, v):
        st.extend(struct.pack(">III", 3, len(v), so(k)) + v + b"\0" * (-len(v) % 4))

    node("")
    prop("#address-cells", struct.pack(">I", 2))
    prop("#size-cells", struct.pack(">I", 1))
    prop("model", b"s21xnu-handoff-model\0")
    node("chosen")
    prop("linux,initrd-start", struct.pack(">I", start))
    prop("linux,initrd-end", struct.pack(">I", end))
    st.extend(struct.pack(">II", 2, 2) + struct.pack(">I", 9))
    off_st = 40 + 16
    off_str = off_st + len(st)
    total = off_str + len(strings)
    hdr = struct.pack(">10I", 0xD00DFEED, total, off_st, off_str, 40, 17, 16, 0, len(strings), len(st))
    return hdr + b"\0" * 16 + bytes(st) + bytes(strings)


def run_case(qemu, tmp, name, kernel, initrd, kaslr, secs=90):
    d = tmp / name
    d.mkdir()
    image_pa = mk.KERNEL_BASE + kaslr
    stub = bytearray(STUB)
    struct.pack_into("<QQ", stub, 8, image_pa, mk.FDT_X0)
    files = {"stub.bin": (bytes(stub), STUB_PA), "Image": (kernel, image_pa),
             "initrd.bin": (initrd, mk.INITRD_BASE),
             "fdt.dtb": (fdt_chosen(mk.INITRD_BASE, mk.INITRD_BASE + len(initrd)), mk.FDT_X0)}
    argv, env = qemu
    args = argv + ["-M", "virt,gic-version=3", "-cpu", "cortex-a76", "-m", "3G", "-smp", "1",
                   "-nodefaults", "-audio", "none", "-display", "none", "-monitor", "none",
                   "-serial", "file:%s" % (d / "serial.txt"), "-no-reboot"]
    for fn, (data, addr) in files.items():
        (d / fn).write_bytes(data)
        loader = "loader,file=%s,addr=%#x,force-raw=on" % (d / fn, addr)
        if fn == "stub.bin":
            loader += ",cpu-num=0"
        args += ["-device", loader]
    serial = d / "serial.txt"
    errf = open(d / "qemu-stderr.txt", "wb")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errf, env=env)
    deadline = time.monotonic() + secs
    try:
        while time.monotonic() < deadline and proc.poll() is None:
            if serial.exists() and "FAKEXNU-END" in serial.read_text(errors="replace"):
                break
            time.sleep(0.2)
    finally:
        proc.kill()
        proc.wait()
        errf.close()
    err = (d / "qemu-stderr.txt").read_text(errors="replace").strip()
    out = serial.read_text(errors="replace") if serial.exists() else ""
    if "FAKEXNU-END" not in out and err:
        out += "\n[qemu stderr] " + err[-400:]
    return out


def parse(serial):
    m = re.search(r"FAKEXNU(.*?)\nFAKEXNU-END", serial, re.S)
    if not m:
        return None
    vals = dict((k, int(v, 16)) for k, v in re.findall(r" (\w+)=0x([0-9a-f]{16})", m.group(1)))
    cm = re.search(r" cmd=(.*)$", m.group(1))
    vals["cmd"] = cm.group(1) if cm else ""
    return vals


STUB = b""


def main(argv=None):
    global STUB
    ap = argparse.ArgumentParser()
    ap.add_argument("clone")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    src = pathlib.Path(a.clone).resolve()
    head = vp.pinned_clone(src)
    report = {"schema": "s21xnu-sboot-handoff/1", "s21xnu_commit": head, "cases": [], "checks": []}
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
        subprocess.run(["patch", "-p1", "--batch", "-s", "-i", str(vp.PATCH)], cwd=tree, check=True)
        shim = vp.build_shim(tree, "p3s", env)
        STUB = cc(env, tmp, "lk_stub", [HERE / "lk_stub.S"], None)
        fake = cc(env, tmp, "fake_xnu", [HERE / "fake_xnu.S", HERE / "fake_xnu.c"], HERE / "fake_xnu.ld")
        payload = make_payload(fake)
        vrd = vendor_ramdisk(HZC2_VENDOR_RD)
        boot, vboot = stock_headers(vrd)
        img, rep = mk.build(boot, vboot, shim, payload)
        report["bootimg"] = {k: rep[k] for k in ("initrd", "ramdisk_pad", "payload_pa", "sha256",
                                                 "boot_img_size")}
        report["inputs_sha256"] = {"shim": hashlib.sha256(shim).hexdigest(),
                                   "fake_xnu": hashlib.sha256(fake).hexdigest(),
                                   "payload": hashlib.sha256(payload).hexdigest()}
        check("boot.img montado; pad para alinhar a 8", rep["ramdisk_pad"] == 7, rep["ramdisk_pad"])
        # Extrai kernel e ramdisk do boot.img como o LK (lk-v3-layout.md).
        parts = {p["name"]: p for p in layout(img)["parts"]}
        kernel = img[parts["kernel"]["start"]:parts["kernel"]["end"]]
        ramdisk = img[parts["ramdisk"]["start"]:parts["ramdisk"]["end"]]
        check("kernel extraído = shim", kernel == shim)
        initrd = vrd + ramdisk
        qemu = qemu_cmd()
        expect = {"el": 1, "rev": 2, "ver": 2, "virt": VIRT_BASE, "phys": PHYS_BASE, "mem": MEM_SIZE,
                  "fb": 0xFA000000, "disp": 1, "stride": 5760, "w": 1440, "h": 3200, "depth": 32,
                  "dtlen": len(ADT), "adt0": struct.unpack("<Q", ADT[:8])[0], "memact": MEM_SIZE}
        for k in KASLR_CASES:
            t0 = time.monotonic()
            serial = run_case(qemu, tmp, "kaslr-%x" % k, kernel, initrd, k)
            case_secs = time.monotonic() - t0
            v = parse(serial)
            case = {"kaslr": hex(k), "fake_xnu": v}
            report["cases"].append(case)
            check("KASLR %#x: kernel falso recebeu o controle" % k, v is not None,
                  "%.1fs" % case_secs if v else (serial[-400:] or "serial vazia após %.0fs" % case_secs))
            if v is None:
                continue
            for key, want in expect.items():
                check("KASLR %#x: %s" % (k, key), v.get(key) == want, hex(v.get(key, -1)))
            check("KASLR %#x: cmdline" % k, v["cmd"] == CMDLINE.decode(), v["cmd"])
            check("KASLR %#x: boot_args dentro da janela e após o kernel" % k,
                  PHYS_BASE < v["ba"] < PHYS_BASE + MEM_SIZE and v["ba"] < v["top"] <= PHYS_BASE + MEM_SIZE,
                  hex(v["ba"]))
        # Controle negativo: o mesmo payload sem o padding cai em endereço não alinhado a 8.
        bad_initrd = vrd + payload
        serial = run_case(qemu, tmp, "sem-padding", shim, bad_initrd, 0, secs=30)
        check("controle sem padding: kernel falso não executa", parse(serial) is None,
              "%#x %% 8 = %d" % (mk.INITRD_BASE + len(vrd), (mk.INITRD_BASE + len(vrd)) % 8))
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"])
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
