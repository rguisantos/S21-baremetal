#!/usr/bin/env python3
"""Kit do primeiro boot do shim s21xnu no SM-G998B HZC2 (sonda), num comando.

  prepare_first_boot.py --stock-dir DIR --s21xnu CLONE --out NOVO_DIR [--lab-key PEM]
                        [--cega entrada|etapas]

DIR contém boot.img e vendor_boot.img do AP HZC2, crus ou .lz4 (como vêm no
tar); os dois são conferidos contra docs/references/capture-a0-pins-hzc2.json
e qualquer outro firmware é recusado. CLONE é o s21xnu no commit fixado e
limpo. O script:

  1. compila o shim BOARD=p3s com os patches 0001 e 0002;
  2. monta a sonda com mk_sboot_bootimg.py e o rodapé AVB de laboratório
     (avb_lab.py; gera uma chave RSA4096 nova se --lab-key faltar);
  3. grava em NOVO_DIR: boot.img (64 MiB), AP_s21xnu_sonda.tar e .tar.md5
     para o Odin, s21xnu-switch.sh, ROTEIRO.md com os valores que a foto da
     sonda deve mostrar, relatorio.json e SHA256SUMS.

Com --cega, aplica também o patch 0003 (sonda cega): o shim grava marcas
nos registradores INFORM do PMU e pede reset para a recovery, e o resultado
se lê no log do S-Boot (/proc/last_kmsg na recovery), sem depender da tela.
"entrada" reinicia na primeira instrução; "etapas" marca cada etapa;
"relogio" espera 30 s pelo contador e reinicia por PSCI; "tela" lê o
TRIG_CON e o GLOBAL_CON do DECON0, desmascara o trigger por hardware e
pinta a tela de vermelho e depois de verde.

Nada é gravado no aparelho. Exige desbloqueio OEM para ser usado.
"""
import argparse
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "scripts"))
import avb_lab  # noqa: E402
import mk_sboot_bootimg as mk  # noqa: E402
import verify_p3s_profile as vp  # noqa: E402
from capture_a0_container import describe, signature_valid  # noqa: E402
from capture_a0_formats import layout  # noqa: E402

PINS = REPO / "docs" / "references" / "capture-a0-pins-hzc2.json"
PATCH2 = HERE / "0002-probe-lk-handoff-facts.patch"
PATCH3 = HERE / "0003-probe-blind-pmu-marks.patch"
BLIND = {"entrada": "1", "etapas": "2", "relogio": "3", "tela": "4"}
BLIND_STAGES = [
    ("5101", "entrou no shim (primeira instrução)"),
    ("5102", "shim_main"), ("5103", "framebuffer pintado de vermelho"),
    ("5104", "loader leu o ramdisk"), ("5105", "linhas do handoff (FDT lido)"),
    ("5106", "pausa de 2 s concluída (contador CNTPCT anda)"),
    ("5107", "MMU ligada"), ("510E", "MMU falhou"), ("5108", "antes do PSCI (hvc)"),
    ("5109", "PSCI respondeu"), ("510A", "teste do GIC concluído"), ("510F", "reset pedido no fim"),
    ("5S8X", "exceção: S = última etapa, X = slot do vetor (0 a F; 4 = sync em EL1 com SPx)"),
]
CLOCK_STAGES = [
    ("5101", "entrou no shim"), ("5102", "shim_main"),
    ("5110", "na espera de 30 s, CNTFRQ_EL0 = 0"), ("5111", "na espera de 30 s, CNTFRQ_EL0 não zero"),
    ("5112", "PSCI SYSTEM_RESET chamado: se voltou sozinho à recovery, o reset por PSCI funciona"),
    ("5113", "PSCI SYSTEM_RESET voltou sem reiniciar; reset feito pelo PMU"),
]


SCREEN_STAGES = [
    ("5101", "entrou no shim; não chegou ao DECON"),
    ("6TTG", "DECON lido: TT = TRIG_CON bits 5..0 (bit0 HW_TRIG_EN, bit4 HW_TRIG_MASK_DECON) em 11..6; "
             "G = GLOBAL_CON (bit0 modo comando, bit1 RUN, bit2 DECON_EN, bit3 DECON_EN_F, bit4 IDLE)"),
]


def blind_rows(blind):
    if blind == "tela":
        return SCREEN_STAGES
    if blind == "entrada":
        return BLIND_STAGES[:1]
    return CLOCK_STAGES if blind == "relogio" else BLIND_STAGES

SWITCH = HERE / "dualboot" / "s21xnu-switch.sh"
FIXED_TAR_TIME = 1764115200          # 2025-11-26 00:00 UTC, para tar reprodutível


