#!/system/bin/sh
# Read only source-identified snapshot proc files. Never read streaming kmsg.
# Run in rish; creates a new directory and refuses to overwrite any directory.
set -u
umask 077
out=${1:-/sdcard/Download/s21-boot-logs}
proc_root=${S21_LOG_PROC_ROOT:-/proc} # fixture root for local tests
if ! mkdir "$out"; then
    printf 'Cannot create a new output directory: %s\n' "$out" >&2
    exit 1
fi
report=$out/report.txt
{
    printf 'S21 bounded boot-log collection v1\n'
    date -u
    id
    printf 'Read-only source interfaces. Limit: 2097152 bytes and 5 seconds per file.\n'
    for name in last_kmsg first_kmsg sec_log; do
        node=$proc_root/$name
        printf '\n[%s]\n' "$node"
        if [ ! -e "$node" ]; then
            printf 'ABSENT (or hidden by permissions)\n'
            continue
        fi
        ls -l "$node" 2>&1
        if [ ! -r "$node" ]; then
            printf 'UNREADABLE\n'
            continue
        fi
        if ! command -v timeout >/dev/null 2>&1 || ! command -v head >/dev/null 2>&1; then
            printf 'SKIPPED: timeout/head unavailable\n'
            continue
        fi
        if timeout 5 head -c 2097152 "$node" >"$out/$name.bin" 2>"$out/$name.error.txt"; then
            status=0
        else
            status=$?
        fi
        size=$(wc -c <"$out/$name.bin")
        printf 'READ_EXIT=%s BYTES=%s FILE=%s.bin\n' "$status" "$size" "$name"
        printf 'Bounded capture; reaching the limit may indicate truncation.\n'
        if [ "$status" -ne 0 ]; then
            printf 'Read failed or timed out; captured bytes may be incomplete.\n'
            cat "$out/$name.error.txt"
        fi
    done
    printf '\nEnd. Proc captures are not a physical header+RAM dump.\n'
} >"$report" 2>&1
printf 'Created: %s\nSend report.txt first; log binaries may contain private information.\n' "$out"
