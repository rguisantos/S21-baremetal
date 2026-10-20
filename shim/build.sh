#!/bin/bash
# S21 Ultra Exynos 2100 shim build script

set -e

cd "$(dirname "$0")"
TOOLS="${TOOLS:-$(cd ../tools/root && pwd)}"
CROSS="${CROSS:-$TOOLS/usr/bin/aarch64-linux-gnu-}"
export PATH="$(dirname "$CROSS"):$PATH"
CC=${CROSS}gcc
LD=${CROSS}ld
OBJCOPY=${CROSS}objcopy

CFLAGS="-ffreestanding -nostdlib -fno-builtin -fno-stack-protector \
        -mgeneral-regs-only -march=armv8-a -O2 -std=gnu11 \
        -Wall -Wextra -I."

LDFLAGS="-nostdlib -static -T shim.ld --build-id=none"

BUILD_DIR=build
SRC="shim.c loader.c mmu.c fdt.c start.S"

mkdir -p $BUILD_DIR

echo "Building shim..."
bash ../scripts/cross-run.sh "$TOOLS" "$CC" $CFLAGS -c start.S -o $BUILD_DIR/start.o
bash ../scripts/cross-run.sh "$TOOLS" "$CC" $CFLAGS -c shim.c -o $BUILD_DIR/shim.o
bash ../scripts/cross-run.sh "$TOOLS" "$CC" $CFLAGS -c loader.c -o $BUILD_DIR/loader.o
bash ../scripts/cross-run.sh "$TOOLS" "$CC" $CFLAGS -c mmu.c -o $BUILD_DIR/mmu.o
bash ../scripts/cross-run.sh "$TOOLS" "$CC" $CFLAGS -c fdt.c -o $BUILD_DIR/fdt.o

bash ../scripts/cross-run.sh "$TOOLS" "$LD" $LDFLAGS -o $BUILD_DIR/shim.elf \
    $BUILD_DIR/start.o \
    $BUILD_DIR/shim.o \
    $BUILD_DIR/loader.o \
    $BUILD_DIR/mmu.o \
    $BUILD_DIR/fdt.o

bash ../scripts/cross-run.sh "$TOOLS" "$OBJCOPY" -O binary $BUILD_DIR/shim.elf $BUILD_DIR/shim.bin

echo "Build complete: $BUILD_DIR/shim.elf $BUILD_DIR/shim.bin"
ls -la $BUILD_DIR/