class KitError(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise KitError(msg)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_stock(stock_dir, name, pins):
    """boot.img ou boot.img.lz4 conferidos contra os pins; devolve os bytes crus."""
    raw_pin, lz4_pin = pins["stock_raw"][name], pins["stock_lz4"].get(name + ".lz4")
    raw_path, lz4_path = stock_dir / name, stock_dir / (name + ".lz4")
    if raw_path.is_file():
        data = raw_path.read_bytes()
        need(len(data) == raw_pin["bytes"] and sha(data) == raw_pin["sha256"],
             "%s não é o HZC2 fixado (tamanho/SHA-256)" % name)
        return data
    need(lz4_path.is_file() and lz4_pin, "%s ausente em %s (cru ou .lz4)" % (name, stock_dir))
    packed = lz4_path.read_bytes()
    need(len(packed) == lz4_pin["bytes"] and sha(packed) == lz4_pin["sha256"],
         "%s.lz4 não é o HZC2 fixado" % name)
    from check_capture_a0_parent import lz4_frame
    data = lz4_frame(packed, raw_pin["bytes"])
    need(len(data) == raw_pin["bytes"] and sha(data) == raw_pin["sha256"], "%s descomprimido difere do pin" % name)
    return data


def odin_tar(boot, name="AP_s21xnu_sonda.tar"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        info = tarfile.TarInfo("boot.img")
        info.size, info.mtime, info.mode = len(boot), FIXED_TAR_TIME, 0o644
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        tf.addfile(info, io.BytesIO(boot))
    tar = buf.getvalue()
    md5 = hashlib.md5(tar).hexdigest()
    return tar, tar + ("%s  %s\n" % (md5, name)).encode()


def roteiro(rep, vsize):
    end = mk.INITRD_BASE + vsize + len(mk.PROBE_RAMDISK)
    return """# Primeiro boot do shim s21xnu no S21 Ultra (sonda)

Gerado por `lab/s21xnu-p3s/prepare_first_boot.py`. boot.img SHA-256
`{sha}`.

## Pré-requisitos

- SM-G998B em G998BXXSJHZC2 (bootloader rev 19), **bootloader desbloqueado**
  (apaga os dados; Knox fica 0x1 para sempre).
- TWRP para o p3s instalado, para voltar sem Odin.
- Backup do que importa no aparelho.

## Gravar a sonda

Opção A, root no Android, sem Odin:

    su
    sh s21xnu-switch.sh install boot.img
    sh s21xnu-switch.sh to-xnu

Opção B, modo download e Odin: AP = `AP_s21xnu_sonda.tar.md5`. Mantenha
o boot.img stock à mão para voltar.

## O que a foto deve mostrar (tela vermelha, ~25 s)

| Linha | Esperado |
|---|---|
| `LOADER` | `no SWEETXNU payload` |
| `ENTRY` | `el=00000001 x0=8B080000` |
| `IMAGE` | `at=` entre 80080000 e 80278000, múltiplo de 8000 |
| `INITRD` | `start=84080000 end={end:08X}` |
| `FB` | `w=000005A0 stride=00001680` |

Depois vêm o diagnóstico (MMU, PSCI, GIC) e PSCI SYSTEM_RESET após 40 s.
Tela preta, outra cor ou valores diferentes: fotografe e compare com a
tabela em docs/xnu-s21xnu-p3s.md.

## Voltar ao Android

A sonda reinicia nela mesma. No reinício, segure Volume+ e Power para o
TWRP e rode `sh /cache/s21xnu/s21xnu-switch.sh to-android`. Sem TWRP: modo
download e Odin com AP = `AP_stock_boot.tar.md5` (o boot.img stock HZC2
conferido pelos pins).
""".format(sha=rep["sha256"], end=end)


def roteiro_cego(rep, blind):
    rows = "\n".join("| `0x%s` | %s |" % (c, d) for c, d in blind_rows(blind))
    return """# Sonda cega do shim s21xnu no S21 Ultra ({blind})

Gerado por `lab/s21xnu-p3s/prepare_first_boot.py --cega {blind}`. boot.img
SHA-256 `{sha}`.

A tela não é usada. O shim grava marcas no PMU (INFORM2 = 0x51nn, INFORM3 =
0x12345604 = pedido de recovery) e reinicia por software; o S-Boot imprime
os dois no boot seguinte e, pelo pedido, entra sozinho na recovery.

## Rodar

Na recovery, com o BOOT stock e a /cache montada:

    sh s21xnu-switch.sh install boot.img
    sh /cache/s21xnu/s21xnu-switch.sh to-xnu --no-reboot
    reboot

Não toque nos botões. Esperado: em poucos segundos ({wait}) o aparelho
volta sozinho à recovery. Se ficar no logo mais de 2 minutos, Volume− e
Power até apagar; se não entrar sozinho na recovery, Volume+ e Power.

## Ler o resultado (na recovery)

    grep -a -E "show_reset_reason_rawdata|sbl_check_reboot_mode" /proc/sec_log

O log do boot que entrou na recovery é o último par de linhas (observado em
27/11: `PINFORM = 12345604` e o `inform2` da sonda). O `/proc/last_kmsg`
mostra o boot anterior.

| inform2 | significado |
|---|---|
{rows}
| `0x0` | marca nenhuma: o shim não rodou ou o S-Boot zerou o PMU |

Depois: `sh /cache/s21xnu/s21xnu-switch.sh to-android --no-reboot`.
""".format(blind=blind, sha=rep["sha256"], rows=rows,
           wait={"entrada": "logo depois do logo", "etapas": "uns 30 s",
                 "relogio": "uns 60 s se o contador for 26 MHz",
                 "tela": "uns 40 s; olhe a tela: vermelho com texto por 15 s e depois verde por 15 s"}[blind])


def prepare(stock_boot, stock_vendor, shim, lab_key_pem, out, blind=None):
    need(not out.exists(), "diretório de saída precisa ser novo: %s" % out)
    img, rep = mk.build(stock_boot, stock_vendor, shim, None)
    body_sha = rep["sha256"]
    img = avb_lab.transplant(stock_boot, img, *avb_lab.openssl_lab_key(lab_key_pem))
    need(len(img) == len(stock_boot), "tamanho da partição mudou")
    q = describe(img)
    need(layout(img)["avb"]["all_hashes_match"] and signature_valid(q), "AVB de laboratório inválido")
    rep.update(avb="lab", body_sha256=body_sha, sha256=sha(img), boot_img_size=len(img))
    vsize = mk.parse_vendor_v3(stock_vendor)["vendor_ramdisk_size"]
    tar, tar_md5 = odin_tar(img)
    stock_tar, stock_md5 = odin_tar(stock_boot, "AP_stock_boot.tar")     # volta pelo Odin
    out.mkdir(parents=True)
    files = {"boot.img": img, "AP_s21xnu_sonda.tar": tar, "AP_s21xnu_sonda.tar.md5": tar_md5,
             "AP_stock_boot.tar": stock_tar, "AP_stock_boot.tar.md5": stock_md5,
             "s21xnu-switch.sh": SWITCH.read_bytes(),
             "ROTEIRO.md": (roteiro_cego(rep, blind) if blind else roteiro(rep, vsize)).encode()}
    for name, data in files.items():
        (out / name).write_bytes(data)
    (out / "s21xnu-switch.sh").chmod(0o755)
    report = {"schema": "s21xnu-first-boot-kit/1", "bootimg": rep, "vendor_ramdisk_size": vsize,
              "cega": blind,
              "expected_initrd_end": hex(mk.INITRD_BASE + vsize + len(mk.PROBE_RAMDISK)),
              "shim_sha256": sha(shim), "files": {k: sha(v) for k, v in files.items()}}
    (out / "relatorio.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    names = sorted(files) + ["relatorio.json"]
    (out / "SHA256SUMS").write_text("".join("%s  %s\n" % (sha((out / n).read_bytes()), n) for n in names))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stock-dir", required=True)
    ap.add_argument("--s21xnu", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lab-key", help="PEM RSA4096; sem ele, gera um em OUT/lab-key.pem")
    ap.add_argument("--cega", choices=sorted(BLIND), help="sonda cega: marcas no PMU, sem tela")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out).resolve()
    try:
        pins = json.loads(PINS.read_text())
        stock_dir = pathlib.Path(a.stock_dir)
        boot = load_stock(stock_dir, "boot.img", pins)
        vendor = load_stock(stock_dir, "vendor_boot.img", pins)
        vp.pinned_clone(a.s21xnu)
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(t)
            tree = tmp / "s21xnu"
            shutil.copytree(pathlib.Path(a.s21xnu).resolve(), tree, symlinks=True,
                            ignore=shutil.ignore_patterns(".git"))
            for p in (vp.PATCH, PATCH2) + ((PATCH3,) if a.cega else ()):
                subprocess.run(["patch", "-p1", "--batch", "-s", "-i", str(p)], cwd=tree, check=True)
            env = vp.cross_env(t)
            if a.cega:
                env["SHIM_BLIND"] = BLIND[a.cega]
            shim = vp.build_shim(tree, "p3s", env)
            key = pathlib.Path(a.lab_key) if a.lab_key else tmp / "lab-key.pem"
            if not a.lab_key:
                subprocess.run(["openssl", "genrsa", "-out", str(key), "4096"], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            report = prepare(boot, vendor, shim, key, out, a.cega)
            if not a.lab_key:
                shutil.copy(key, out / "lab-key.pem")
    except (KitError, mk.ContractError, ValueError) as e:
        print("RECUSADO:", e, file=sys.stderr)
        return 2
    print("kit em", out)
    print("boot.img", report["bootimg"]["sha256"])
    if a.cega:
        print("sonda cega (%s): resultado em /proc/last_kmsg, veja ROTEIRO.md" % a.cega)
    else:
        print("INITRD end esperado na foto:", report["expected_initrd_end"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
