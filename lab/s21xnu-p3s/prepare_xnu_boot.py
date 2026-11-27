#!/usr/bin/env python3
"""Kit do segundo boot no SM-G998B HZC2: o XNU do fork pelo S-Boot (depois da foto da sonda).

  prepare_xnu_boot.py --stock-dir DIR --s21xnu CLONE --kernel kernel.development.sweet --out NOVO_DIR
                      [--filefrag ff.txt] [--sweetwifi N] [--cpus N] [--lab-key PEM]

DIR: boot.img e vendor_boot.img do AP HZC2 (conferidos pelos pins, como na
sonda). CLONE: s21xnu no commit fixado e limpo; a série do fork
(lab/s21xnu-p3s/fork/0001–0007) é aplicada numa cópia. KERNEL: o
kernel.development.sweet do artefato `xnu-kernel` do fork; precisa conter
as marcas dos patches 0146, 0148, 0149 e 0150 (o 0150 com o BAR2 primeiro).

O script compila o shim BOARD=p3s (com as linhas da sonda), gera o ADT
(`mkadt.py --board=p3s --highmem`, com o mapa UFS se houver --filefrag),
o payload SWEETXNU (`mkpayload.py`) e o boot.img com o rodapé AVB de
laboratório; confere o payload contra o hand-off do LK
(mk_sboot_bootimg.check_payload_memory); e grava boot.img,
AP_s21xnu_xnu.tar(.md5), s21xnu-switch.sh, ROTEIRO-XNU.md, relatorio.json e
SHA256SUMS.

Linha de comando do kernel: verbosa, framebuffer escalado (sweetfb_scale=1),
toque no painel 1440x3200. Com --filefrag (saída de `filefrag -v` do
iosroot.img em /data), raiz pelo mapa UFS com sobreposição em RAM
(ufsov=1: nada é gravado no UFS). Sem ele, o kernel sobe até procurar a
raiz. Nada é gravado no aparelho.
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mk_sboot_bootimg as mk  # noqa: E402
import prepare_first_boot as kit  # noqa: E402
import verify_p3s_profile as vp  # noqa: E402

FORK_SERIES = sorted((HERE / "fork").glob("000[1-7]-*.patch"))
KERNEL_MARKS = {
    "0146 toque": b"touch_panel_w",
    "0148 escala": b"sweetfb_scale",
    "0149 BCM4389": b"14e4:4441 p3s",
    "0150 CA7": b"SYSMEM rev %u coreinfo",
    "0150 BAR2 primeiro": b"BAR2 (%llu KB) first at",
}
MACHO_MAGIC = b"\xcf\xfa\xed\xfe"
# kernels do fork identificados pelo SHA-256 que o workflow imprime no log (série 0008); 0151 não deixa marca
# no binário, então só esta tabela diz se o kernel tem a correção do HID
KERNELS = HERE.parent.parent / "docs" / "references" / "s21xnu-fork-kernels.json"
UFS_MAP_MAX = 8192                      # "SWEET UFS: extent cap 8192"
BASE_ARGS = "-v debug=0xc serial=3 keepsyms=1 sweetfb_scale=1 touch_panel_w=1440 touch_panel_h=3200"
ROOT_ARGS = "rd=ufsroot0 ufsroot=userdata ufsov=1 ufsovmb=1024 rootrw=1"


def identify_kernel(data, table=KERNELS):
    known = json.loads(pathlib.Path(table).read_text())["kernels"]
    k = known.get(kit.sha(data))
    if k is None:
        return {"known": False, "note": "kernel fora da tabela: marcas até 0150 conferidas; a correção HID 0151 "
                                         "não é identificável no binário"}
    return dict(known=True, **k)


def check_kernel(data):
    kit.need(data[:4] == MACHO_MAGIC, "kernel: não é Mach-O arm64 (magic %s)" % data[:4].hex())
    missing = [k for k, m in KERNEL_MARKS.items() if m not in data]
    kit.need(not missing, "kernel sem os patches do p3s: falta %s" % ", ".join(missing))


def cmdline(cpus, sweetwifi, with_root):
    kit.need(1 <= cpus <= 8, "--cpus fora de 1..8")
    kit.need(0 <= sweetwifi <= 4, "--sweetwifi fora de 0..4")
    kit.need(not (sweetwifi >= 4 and not with_root),
             "--sweetwifi=4 precisa da raiz (--filefrag): o firmware vem de /usr/local/etc/wifi")
    args = "%s cpus=%d" % (BASE_ARGS, cpus)
    if with_root:
        args += " " + ROOT_ARGS
    if sweetwifi:
        args += " sweetwifi=%d" % sweetwifi
    return args


def roteiro(rep):
    root = rep["root"]
    lines = [
        "# Segundo boot: XNU no SM-G998B (p3s)",
        "",
        "Usar só depois da foto da sonda conferida (ROTEIRO.md do primeiro kit).",
        "",
        "boot.img: `%s`" % rep["bootimg"]["sha256"],
        "kernel: `%s` (%d bytes)" % (rep["kernel_sha256"], rep["kernel_bytes"]),
        "build: %s" % (("fork `%s`, run %s, patches até %s" % (rep["kernel_build"]["fork_commit"],
                                                                rep["kernel_build"]["run_id"],
                                                                rep["kernel_build"]["patches_up_to"]))
                       if rep["kernel_build"].get("known") else "**%s**" % rep["kernel_build"]["note"]),
        "",
        "Linha de comando do kernel:",
        "",
        "    %s" % rep["cmdline"],
        "",
        "## Gravar",
        "",
        "Opção A, root no Android ou shell do TWRP (o backup stock feito na sonda",
        "é mantido; só a imagem do shim é trocada). Se a BOOT ainda tem a sonda,",
        "o primeiro comando a troca pelo stock; com o stock na BOOT, só avisa:",
        "",
        "    sh /cache/s21xnu/s21xnu-switch.sh to-android --no-reboot",
        "    sh s21xnu-switch.sh install boot.img",
        "    sh s21xnu-switch.sh to-xnu",
        "",
        "Opção B, Odin: AP = `AP_s21xnu_xnu.tar.md5`.",
        "",
        "Volta: Volume+ e Power para o TWRP e `sh /cache/s21xnu/s21xnu-switch.sh",
        "to-android`, ou o boot.img stock pelo Odin.",
        "",
        "## O que deve aparecer",
        "",
        "1. Tela do loader com as linhas ENTRY/IMAGE/INITRD/FB, agora com o",
        "   payload SWEETXNU achado em vez do motivo de recusa.",
        "2. Log verboso do XNU em tela cheia (1440x3118 com borda de 41 linhas).",
    ]
    if root:
        lines += [
            "3. Raiz pelo mapa UFS (%d extents) com sobreposição em RAM: nada é" % rep["ufs_extents"],
            "   gravado no UFS; tudo some no reboot.",
        ]
    else:
        lines += ["3. Sem --filefrag: o kernel para procurando a raiz. Esse já é o marco."]
    if rep["sweetwifi"]:
        lines += [
            "4. Linhas `wifi:` com sweetwifi=%d: `endpoint 14e4:4441`, `W2 PASS` (tamanhos" % rep["sweetwifi"],
            "   dos BARs), `W2b PASS … chip 4389` (nível 3) e, no nível 4, `W4 PASS: the",
            "   firmware is up` ou o `W4 FAIL` com o motivo.",
        ]
    lines += [
        "",
        "Fotografar cada tela que parar. Nunca usar `ufsrw` (grava no UFS).",
        "",
    ]
    return "\n".join(lines)


def prepare(stock_boot, stock_vendor, shim, payload, kernel, lab_key_pem, out, extra):
    kit.need(not out.exists(), "diretório de saída precisa ser novo: %s" % out)
    img, rep = mk.build(stock_boot, stock_vendor, shim, payload)
    body_sha = rep["sha256"]
    img = kit.avb_lab.transplant(stock_boot, img, *kit.avb_lab.openssl_lab_key(lab_key_pem))
    kit.need(len(img) == len(stock_boot), "tamanho da partição mudou")
    q = kit.describe(img)
    kit.need(kit.layout(img)["avb"]["all_hashes_match"] and kit.signature_valid(q), "AVB de laboratório inválido")
    rep.update(avb="lab", body_sha256=body_sha, sha256=kit.sha(img), boot_img_size=len(img))
    report = {"schema": "s21xnu-xnu-boot-kit/1", "bootimg": rep, "kernel_sha256": kit.sha(kernel),
              "kernel_bytes": len(kernel), "payload_sha256": kit.sha(payload), "shim_sha256": kit.sha(shim)}
    report.update(extra)
    tar, tar_md5 = kit.odin_tar(img, "AP_s21xnu_xnu.tar")
    out.mkdir(parents=True)
    files = {"boot.img": img, "AP_s21xnu_xnu.tar": tar, "AP_s21xnu_xnu.tar.md5": tar_md5,
             "s21xnu-switch.sh": kit.SWITCH.read_bytes(), "ROTEIRO-XNU.md": roteiro(report).encode()}
    for name, data in files.items():
        (out / name).write_bytes(data)
    (out / "s21xnu-switch.sh").chmod(0o755)
    report["files"] = {k: kit.sha(v) for k, v in files.items()}
    (out / "relatorio.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    names = sorted(files) + ["relatorio.json"]
    (out / "SHA256SUMS").write_text("".join("%s  %s\n" % (kit.sha((out / n).read_bytes()), n) for n in names))
    return report


def build_inputs(s21xnu, kernel_path, filefrag, cpus, sweetwifi, tmp):
    """Shim, ADT e payload a partir do clone fixado + série do fork (usa o toolchain de verify_p3s_profile)."""
    vp.pinned_clone(s21xnu)
    tree = tmp / "s21xnu"
    shutil.copytree(pathlib.Path(s21xnu).resolve(), tree, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    kit.need(len(FORK_SERIES) == 7, "série do fork incompleta: %d arquivos" % len(FORK_SERIES))
    for p in FORK_SERIES:
        subprocess.run(["patch", "-p1", "--batch", "-s", "-i", str(p)], cwd=tree, check=True)
    shim = vp.build_shim(tree, "p3s", vp.cross_env(str(tmp)))
    kernel = pathlib.Path(kernel_path).read_bytes()
    check_kernel(kernel)
    env = dict(os.environ)
    extra = {"root": bool(filefrag), "ufs_extents": 0, "kernel_build": identify_kernel(kernel)}
    if filefrag:
        ufsmap = tmp / "ufsmap.bin"
        subprocess.run([sys.executable, "tools/mkufsmap.py", str(pathlib.Path(filefrag).resolve()), str(ufsmap)],
                       cwd=tree, check=True, stdout=subprocess.DEVNULL)
        n = ufsmap.stat().st_size // 12
        kit.need(0 < n <= UFS_MAP_MAX, "mapa UFS com %d extents (o kernel aceita até %d)" % (n, UFS_MAP_MAX))
        extra["ufs_extents"] = n
        env["UFSMAP"] = str(ufsmap)
    args = cmdline(cpus, sweetwifi, bool(filefrag))
    adt, payload = tmp / "adt.bin", tmp / "payload.bin"
    subprocess.run([sys.executable, "tools/mkadt.py", str(adt), "--board=p3s", "--highmem"], cwd=tree, env=env,
                   check=True, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, "tools/mkpayload.py", str(pathlib.Path(kernel_path).resolve()), str(adt),
                    str(payload), "--cmdline", args], cwd=tree, check=True, stdout=subprocess.DEVNULL)
    extra.update(cmdline=args, sweetwifi=sweetwifi, cpus=cpus, adt_sha256=kit.sha(adt.read_bytes()))
    return shim, payload.read_bytes(), kernel, extra


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stock-dir", required=True)
    ap.add_argument("--s21xnu", required=True)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--filefrag")
    ap.add_argument("--sweetwifi", type=int, default=0)
    ap.add_argument("--cpus", type=int, default=1)
    ap.add_argument("--lab-key", help="PEM RSA4096 (o mesmo da sonda); sem ele, gera um em OUT/lab-key.pem")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out).resolve()
    try:
        pins = json.loads(kit.PINS.read_text())
        stock_dir = pathlib.Path(a.stock_dir)
        boot = kit.load_stock(stock_dir, "boot.img", pins)
        vendor = kit.load_stock(stock_dir, "vendor_boot.img", pins)
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(t)
            shim, payload, kernel, extra = build_inputs(a.s21xnu, a.kernel, a.filefrag, a.cpus, a.sweetwifi, tmp)
            key = pathlib.Path(a.lab_key) if a.lab_key else tmp / "lab-key.pem"
            if not a.lab_key:
                subprocess.run(["openssl", "genrsa", "-out", str(key), "4096"], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            report = prepare(boot, vendor, shim, payload, kernel, key, out, extra)
            if not a.lab_key:
                shutil.copy(key, out / "lab-key.pem")
    except (kit.KitError, mk.ContractError, ValueError) as e:
        print("RECUSADO:", e, file=sys.stderr)
        return 2
    print("kit em", out)
    print("boot.img", report["bootimg"]["sha256"])
    print("cmdline", report["cmdline"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
