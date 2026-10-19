#!/bin/bash
# repack_day1.sh — pipeline magiskboot do Dia 1 com o boot.img STOCK do aparelho.
#
# uso:   ./repack_day1.sh <boot_stock.img> [payload.bin]
#        (payload default: payloads/payload_80000000.bin — tentativa 1 do ladder)
# saída: BOOT_CUSTOM.tar e BOOT_CUSTOM.tar.md5 no diretório ATUAL
#        (carregar no slot AP do Odin, Auto Reboot DESMARCADO)
#
# O ciclo é o validado em round-trip no ambiente controlado:
#   unpack (detecta a compressão original) → troca do kernel pelo payload
#   (com header de Image arm64 "ARM\x64") → repack (magiskboot v30 re-lê a
#   imagem original e re-comprime NO MESMO formato) → verificação byte a byte
#   → tar ustar + variante .tar.md5 (checksum que o Odin valida).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
CALLDIR=$(pwd)
BOOT=${1:?uso: repack_day1.sh <boot_stock.img> [payload.bin]}
PAY=${2:-$HERE/../payloads/payload_80000000.bin}
MB=$HERE/magiskboot

[ -f "$BOOT" ] || { echo "ERRO: boot stock nao encontrado: $BOOT"; exit 1; }
[ -f "$PAY" ]  || { echo "ERRO: payload nao encontrado: $PAY"; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp "$BOOT" "$WORK/boot.img"
cd "$WORK"

echo "== 1/5 magiskboot unpack (deteccao automatica da compressao stock) =="
"$MB" unpack boot.img
ls -la kernel 2>/dev/null

echo "== 2/5 troca do kernel pelo payload (header arm64 Image incluido) =="
cp "$PAY" kernel
od -A x -t x1z -v -j 0x38 -N 4 kernel | grep -q '41 52 4d 64' \
        && echo "magic ARMd em 0x38: OK" \
        || echo "AVISO: magic ARMd ausente — payload sem header?"

echo "== 3/5 magiskboot repack (mesma compressao do boot stock) =="
"$MB" repack boot.img custom_boot.img

echo "== 4/5 verificacao de integridade (unpack do repack) =="
cp custom_boot.img verify.img
"$MB" unpack verify.img
cmp -s kernel "$PAY" \
        && echo "ROUNDTRIP OK: kernel do repack == payload byte a byte" \
        || { echo "FALHA: kernel divergiu — NAO FLACAR"; exit 1; }

echo "== 5/5 tar ustar p/ Odin (slot AP) =="
tar -H ustar -C "$WORK" -c custom_boot.img > "$CALLDIR/BOOT_CUSTOM.tar"
cp "$CALLDIR/BOOT_CUSTOM.tar" "$CALLDIR/BOOT_CUSTOM.tar.md5"
md5sum "$CALLDIR/BOOT_CUSTOM.tar" | cut -d' ' -f1 >> "$CALLDIR/BOOT_CUSTOM.tar.md5"

echo
echo "pronto para o Odin (slot AP, Auto Reboot OFF):"
echo "  $CALLDIR/BOOT_CUSTOM.tar"
echo "  $CALLDIR/BOOT_CUSTOM.tar.md5"
