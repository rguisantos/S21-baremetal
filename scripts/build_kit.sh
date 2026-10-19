#!/bin/bash
# build_kit.sh — monta e empacota o kit Dia 1 (reproduzível após qualquer mudança)
# Uso: bash /home/z/my-project/scripts/build_kit.sh
set -euo pipefail

ROOT=/home/z/my-project
KIT=$ROOT/download/exynos-baremetal-kit-DAY1
CODE=$ROOT/download/exynos-baremetal-qemu
SCR=$ROOT/scripts
MB=$SCR/magiskboot

# 1. regenera o pipeline sintético com o payload do ladder-r1 (header incluso)
bash "$MB/demo_repack.sh" "$CODE/payload_80000000.bin" > "$SCR/demo_r1.log" 2>&1
grep -a 'ROUNDTRIP OK' "$SCR/demo_r1.log" \
        || { echo "FALHA no round-trip do repack — kit abortado"; exit 1; }

# 2. estrutura do kit
rm -rf "$KIT"
mkdir -p "$KIT"/{code,payloads,qemu,magiskboot,toolchain}

cp "$CODE/start.S" "$CODE/link.ld" "$CODE/main.c" "$CODE/Makefile" "$CODE/check_payload_base.sh" "$KIT/code/"
cp "$CODE"/payload.bin "$CODE"/payload_*.bin "$KIT/payloads/"

cp "$SCR"/run_qemu.sh "$SCR"/test_header_qemu.sh "$KIT/qemu/"
cp "$SCR"/test_header_*.log "$KIT/qemu/"

cp "$MB/magiskboot" "$MB/make_boot_v3.py" "$MB/demo_repack.sh" \
   "$MB/verify_repack.py" "$MB/boot.img" "$MB/custom_boot.img" \
   "$MB/BOOT_CUSTOM.tar" "$KIT/magiskboot/"

# autorais do kit (fonte permanente em scripts/kit-assets/)
cp "$SCR/kit-assets/README.md"        "$KIT/README.md"
cp "$SCR/kit-assets/repack_day1.sh"   "$KIT/magiskboot/repack_day1.sh"
cp "$SCR/kit-assets/SETUP.md"         "$KIT/toolchain/SETUP.md"
[ -f "$MB/magisk.apk" ] && cp "$MB/magisk.apk" "$KIT/magiskboot/"

cp "$SCR/toolchain/fetch_qemu.sh" "$KIT/toolchain/"
cp "$ROOT/worklog.md" "$KIT/worklog.md"

chmod +x "$KIT/magiskboot/magiskboot" "$KIT/magiskboot/"*.sh "$KIT/qemu/"*.sh

# 3. empacotamento
cd "$ROOT/download"
tar czf exynos-baremetal-kit-DAY1.tar.gz exynos-baremetal-kit-DAY1
sha256sum exynos-baremetal-kit-DAY1.tar.gz > exynos-baremetal-kit-DAY1.tar.gz.sha256

echo "=== kit gerado ==="
du -sh exynos-baremetal-kit-DAY1.tar.gz
cat exynos-baremetal-kit-DAY1.tar.gz.sha256
echo "=== arvore ==="
find exynos-baremetal-kit-DAY1 -type f | sort
