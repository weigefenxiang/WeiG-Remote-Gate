#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
VERSION_FILE="$ROOT/../VERSION"

[ "$#" -eq 2 ] || {
    echo "usage: $0 <build-class> <binary>" >&2
    exit 2
}

class="$1"
binary="$2"
[ -x "$binary" ] && [ -r "$VERSION_FILE" ] || exit 1
version="$(sed -n '1p' "$VERSION_FILE" | tr -d '\r\n')"
case "$version" in ''|*[!0-9A-Za-z._+-]*) exit 1 ;; esac

case "$class" in
    x86_64) runner="" ;;
    x86_i486) runner=qemu-i386 ;;
    aarch64) runner=qemu-aarch64 ;;
    armv6_le|armv7_le) runner=qemu-arm ;;
    mips32_be) runner=qemu-mips ;;
    mips32_le) runner=qemu-mipsel ;;
    mips64_be) runner=qemu-mips64 ;;
    mips64_le) runner=qemu-mips64el ;;
    powerpc32_be) runner=qemu-ppc ;;
    powerpc64_be) runner=qemu-ppc64 ;;
    riscv64) runner=qemu-riscv64 ;;
    loongarch64) runner=qemu-loongarch64 ;;
    *) echo "no smoke runner for mapper class: $class" >&2; exit 2 ;;
esac

run_binary() {
    if [ -n "$runner" ]; then
        "$runner" "$binary" "$@"
    else
        "$binary" "$@"
    fi
}

if [ -n "$runner" ]; then
    command -v "$runner" >/dev/null 2>&1 || {
        echo "missing QEMU runner: $runner" >&2
        exit 1
    }
fi

set +e
run_binary >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 2 ] || {
    echo "mapper smoke test returned $rc for $class; expected argument-validation exit 2" >&2
    exit 1
}

identity="$(run_binary --version 2>/dev/null)" || {
    echo "mapper self-version failed for $class" >&2
    exit 1
}
[ "$identity" = "remote-gate-mapper $version api=1" ] || {
    echo "mapper self-version mismatch for $class: $identity" >&2
    exit 1
}
