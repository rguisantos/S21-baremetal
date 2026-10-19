#!/bin/bash
# repack_day2.sh — pipeline magiskboot BLINDADO (evolução do repack_day1.sh)
#
# uso:   ./repack_day2.sh <boot_stock.img> [payload.bin] [--dry-run] [--force]
#        payload default: payloads/payload_fase2.bin (Fase 2 PIC — roda em
#        qualquer base e reporta delta; ver worklog R6)
# saída: BOOT_CUSTOM_F2.tar e BOOT_CUSTOM_F2.tar.md5 no diretório ATUAL
#        (Odin slot AP, Auto Reboot DESMARCADO)
#
# BLINDAGEM vs repack_day1.sh (falha humana é o maior risco do flash):
#   1. sanity do INPUT: boot stock precisa de magic ANDROID!; payload
#      precisa do magic "ARM\x64" em 0x38 e cabe no kernel original.
#   2. --dry-run: valida tudo e imprime o plano SEM escrever artefatos.
#   3. recusa sobrescrever BOOT_CUSTOM_F2.* existente sem --force.
#   4. verificação TRIPLO: kernel do repack == payload (byte a byte),
#      tamanho do repack <= boot stock (partição tem tamanho fixo),
#      md5 do .tar.md5 re-calculado e conferido após gerar.
#   5. sha256 do payload impresso — anote para conferir no dia do flash.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
CALLDIR=$(pwd)
BOOT=""
PAY=""
DRY=0
FORCE=0
for a in "$@"; do
        case "$a" in
        --dry-run) DRY=1 ;;
        --force)   FORCE=1 ;;
        *)  if [ -z "$BOOT" ]; then BOOT=$a
            elif [ -z "$PAY" ]; then PAY=$a
            else echo "ERRO: argumento demais: $a"; exit 2; fi ;;
        esac
done
BOOT=${BOOT:?uso: repack_day2.sh <boot_stock.img> [payload.bin] [--dry-run] [--force]}
PAY=${PAY:-$HERE/../payloads/payload_fase2.bin}
MB=$HERE/magiskboot

# caminhos ABSOLUTOS: o pipeline roda dentro de mktemp -d (um caminho
# relativo sobreviveria até o cd e morreria no cp do kernel)
BOOT=$(readlink -f "$BOOT" || echo "$BOOT")
PAY=$(readlink -f "$PAY" || echo "$PAY")

fail () { echo "ERRO: $*"; echo "    (nada foi gravado — abortado antes de qualquer mutação)"; exit 1; }

# ---------- 1. sanity do input ----------
[ -f "$BOOT" ] || fail "boot stock não encontrado: $BOOT"
[ -f "$PAY" ]  || fail "payload não encontrado: $PAY"
od -A n -t x1 -N 8 "$BOOT" | grep -q '41 4e 44 52 4f 49 44 21' \
        || fail "magic ANDROID! ausente no boot stock — arquivo correto? (é a imagem da partição boot do AP)"
SZ_PAY=$(stat -c %s "$PAY")
[ "$SZ_PAY" -ge 64 ] || fail "payload menor que o header de 64 B"
od -A x -t x1z -v -j 0x38 -N 4 "$PAY" | grep -q '41 52 4d 64' \
        || fail "magic ARM\x64 ausente em 0x38 do payload — sem ele o ABL pode rejeitar"
[ $DRY -eq 1 ] && OUT="--dry-run" || OUT=""
echo "== sanity =="
echo "  boot stock : $BOOT ($(stat -c %s "$BOOT") B, magic ANDROID! OK)"
echo "  payload    : $PAY ($SZ_PAY B, magic ARM\\x64 em 0x38 OK)"
sha256sum "$PAY" | sed 's/^/  sha256    : /'

