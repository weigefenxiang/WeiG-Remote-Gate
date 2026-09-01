#!/bin/sh
set -eu

[ "$#" -eq 2 ] || {
    echo "usage: $0 <build-class> <binary>" >&2
    exit 2
}

class="$1"
binary="$2"
[ -x "$binary" ] || exit 1

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

if [ -n "$runner" ]; then
    command -v "$runner" >/dev/null 2>&1 || {
        echo "missing QEMU runner: $runner" >&2
        exit 1
    }
    set +e
    "$runner" "$binary" >/dev/null 2>&1
    rc=$?
    set -e
else
    set +e
    "$binary" >/dev/null 2>&1
    rc=$?
    set -e
fi

[ "$rc" -eq 2 ] || {
    echo "mapper smoke test returned $rc for $class; expected argument-validation exit 2" >&2
    exit 1
}
