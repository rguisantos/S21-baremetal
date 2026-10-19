#!/bin/bash
# build_kit_day2.sh — monta e empacota o kit Dia 2 (reproduzível)
# uso: bash /home/z/my-project/scripts/build_kit_day2.sh
set -euo pipefail

ROOT=/home/z/my-project
KIT=$ROOT/download/exynos-baremetal-kit-DAY2
F2=$ROOT/download/exynos-baremetal-qemu-fase2
SCR=$ROOT/scripts
MB=$SCR/magiskboot

# 1. regenera o pipeline sintético com o payload Fase 2 (PIC) — roundtrip
bash "$MB/demo_repack.sh" "$F2/payload_fase2.bin" > "$SCR/demo_f2.log" 2>&1
grep -a 'ROUNDTRIP OK' "$SCR/demo_f2.log" \
        || { echo "FALHA no round-trip do repack F2 — kit abortado"; exit 1; }

# 2. estrutura
rm -rf "$KIT"
mkdir -p "$KIT"/{code,payloads,experiments,analysis,magiskboot,toolchain}

cp "$F2"/start.S "$F2"/main.c "$F2"/link.ld "$F2"/Makefile "$KIT/code/"
cp "$F2/payload_fase2.bin" "$KIT/payloads/"

cp "$SCR"/test_delta_sweep.sh "$SCR"/test_delta_sweep_fase2.sh "$KIT/experiments/"
cp "$SCR"/test_delta_*.log "$SCR"/test_delta_*.exc "$SCR"/test_delta_sweep.txt \
        "$KIT/experiments/" 2>/dev/null || true
cp "$SCR"/test_delta2_*.log "$SCR"/test_delta2_sweep.txt \
        "$KIT/experiments/" 2>/dev/null || true
cp "$SCR/test_delta_d_unmap.exc" "$SCR/experiments_dataabort.exc" 2>/dev/null || true

cp "$SCR/abl_triage.py" "$KIT/analysis/"
cp "$SCR/kit-assets/ABL_EXTRACTION.md" "$KIT/analysis/"

cp "$MB/magiskboot" "$MB/make_boot_v3.py" "$MB/demo_repack.sh" \
   "$MB/verify_repack.py" "$MB/boot.img" "$MB/custom_boot.img" \
   "$KIT/magiskboot/"
cp "$SCR/kit-assets/repack_day2.sh" "$KIT/magiskboot/repack_day2.sh"
[ -f "$MB/magisk.apk" ] && cp "$MB/magisk.apk" "$KIT/magiskboot/"

cp "$SCR/kit-assets/README-DAY2.md" "$KIT/README.md"
cp "$SCR/kit-assets/SETUP.md" "$KIT/toolchain/SETUP.md"
cp "$SCR/toolchain/fetch_qemu.sh" "$KIT/toolchain/"
cp "$ROOT/worklog.md" "$KIT/worklog.md"

chmod +x "$KIT/magiskboot/magiskboot" "$KIT/magiskboot/"*.sh \
         "$KIT/experiments/"*.sh "$KIT/analysis/abl_triage.py"

# 3. BOOT_CUSTOM_F2.tar oficial — gerado PELO repack blindado (smoke real)
cd "$KIT/magiskboot"
if ! ./repack_day2.sh --force boot.img ../payloads/payload_fase2.bin \
        > "$SCR/repack_f2_kit.log" 2>&1; then
        echo "FALHA: repack_day2.sh não completou no kit — log:"
        cat "$SCR/repack_f2_kit.log"
        exit 1
fi
grep -a 'md5 verificado' "$SCR/repack_f2_kit.log" \
        || { echo "FALHA: verificação do md5 não apareceu — log:"; \
             cat "$SCR/repack_f2_kit.log"; exit 1; }

# 4. empacotamento
cd "$ROOT/download"
rm -f exynos-baremetal-kit-DAY2.tar.gz exynos-baremetal-kit-DAY2.tar.gz.sha256
tar czf exynos-baremetal-kit-DAY2.tar.gz exynos-baremetal-kit-DAY2
sha256sum exynos-baremetal-kit-DAY2.tar.gz > exynos-baremetal-kit-DAY2.tar.gz.sha256

echo "=== kit Dia 2 gerado ==="
du -sh exynos-baremetal-kit-DAY2.tar.gz
cat exynos-baremetal-kit-DAY2.tar.gz.sha256
echo "=== árvore ==="
find exynos-baremetal-kit-DAY2 -type f | sort