if [ $DRY -eq 1 ]; then
        echo "== DRY-RUN: plano (nada será gravado) =="
        echo "  1. magiskboot unpack $BOOT (detecta compressão stock)"
        echo "  2. kernel <- $PAY (com header arm64)"
        echo "  3. magiskboot repack -> custom_boot.img (mesma compressão)"
        echo "  4. verificar: kernel == payload byte a byte; tamanho <= stock"
        echo "  5. gerar $CALLDIR/BOOT_CUSTOM_F2.tar + .tar.md5 p/ Odin (AP)"
        exit 0
fi

for f in "$CALLDIR/BOOT_CUSTOM_F2.tar" "$CALLDIR/BOOT_CUSTOM_F2.tar.md5"; do
        if [ -e "$f" ] && [ $FORCE -eq 0 ]; then
                fail "$f já existe — use --force para sobrescrever (ou confira se é o flash de ontem)"
        fi
done

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp "$BOOT" "$WORK/boot.img"
cd "$WORK"

echo "== 1/5 unpack (detecção automática da compressão stock) =="
"$MB" unpack boot.img
[ -f kernel ] || fail "unpack não produziu 'kernel' — boot.img legível?"
SZ_K=$(stat -c %s kernel)
echo "  kernel stock: $SZ_K B"
if [ "$SZ_PAY" -gt "$SZ_K" ]; then
        echo "  AVISO: payload ($SZ_PAY B) maior que o kernel stock ($SZ_K B)"
        echo "         o repack comprimirá — confira o tamanho final no passo 4"
fi

echo "== 2/5 kernel <- payload =="
cp "$PAY" kernel

echo "== 3/5 repack (mesma compressão do boot stock) =="
"$MB" repack boot.img custom_boot.img
[ -f custom_boot.img ] || fail "repack não produziu custom_boot.img"

echo "== 4/5 verificação tripla =="
cp custom_boot.img verify.img
"$MB" unpack verify.img
cmp -s kernel "$PAY" \
        || fail "kernel divergiu do payload — NÃO FLASHEAR"
echo "  [OK] kernel do repack == payload byte a byte"
SZ_BOOT=$(stat -c %s boot.img)
SZ_CUST=$(stat -c %s custom_boot.img)
[ "$SZ_CUST" -le "$SZ_BOOT" ] \
        && echo "  [OK] repack $SZ_CUST B <= stock $SZ_BOOT B" \
        || fail "repack ($SZ_CUST B) maior que boot stock ($SZ_BOOT B) — não cabe na partição"

echo "== 5/5 tar ustar p/ Odin (slot AP) =="
tar -H ustar -C "$WORK" -c custom_boot.img > "$CALLDIR/BOOT_CUSTOM_F2.tar"
cp "$CALLDIR/BOOT_CUSTOM_F2.tar" "$CALLDIR/BOOT_CUSTOM_F2.tar.md5"
MD5=$(md5sum "$CALLDIR/BOOT_CUSTOM_F2.tar" | cut -d' ' -f1)
echo "$MD5" >> "$CALLDIR/BOOT_CUSTOM_F2.tar.md5"
# .tar.md5 = tar binário + md5 appendado — ler só os hex dos últimos bytes
MD5B=$(tail -c 64 "$CALLDIR/BOOT_CUSTOM_F2.tar.md5" | tr -cd '0-9a-f' | tail -c 32)
[ "$MD5" = "$MD5B" ] || fail "md5 do .tar.md5 divergiu ao re-ler — NÃO FLASHEAR"
echo "  [OK] md5 verificado: $MD5"

echo
echo "pronto para o Odin (slot AP, Auto Reboot OFF):"
echo "  $CALLDIR/BOOT_CUSTOM_F2.tar"
echo "  $CALLDIR/BOOT_CUSTOM_F2.tar.md5"
echo "lembretes: EFS/nvdata/omr/persistent já copiados antes; nunca .pit custom;"
echo "se não bootar, força Download Mode com Vol- + Power 7s (jig 523k se preciso)"
