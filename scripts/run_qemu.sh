#!/bin/bash
# run_qemu.sh — wrapper do QEMU user-space provisionado em scripts/toolchain
# uso: bash run_qemu.sh <flags qemu...>   (timeout via T=..., default 6s)
export LD_LIBRARY_PATH=/home/z/my-project/scripts/toolchain/qemu-root/usr/lib/x86_64-linux-gnu
T=${T:-6}
exec timeout "$T" /home/z/my-project/scripts/toolchain/qemu-root/usr/bin/qemu-system-aarch64 "$@"
