#!/bin/bash
# Model + production-entry QEMU test. No phone operations.
set -eu
cd "$(dirname "$0")/.."
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
for model in gic exceptions; do
    cc -O1 -g -Ir8/common -Wall -Wextra -Werror -fsanitize=address,undefined \
        "r8/tests/${model}_model.c" -o "$build/$model-model"
    ASAN_OPTIONS=detect_leaks=0 "$build/$model-model"
done
make -C r8 BUILD="$build/arm" "$build/arm/r10_stage_test.elf"
status=0
timeout 8 make -C r8 BUILD="$build/arm" run_r10_stage_test > "$build/stage.log" 2>&1 || status=$?
cat "$build/stage.log"
[ "$status" -eq 124 ]
grep -q '^R10 BOOT PASS:' "$build/stage.log"
grep -q '^R10 FDT PASS:' "$build/stage.log"
grep -q '^R10 TIMER PASS:' "$build/stage.log"
grep -q '^R10 FATAL kind=0x0 ' "$build/stage.log"
! grep -q 'FAIL' "$build/stage.log"
