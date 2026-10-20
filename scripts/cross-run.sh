#!/bin/bash
# Keep the host loader/libc; expose only the cross-binutils libraries.
set -eu
root=$(cd "$1" && pwd)
shift
runtime="$root/../build/cross-libs"
mkdir -p "$runtime"
for lib in "$root"/usr/lib/x86_64-linux-gnu/lib{bfd,opcodes,ctf,sframe}*.so*; do
    [ -e "$lib" ] || continue
    link="$runtime/$(basename "$lib")"
    [ -L "$link" ] || ln -s "$lib" "$link" 2>/dev/null || [ -L "$link" ]
done
export LD_LIBRARY_PATH="$runtime${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$@"
