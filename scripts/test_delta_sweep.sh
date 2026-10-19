#!/bin/bash
# test_delta_sweep.sh — mapa empírico da "zona de morte" por deslocamento
#
# SIMULA O RISCO ABL SEM HARDWARE:
#   O QEMU (com magic "ARM\x64") carrega o payload SEMPRE em C=0x40200000
#   (RAMbase+2MB, armadilha 8). Variando o BOOT_BASE do link B, o payload
#   roda com delta d = C - B arbitrário — exatamente o cenário "ABL carregou
#   o kernel deslocado do ladder".
#
# Geometria (payload Fase 1, 2744 B = 0xAB8):
#   arquivo: [0x000 header+stext+pool][0x0a0 código C][0x840 rodata][fim 0xAB8]
#   clear da BSS zera 16 B em B+0xAC0. A imagem carregada ocupa [C, C+0xAB8).
#   → se d ∈ [9, 0xAC0]:  B+0xAC0 cai DENTRO da imagem → o clear APAGA
#     bytes do próprio payload (offsets 0xAC0-d .. 0xAD0-d do arquivo):
#       rodata  → strings truncadas na serial
#       .text   → instrução vira 0x00000000 (UDF) → hang
#       header/stext → nem o banner sai
#   → se d > 0xAC0 (ou d ≤ 0): clear zera RAM fora da imagem → boot limpo,
#     current_pc denuncia o deslocamento real.
#   → se B não é RAM (unmapped): str do clear → DATA ABORT → silêncio
#     (assinatura esperada no aparelho quando o ladder erra a base).
#
# Saída: scripts/test_delta_*.log (+ .exc com exceções via -d int) e tabela.
set -u
DIR=/home/z/my-project/download/exynos-baremetal-qemu
LOGS=/home/z/my-project/scripts
QEMU=/home/z/my-project/scripts/toolchain/qemu-root/usr/bin/qemu-system-aarch64
export LD_LIBRARY_PATH=/home/z/my-project/scripts/toolchain/qemu-root/usr/lib/x86_64-linux-gnu
C=0x40200000
cd "$DIR"

run_bg () {  # $1=RAM  $2=tag
        $QEMU -M virt -cpu cortex-a53 -smp 4 -m "$1" -nographic -nic none \
              -kernel payload.bin \
              -d int,guest_errors -D "$LOGS/test_delta_$2.exc" \
              > "$LOGS/test_delta_$2.log" 2>&1 &
        QPID=$!
        sleep 4
        kill -9 "$QPID" 2>/dev/null
        wait "$QPID" 2>/dev/null
}

scenario () {  # $1=tag  $2=BOOT_BASE  $3=RAM
        echo "" >> "$LOGS/test_delta_sweep.txt"
        echo "### $1 (BOOT_BASE=$2 RAM=$3)" >> "$LOGS/test_delta_sweep.txt"
        make -C "$DIR" BOOT_BASE="$2" >/dev/null 2>&1
        run_bg "$3" "$1"
        grep -a -E 'Exynos|rodando em|EL de entrada|x0 =|DTB Magic|memory@ reg|bss_probe|nao parece' \
                "$LOGS/test_delta_$1.log" | head -8 >> "$LOGS/test_delta_sweep.txt"
        ABORT=$(grep -ac 'Data Abort\|Synchronous' "$LOGS/test_delta_$1.exc" 2>/dev/null || true)
        echo "  [exceptions: ${ABORT:-0}]" >> "$LOGS/test_delta_sweep.txt"
}

rm -f "$LOGS"/test_delta_*.log "$LOGS"/test_delta_*.exc "$LOGS/test_delta_sweep.txt"
echo "== delta sweep Fase 1 — carga QEMU fixa em $C ==" > "$LOGS/test_delta_sweep.txt"

# --- zona limpa: fora de [9, 0xAC0] — boot completo previsto ---
scenario d_neg10000 0x40210000 128M   # d = -0x10000 (link acima da carga)
scenario d_neg1000  0x40201000 128M   # d = -0x1000
scenario d_zero     0x40200000 128M   # d = 0    (baseline)
# --- zona de morte: d ∈ [9, 0xAC0] — clear apaga a própria imagem ---
scenario d_p40      0x401fffc0 128M   # d = +0x40   apaga offsets 0xa80-0xa90 (rodata final)
scenario d_p300     0x401ffd00 128M   # d = +0x300  apaga 0x7c0-0x7d0 (.text do main)
scenario d_p600     0x401ffa00 128M   # d = +0x600  apaga 0x4c0-0x4d0 (.text)
scenario d_p800     0x401ff800 128M   # d = +0x800  apaga 0x2c0-0x2d0 (.text)
scenario d_p9c0     0x401ff640 128M   # d = +0x9c0  apaga 0x100-0x110 (.text cedo)
scenario d_pa80     0x401ff580 128M   # d = +0xa80  apaga 0x40-0x50  (STEXT)
scenario d_pac0     0x401ff540 128M   # d = +0xac0  apaga 0x00-0x10  (HEADER + code0)
# --- fora da zona: clear cai em RAM além/antes da imagem — limpo previsto ---
scenario d_p1000    0x401ff000 128M   # d = +0x1000 (logo acima da zona)
scenario d_p200000  0x40000000 128M   # d = +0x200000 (= test-2g)
# --- base linkada FORA da RAM: clear em unmapped → DATA ABORT ---
scenario d_unmap    0x60000000 128M   # B=0x60000000 não é RAM no virt 128M

cat "$LOGS/test_delta_sweep.txt"
echo ""
echo "=== logs: $LOGS/test_delta_*.log | exceções: .exc ==="
