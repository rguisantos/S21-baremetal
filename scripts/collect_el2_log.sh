#!/system/bin/sh
# One bounded capture of the source-identified Harx sysfs getter.
# Reading may advance the firmware log cursor. Never writes/resets the attribute.
set -u
umask 077
out=${1:-/sdcard/Download/s21-el2-log}
sys_root=${S21_EL2_SYS_ROOT:-/sys} # fixture root; leave unset on the phone
if ! mkdir "$out"; then
    printf 'Cannot create a new output directory: %s\n' "$out" >&2
    exit 1
fi
report=$out/report.txt
{
    printf 'S21 Harx EL2 log collection v1\n'
    date -u
    id
    printf 'One capture, at most 4096 bytes / 5 seconds.\n'
    printf 'Reading may advance the Harx log cursor; no reset or sysfs writes.\n'
    for key in ro.product.model ro.build.display.id ro.boot.bootloader; do
        if command -v getprop >/dev/null 2>&1; then
            printf '[%s] ' "$key"
            getprop "$key"
        fi
    done
    selected=
    for candidate in "$sys_root/devices/platform/el2_dynamic_lv3/exynos_el2_log" \
                     "$sys_root"/bus/platform/drivers/exynos-el2/*/exynos_el2_log; do
        if [ -e "$candidate" ]; then
            selected=$candidate
            break
        fi
    done
    if [ -z "$selected" ]; then
        printf 'ABSENT (or hidden by permissions): no source-identified log attribute\n'
    else
        printf '\n[NODE %s]\n' "$selected"
        ls -l "$selected" 2>&1
        if [ ! -r "$selected" ]; then
            printf 'UNREADABLE\n'
        elif ! command -v timeout >/dev/null 2>&1 || ! command -v head >/dev/null 2>&1; then
            printf 'SKIPPED: timeout/head unavailable\n'
        else
            if timeout 5 head -c 4096 "$selected" >"$out/el2-log.txt" 2>"$out/read-error.txt"; then
                status=0
            else
                status=$?
            fi
            size=$(wc -c <"$out/el2-log.txt")
            printf 'READ_EXIT=%s BYTES=%s FILE=el2-log.txt\n' "$status" "$size"
            printf 'No aliases or further pages were read. A full capture may be truncated.\n'
            if [ "$status" -ne 0 ]; then
                printf 'Read failed or timed out; bytes may be incomplete.\n'
                cat "$out/read-error.txt"
            fi
        fi
    fi
    printf '\nEnd. This is a sysfs page, not a raw RAM dump or verified memory map.\n'
} >"$report" 2>&1
printf 'Created: %s\nSend report.txt first. Review el2-log.txt before sharing.\n' "$out"
