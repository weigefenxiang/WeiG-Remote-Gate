#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
RESOLVER="$ROOT/resolve-abi.sh"
SOURCE="$ROOT/remote-gate-mapper-entry.c"
VERSION_FILE="$ROOT/../VERSION"
ZIG="${ZIG:-zig}"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"

[ "$#" -eq 1 ] || {
    echo "usage: $0 <build-class>" >&2
    exit 2
}

class="$1"
case "$class" in ''|*[!A-Za-z0-9_.+-]*) exit 2 ;; esac
[ -r "$SOURCE" ] && [ -r "$ROOT/remote-gate-mapper.c" ] && [ -r "$VERSION_FILE" ] || exit 1
version="$(sed -n '1p' "$VERSION_FILE" | tr -d '\r\n')"
case "$version" in ''|*[!0-9A-Za-z._+-]*) echo "invalid VERSION" >&2; exit 1 ;; esac

class_result="$(sh "$RESOLVER" class "$class" 2>/dev/null)" || {
    echo "unknown mapper build class: $class" >&2
    exit 1
}

target="$(printf '%s\n' "$class_result" | awk -F '\t' '{print $1}')"
cflags="$(printf '%s\n' "$class_result" | awk -F '\t' '{print $2}')"
validation="$(printf '%s\n' "$class_result" | awk -F '\t' '{print $3}')"

[ "$validation" = "cross-build" ] || {
    echo "build class requires OpenWrt SDK: $class" >&2
    exit 3
}
[ "$target" != "-" ] && [ -n "$target" ] || exit 1
command -v "$ZIG" >/dev/null 2>&1 || {
    echo "zig compiler not found: $ZIG" >&2
    exit 1
}

mkdir -p "$OUT_DIR"
out="$OUT_DIR/remote-gate-mapper-$class"

# cflags are maintained as trusted repository data in mapper-build-classes.tsv.
# They are never derived from browser, network or router runtime input.
# shellcheck disable=SC2086
"$ZIG" cc \
    -target "$target" \
    $cflags \
    -DREMOTE_GATE_VERSION="\"$version\"" \
    -O2 \
    -static \
    -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wconversion -Wstrict-prototypes \
    -std=c11 \
    -o "$out" \
    "$SOURCE"

chmod 0755 "$out"

if command -v file >/dev/null 2>&1; then
    description="$(file "$out")"
    printf '%s\n' "$description"
    printf '%s\n' "$description" | grep -qi 'statically linked' || {
        echo "portable mapper build is not static: $class" >&2
        rm -f "$out"
        exit 1
    }
fi

printf '%s\n' "$out"
