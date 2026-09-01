#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
RESOLVER="$ROOT/resolve-abi.sh"
PACKAGE_TEMPLATE="$ROOT/openwrt-sdk-package/Makefile"
SOURCE="$ROOT/remote-gate-mapper.c"
ENTRY="$ROOT/remote-gate-mapper-entry.c"
VERSION_FILE="$ROOT/../VERSION"

usage() {
    echo "usage: $0 <sdk-root> <expected-package-abi> [output-dir]" >&2
    exit 2
}

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || usage

SDK_ROOT="$1"
EXPECTED_ABI="$2"
OUT_DIR="${3:-$ROOT/dist-sdk}"
PACKAGE_DIR="$SDK_ROOT/package/weig-remote-gate-mapper"
SDK_FORCE_PREREQ="${REMOTE_GATE_SDK_FORCE_PREREQ:-0}"

case "$EXPECTED_ABI" in ''|*[!A-Za-z0-9_.+-]*) usage ;; esac
case "$SDK_FORCE_PREREQ" in 0|1) ;; *) echo "invalid REMOTE_GATE_SDK_FORCE_PREREQ" >&2; exit 1 ;; esac
[ -d "$SDK_ROOT" ] || { echo "SDK root not found: $SDK_ROOT" >&2; exit 1; }
[ -r "$SDK_ROOT/rules.mk" ] || { echo "not an OpenWrt-family SDK root: $SDK_ROOT" >&2; exit 1; }
[ -r "$PACKAGE_TEMPLATE" ] && [ -r "$SOURCE" ] && [ -r "$ENTRY" ] && [ -r "$VERSION_FILE" ] || exit 1

resolved="$(sh "$RESOLVER" full "$EXPECTED_ABI" 2>/dev/null)" || {
    echo "unsupported package ABI: $EXPECTED_ABI" >&2
    exit 1
}
class="$(printf '%s\n' "$resolved" | awk -F '\t' '{print $1}')"
delivery="$(printf '%s\n' "$resolved" | awk -F '\t' '{print $2}')"
validation="$(printf '%s\n' "$resolved" | awk -F '\t' '{print $5}')"

[ -n "$class" ] && [ -n "$delivery" ] && [ -n "$validation" ] || exit 1

version="$(sed -n '1p' "$VERSION_FILE" | tr -d '\r\n')"
case "$version" in ''|*[!0-9A-Za-z._+-]*) echo "invalid VERSION" >&2; exit 1 ;; esac

if [ -e "$PACKAGE_DIR" ]; then
    [ -f "$PACKAGE_DIR/.weig-remote-gate-owned" ] || {
        echo "refusing to replace non-Remote-Gate SDK package directory: $PACKAGE_DIR" >&2
        exit 1
    }
    rm -rf "$PACKAGE_DIR"
fi
mkdir -p "$PACKAGE_DIR/src" "$OUT_DIR"
: > "$PACKAGE_DIR/.weig-remote-gate-owned"
cp "$PACKAGE_TEMPLATE" "$PACKAGE_DIR/Makefile"
cp "$SOURCE" "$PACKAGE_DIR/src/remote-gate-mapper.c"
cp "$ENTRY" "$PACKAGE_DIR/src/remote-gate-mapper-entry.c"
printf '%s\n' "$version" > "$PACKAGE_DIR/VERSION"

cleanup() {
    if [ -f "$PACKAGE_DIR/.weig-remote-gate-owned" ]; then
        rm -rf "$PACKAGE_DIR"
    fi
}
trap cleanup EXIT INT TERM

(
    cd "$SDK_ROOT"
    if [ "$SDK_FORCE_PREREQ" = 1 ]; then
        FORCE=1 make defconfig
    else
        make defconfig
    fi
)

[ -r "$SDK_ROOT/.config" ] || {
    echo "SDK defconfig did not create .config: $SDK_ROOT/.config" >&2
    exit 1
}

sdk_abi="$(sed -n 's/^CONFIG_TARGET_ARCH_PACKAGES="\([^"]*\)"/\1/p' "$SDK_ROOT/.config" | sed -n '1p')"
if [ -z "$sdk_abi" ]; then
    sdk_abi="$(sed -n 's/^CONFIG_TARGET_ARCH_PACKAGES=\([^[:space:]]*\)$/\1/p' "$SDK_ROOT/.config" | sed -n '1p')"
    sdk_abi="${sdk_abi#\"}"
    sdk_abi="${sdk_abi%\"}"
fi
[ -n "$sdk_abi" ] || {
    echo "SDK does not expose CONFIG_TARGET_ARCH_PACKAGES after defconfig; refusing to guess ABI" >&2
    exit 1
}
[ "$sdk_abi" = "$EXPECTED_ABI" ] || {
    echo "SDK ABI mismatch: expected $EXPECTED_ABI, SDK reports $sdk_abi" >&2
    exit 1
}

(
    cd "$SDK_ROOT"
    make package/weig-remote-gate-mapper/clean >/dev/null 2>&1 || true
    if [ "$SDK_FORCE_PREREQ" = 1 ]; then
        FORCE=1 make package/weig-remote-gate-mapper/compile V=s -j1
    else
        make package/weig-remote-gate-mapper/compile V=s -j1
    fi
)

# OpenWrt's autoremove phase may remove the direct build binary after the IPK
# is created. Recover the mapper from package staging when that happens.
binary=""
for candidate in \
    "$(find "$SDK_ROOT/build_dir" -type f -path "*/remote-gate-mapper-${version}/remote-gate-mapper" 2>/dev/null | sed -n '1p')" \
    "$(find "$SDK_ROOT/build_dir" -type f -path "*/remote-gate-mapper-${version}/.pkgdir/remote-gate-mapper/usr/lib/remote-gate/remote-gate-mapper" 2>/dev/null | sed -n '1p')" \
    "$(find "$SDK_ROOT/build_dir" -type f -path "*/remote-gate-mapper-${version}/ipkg-*/remote-gate-mapper/usr/lib/remote-gate/remote-gate-mapper" 2>/dev/null | sed -n '1p')"
do
    [ -n "$candidate" ] || continue
    [ -f "$candidate" ] || continue
    binary="$candidate"
    break
done
[ -n "$binary" ] || {
    echo "SDK build completed without a mapper binary" >&2
    find "$SDK_ROOT/bin" -type f -name 'remote-gate-mapper_*' -print 2>/dev/null | sed 's/^/SDK package output: /' >&2 || true
    exit 1
}
chmod 0755 "$binary" 2>/dev/null || true

out="$OUT_DIR/remote-gate-mapper-$EXPECTED_ABI"
cp "$binary" "$out"
chmod 0755 "$out"

if command -v file >/dev/null 2>&1; then
    description="$(file "$out")"
    printf '%s\n' "$description"
    printf '%s\n' "$description" | grep -qi 'statically linked' || {
        echo "SDK mapper output is not statically linked: $EXPECTED_ABI" >&2
        rm -f "$out"
        exit 1
    }
fi

sha256=""
if command -v sha256sum >/dev/null 2>&1; then
    sha256="$(sha256sum "$out" | awk '{print $1}')"
fi
printf 'package_abi=%s\n' "$EXPECTED_ABI"
printf 'build_class=%s\n' "$class"
printf 'delivery=%s\n' "$delivery"
printf 'validation=%s\n' "$validation"
printf 'sha256=%s\n' "$sha256"
printf '%s\n' "$out"
