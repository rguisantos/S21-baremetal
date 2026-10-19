#!/bin/bash
# test_delta_sweep_fase2.sh v2 — prova de conceito do PIC (Fase 2)
#
# LIÇÃO da v1 + armadilha 12: o ADRP+ADD do small model relocaliza apenas em
# múltiplos de 4096 (page-aligned). O delta SUB-PÁGINA corrompe acessos a
# rodata (sintoma: canários SK + strings/digits lixo). Isso NÃO é um buraco
# do PIC para o mundo real: o header do payload declara flags bit3 =
# placement 2MB-aligned — loaders conformes (QEMU incluso) carregam em
# endereços múltiplos de página, e o delta real do ABL pertence a essa
# classe. O sweep v2 testa:
#
#   A) deltas múltiplos de página (universo real) — TODOS 100% limpos:
#      banner, delta reportado, FDT, bss_probe=0.
#   B) delta sub-página (limite conhecido, documentado): SK + strings
#      corrompidas — catalogado, não falha de design.
#   C) RAM suja: dirt.bin AGORA posicionado em C+0xD78 (logo após a imagem
#      de 0xD78 B, cobrindo a BSS runtime em C+0xD80) — o radar deve ler
#      0xAA..AA no "bss pre-clear" e 0 no "bss_probe pos-clear" (o clear
#      PIC limpa a BSS REAL, não a linkada).
set -u
DIR=/home/z/my-project/download/exynos-baremetal-qemu-fase2
LOGS=/home/z/my-project/scripts
QEMU=/home/z/my-project/scripts/toolchain/qemu-root/usr/bin/qemu-system-aarch64
export LD_LIBRARY_PATH=/home/z/my-project/scripts/toolchain/qemu-root/usr/lib/x86_64-linux-gnu
C=0x40200000
SZ=0x$(stat -c %x "$DIR/payload.bin" >/dev/null 2>&1; stat -c %s "$DIR/payload.bin")
cd "$DIR"

# dirt: cobre [C+0xD78, C+0x1D78) — a BSS runtime (C+0xD80..C+0xD90) suja
# de 0xAA, SEM tocar na imagem (termina em C+0xD77). A stack runtime é
# NOLOAD e o main só usa o topo — o dirt não interfere.
python3 -c 'open("dirt.bin","wb").write(b"\xAA"*4096)'

run_bg () {  # $1=RAM  $2=tag  $3=extras
        $QEMU -M virt -cpu cortex-a53 -smp 4 -m "$1" -nographic -nic none \
              -kernel payload.bin $3 \
              > "$LOGS/test_delta2_$2.log" 2>&1 &
        QPID=$!
        sleep 4
        kill -9 "$QPID" 2>/dev/null
        wait "$QPID" 2>/dev/null
}

scenario () {  # $1=tag  $2=BOOT_BASE  $3=RAM  $4=extras-loader
        echo "" >> "$LOGS/test_delta2_sweep.txt"
        echo "### $1 (BOOT_BASE=$2 RAM=$3)" >> "$LOGS/test_delta2_sweep.txt"
        make -C "$DIR" BOOT_BASE="$2" >/dev/null 2>&1
        run_bg "$3" "$1" "$4"
        grep -a -E "Exynos|rodando em|delta carga|sp herdado|x0 =|bss pre|bss_probe|DTB Magic|memory@ reg" \
                "$LOGS/test_delta2_$1.log" | head -10 >> "$LOGS/test_delta2_sweep.txt"
        CAN=$(head -c 4 "$LOGS/test_delta2_$1.log" | tr -cd 'SK' | head -c 4)
        echo "  canarios: [${CAN:-nenhum}]" >> "$LOGS/test_delta2_sweep.txt"
}

rm -f "$LOGS"/test_delta2_*.log "$LOGS/test_delta2_sweep.txt"
echo "== delta sweep FASE 2 v2 (PIC) — carga QEMU fixa em $C ==" > "$LOGS/test_delta2_sweep.txt"

# --- A) múltiplos de página (o universo real de bootloaders) ---
scenario d_zero     0x40200000 128M ""    # delta 0
scenario d_neg1000  0x40201000 128M ""    # delta -0x1000
scenario d_neg10000 0x40210000 128M ""    # delta -0x10000
scenario d_p1000    0x401ff000 128M ""    # delta +0x1000
scenario d_p200000  0x40000000 128M ""    # delta +0x200000 (= test-2g)
# --- base linkada FORA da RAM: Fase 1 abortava (FAR 0x60000ac0); PIC ignora ---
scenario d_unmap    0x60000000 128M ""    # delta -0x1FE00000 (múltiplo de página)
# --- B) sub-página: LIMITE CONHECIDO (ADRP ±1 page) — sintoma catalogado ---
scenario d_p40      0x401fffc0 128M ""    # delta +0x40: SK + strings lixo
# --- C) RAM suja na BSS runtime: radar lê 0xAA, clear PIC zera de verdade ---
scenario d_dirt     0x40200000 128M "-device loader,file=dirt.bin,addr=0x40200d78,force-raw=on"

cat "$LOGS/test_delta2_sweep.txt"
echo ""
echo "=== logs: $LOGS/test_delta2_*.log ==="
