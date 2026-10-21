#!/system/bin/sh
# Read selected UART/MUIC attributes; no sysfs writes or root escalation.
# Run inside rish. Creates a new report exclusively, refusing to overwrite.
set -u
out=${1:-/sdcard/Download/s21-uart-state.txt}
umask 077
set -C
if ! exec 3>"$out"; then
    printf 'Cannot create report (existing file or inaccessible path): %s\n' "$out" >&2
    exit 1
fi
{
    printf 'S21 UART/MUIC read-only state v1\n'
    date -u
    id
    for key in ro.product.model ro.build.display.id ro.boot.bootloader; do
        printf '\n[property %s]\n' "$key"
        if command -v getprop >/dev/null 2>&1; then getprop "$key"; else printf 'getprop unavailable\n'; fi
    done
    for node in /sys/class/sec/switch/uart_sel /sys/class/sec/switch/uart_en \
                /sys/class/sec/switch/adc /sys/class/sec/switch/attached_dev \
                /sys/class/sec/switch/usb_state; do
        printf '\n[%s]\n' "$node"
        if [ ! -e "$node" ]; then
            printf 'ABSENT (or hidden by permissions)\n'
        elif [ ! -r "$node" ]; then
            ls -l "$node" 2>&1
            printf 'UNREADABLE\n'
        else
            cat "$node" 2>&1
        fi
    done
    printf '\nEnd. Runtime Android state; does not establish bootloader handoff state.\n'
} >&3 2>&1
exec 3>&-
printf 'Report created: %s\n' "$out"
