#!/bin/bash
# regress.sh — suíte de regressão do kit: R8A, R8B, R8C e R9
#
# Roda cada módulo pelo alvo run_* do Makefile (fonte única da verdade
# para as flags de máquina) com timeout externo. Os módulos entram em
# park/wfe deliberadamente — exit 124 (timeout) é ESPERADO; o critério
# é a assinatura "=== Rxx PASS" no log de cada um.
#
# Uso: scripts/regress.sh   (ou `make regress` dentro de r8/)

set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
R8DIR="$KIT/r8"
LOGDIR="$R8DIR/logs"
mkdir -p "$LOGDIR"

pkill -f qemu-system-aarch64 2>/dev/null
sleep 1

declare -A SIG=( [r8a]="R8A PASS" [r8b]="R8B PASS" [r8c]="R8C PASS" [r9]="R9 PASS" )
declare -A LIM=( [r8a]=25 [r8b]=25 [r8c]=40 [r9]=35 )
mods=(r8a r8b r8c r9)

rc=0
for m in "${mods[@]}"; do
    log="$LOGDIR/regress_${m}.log"
    timeout "${LIM[$m]}" make -C "$R8DIR" --no-print-directory "run_$m" \
        </dev/null >"$log" 2>&1
    if grep -q "${SIG[$m]}" "$log"; then
        printf "  %-4s PASS  (assinatura: \"%s\")\n" "$m" "${SIG[$m]}"
    else
        printf "  %-4s FAIL  (sem assinatura — ver logs/regress_%s.log)\n" "$m" "$m"
        rc=1
    fi
    pkill -f qemu-system-aarch64 2>/dev/null
done

if [ "$rc" -eq 0 ]; then
    echo "REGRESSAO: 4/4 PASS"
else
    echo "REGRESSAO: FALHOU — ver logs"
fi
exit "$rc"
