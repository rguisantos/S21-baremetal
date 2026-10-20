#!/bin/bash
# Reproduce focused PR tests; QEMU's intentional park must end via timeout.
set -eu
cd "$(dirname "$0")/.."
root=$PWD
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
for mode in default enabled; do
    flags=()
    [ "$mode" = default ] || flags+=(-DR10_UART_FIRMWARE_CONFIGURED)
    cc -O1 -g -fsanitize=address,undefined "${flags[@]}" \
        r8/tests/uart_smoke.c -o "$build/uart-$mode"
    ASAN_OPTIONS=detect_leaks=0 "$build/uart-$mode"
done
make -C r8 BUILD="$build/arm" "$build/arm/atomic_smoke.elf"
status=0
timeout 8 make -C r8 BUILD="$build/arm" run_atomic > "$build/atomic.log" 2>&1 || status=$?
cat "$build/atomic.log"
[ "$status" -eq 0 ] || [ "$status" -eq 124 ]
grep -q '^ATOMIC PASS' "$build/atomic.log"
! grep -q 'ATOMIC FAIL' "$build/atomic.log"
