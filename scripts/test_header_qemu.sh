#!/bin/bash
# test_header_qemu.sh — validação empírica do header de Image arm64 no payload
#
# Cenário 0 : header presente, text_offset=0, BOOT_BASE=0x40000000
#             → prova de não-regressão (deve bootar sempre, honre ou não o header)
# Cenário 2a: TEXT_OFFSET=0x200000, BOOT_BASE=0x40200000 (RAM 128M)
#             → se o banner aparecer, o QEMU HONROU text_offset (Cenário 2 do ABL)
# Cenário 2b: TEXT_OFFSET=0x40000000, BOOT_BASE=0x80000000 (RAM 2G)
#             → ensaio geral do ladder-r1: payload linkado a 0x80000000 rodando
# Prova por linha: "rodando em 0x<BOOT_BASE>xx" = carga no endereço do link.
set -u
DIR=/home/z/my-project/download/exynos-baremetal-qemu
LOGS=/home/z/my-project/scripts
export LD_LIBRARY_PATH=/home/z/my-project/scripts/toolchain/qemu-root/usr/lib/x86_64-linux-gnu
QEMU=/home/z/my-project/scripts/toolchain/qemu-root/usr/bin/qemu-system-aarch64
cd "$DIR"

run_bg () {  # $1=RAM  $2=logfile
        $QEMU -M virt -cpu cortex-a53 -smp 4 -m "$1" -nographic -nic none \
              -kernel payload.bin > "$LOGS/$2" 2>&1 &
        QPID=$!
        sleep 4
        kill -9 "$QPID" 2>/dev/null
        wait "$QPID" 2>/dev/null
}

scenario () {  # $1=nome  $2=BOOT_BASE  $3=TEXT_OFFSET  $4=RAM
        echo ""
        echo "### $1 (BOOT_BASE=$2 TEXT_OFFSET=$3 RAM=$4)"
        make -C "$DIR" BOOT_BASE="$2" TEXT_OFFSET="$3" >/dev/null 2>&1
        run_bg "$4" "test_header_$1.log"
        grep -a -E 'rodando em|EL de entrada|x0 =|DTB Magic|magic|memory@ reg|bss_probe|não parece' \
                "$LOGS/test_header_$1.log" | head -8 || \
                echo "  (SEM SAÍDA no UART — bootloader NÃO honrou o endereço esperado)"
}

scenario c0  0x40000000 0x0        128M
scenario c2a 0x40200000 0x200000   128M
scenario c2b 0x80000000 0x40000000 2G

echo ""
echo "=== fim: logs em $LOGS/test_header_*.log ==="
