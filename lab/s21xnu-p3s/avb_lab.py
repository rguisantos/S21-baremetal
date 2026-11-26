#!/usr/bin/env python3
"""Rodapé AVB com chave de laboratório para um boot.img de tamanho novo.

Reaproveita o vbmeta do boot.img stock HZC2 (mesmo perfil canônico que
scripts/capture_a0_container.py aceita: v1.0, SHA256_RSA4096, um descritor
de hash `boot`) e o transplanta para um corpo novo, como `avbtool
add_hash_footer` faria: vbmeta logo após o corpo alinhado a 4 KiB, rodapé
AVBf no fim da partição, image_size e digest do descritor recalculados,
chave pública trocada pela de laboratório e assinatura refeita.

Isto é o mesmo formato que o port MonsterROM grava no HZC2 desbloqueado
(boot assinado com chave de teste). **Uma assinatura de laboratório nunca é
confiança do aparelho**; o efeito no LK desbloqueado não foi observado aqui.
A extensão opaca Samsung do stock (entre o corpo e o fim do hash) não é
copiada: o corpo novo não tem extensão.
"""
import hashlib
import pathlib
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
from capture_a0_container import describe, signature_valid, template  # noqa: E402
from capture_a0_formats import align, layout, require  # noqa: E402
from inspect_lk_embedded_key import inspect_avb_rsa_key  # noqa: E402


def transplant(stock, body, public_key, signer):
    """Devolve a partição (mesmo tamanho do stock) com `body` e vbmeta de laboratório."""
    p = template(stock)
    require(type(body) is bytes and 0 < len(body), "corpo vazio")
    require(layout(body)["kind"] == "boot_v3", "corpo não é boot.img v3")
    require(type(public_key) is bytes and len(public_key) == 1032, "chave de laboratório: tamanho/tipo")
    require(inspect_avb_rsa_key(public_key)["key_num_bits"] == 4096, "chave de laboratório deve ser RSA4096")
    require(public_key != p["key"], "chave de laboratório igual à chave do stock")
    meta = bytearray(p["meta"])
    offset = align(len(body), 4096)
    total = len(stock)
    require(offset + len(meta) <= total - 64, "corpo + vbmeta não cabem na partição")
    desc = p["descriptor"]
    struct.pack_into(">Q", meta, desc + 16, len(body))                 # image_size
    h = hashlib.sha256(p["salt"])
    h.update(body)
    meta[p["digest_offset"]:p["digest_offset"] + 32] = h.digest()
    meta[p["key_offset"]:p["key_offset"] + 1032] = public_key
    signing_input = bytes(meta[:256]) + bytes(meta[256 + p["auth"]:])
    signature = signer(signing_input)
    require(type(signature) is bytes and len(signature) == 512, "assinatura: tamanho/tipo")
    meta[256:288] = hashlib.sha256(signing_input).digest()
    meta[288:800] = signature
    out = bytearray(total)
    out[:len(body)] = body
    out[offset:offset + len(meta)] = meta
    out[-64:] = stock[-64:]
    struct.pack_into(">QQQ", out, total - 64 + 12, len(body), offset, len(meta))
    out = bytes(out)
    q = describe(out)
    require(q["inventory"]["avb"]["all_hashes_match"] and signature_valid(q),
            "verificação do hash/assinatura de laboratório falhou")
    require(q["extent"] == len(body) and q["key"] == public_key, "extensão/chave inesperadas")
    return out


def openssl_lab_key(pem):
    """(chave pública AVB de 1032 bytes, assinador) a partir de um PEM RSA4096 via openssl."""
    openssl = shutil.which("openssl")
    require(openssl is not None, "openssl ausente")
    mod = subprocess.check_output([openssl, "rsa", "-in", str(pem), "-modulus", "-noout"],
                                  stderr=subprocess.DEVNULL).decode().strip()
    n = int(mod.split("=", 1)[1], 16)
    require(n.bit_length() == 4096, "PEM não é RSA4096")
    blob = struct.pack(">II", 4096, (-pow(n, -1, 2 ** 32)) % 2 ** 32)
    blob += n.to_bytes(512, "big") + pow(2, 8192, n).to_bytes(512, "big")

    def signer(data):
        return subprocess.check_output([openssl, "dgst", "-sha256", "-sign", str(pem)], input=data)

    return blob, signer
