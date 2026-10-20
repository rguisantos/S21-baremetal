#!/bin/sh
# bootstrap_tools.sh — ambiente userspace (sem root) para o kit R8:
#   1. cross-toolchain AArch64 (gcc + binutils) via .debs do Debian
#   2. QEMU (qemu-system-arm => qemu-system-aarch64) via .debs do Debian
# Tudo extraído com dpkg -x em tools/root; nada é instalado no sistema.
set -e

TOOLS=${TOOLS:-$(CDPATH= cd -- "$(dirname -- "$0")/../tools" && pwd)}
DL=$TOOLS/debs
ROOT=$TOOLS/root
mkdir -p "$DL" "$ROOT"

# ---------------------------------------------------------------
# 1) calcular conjunto de pacotes (closure de Depends, sem
#    Recommends/Suggests) já excluindo o que está instalado no host
# ---------------------------------------------------------------
collect() {
    apt-cache depends --recurse --no-recommends --no-suggests \
        --no-conflicts --no-breaks --no-replaces --no-enhances "$@" 2>/dev/null \
        | grep "^[a-zA-Z0-9]" | sort -u
}

HOST_INSTALLED=$(mktemp)
dpkg-query -W -f '${binary:Package}\n' 2>/dev/null | sort -u > "$HOST_INSTALLED"

need() {  # imprime pacotes que faltam (não instalados no host)
    collect "$@" | while read -r p; do
        grep -qx "$p" "$HOST_INSTALLED" || echo "$p"
    done
}

PKGS_QEMU=$(need qemu-system-arm)
PKGS_CROSS=$(need gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu)

# ---------------------------------------------------------------
# 2) baixar e extrair
# ---------------------------------------------------------------
fetch_extract() {
    cd "$DL" || exit 1
    for p in $1; do
        [ -n "$p" ] || continue
        if ls "${p}_"*.deb >/dev/null 2>&1; then
            echo "  [cache] $p"
        else
            apt-get download "$p" >/dev/null 2>&1 && echo "  [down ] $p" || echo "  [FAIL ] $p"
        fi
    done
    for f in "$DL"/*.deb; do
        [ -e "$f" ] || continue
        b=$(basename "$f")
        [ -f "$ROOT/.done-$b" ] && continue
        dpkg -x "$f" "$ROOT"
        touch "$ROOT/.done-$b"
    done
}

echo "== baixando toolchain cross =="
fetch_extract "$PKGS_CROSS"
echo "== baixando qemu =="
fetch_extract "$PKGS_QEMU"

# ---------------------------------------------------------------
# 3) verificação
# ---------------------------------------------------------------
LIBDIR="$ROOT/usr/lib/x86_64-linux-gnu"
export LD_LIBRARY_PATH="$LIBDIR:$ROOT/usr/lib"
echo "== teste =="
"$ROOT/usr/bin/qemu-system-aarch64" --version | head -1
"$ROOT/usr/bin/aarch64-linux-gnu-gcc" --version | head -1
"$ROOT/usr/bin/aarch64-linux-gnu-as" --version | head -1
echo "OK — ferramentas em $ROOT"
