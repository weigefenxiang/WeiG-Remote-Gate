#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
MATRIX="${REMOTE_GATE_SDK_COMPAT_MATRIX:-$ROOT/sdk-compat-matrix.tsv}"
BUILDER="$ROOT/build-openwrt-sdk.sh"
VERSION_FILE="$ROOT/../VERSION"
OUT_DIR="${2:-$ROOT/dist-sdk}"

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || {
    echo "usage: $0 <sample> [output-dir]" >&2
    exit 2
}

sample="$1"
case "$sample" in ''|*[!A-Za-z0-9_.+-]*) exit 2 ;; esac
[ -r "$MATRIX" ] && [ -r "$BUILDER" ] && [ -r "$VERSION_FILE" ] || exit 1
version="$(sed -n '1p' "$VERSION_FILE" | tr -d '\r\n')"
case "$version" in ''|*[!0-9A-Za-z._+-]*) exit 1 ;; esac

row="$(awk -F '\t' -v wanted="$sample" '
    $0 !~ /^#/ && NF == 8 && $1 == wanted {
        print $2 "|" $3 "|" $4 "|" $5 "|" $6 "|" $7 "|" $8
        found = 1
        exit
    }
    END { if (!found) exit 1 }
' "$MATRIX")" || {
    echo "unknown SDK compatibility sample: $sample" >&2
    exit 1
}

oldifs="$IFS"
IFS='|'
set -- $row
IFS="$oldifs"
[ "$#" -eq 7 ] || exit 1
family="$1"
release="$2"
target="$3"
abi="$4"
archive="$5"
sha256="$6"
url="$7"

case "$family" in lede|openwrt|immortalwrt) ;; *) exit 1 ;; esac
case "$release" in ''|*[!0-9A-Za-z._+-]*) exit 1 ;; esac
case "$target" in ''|*[!A-Za-z0-9_./+-]*) exit 1 ;; esac
case "$abi" in ''|*[!A-Za-z0-9_.+-]*) exit 1 ;; esac
case "$archive" in xz|zst) ;; *) exit 1 ;; esac
printf '%s\n' "$sha256" | grep -Eq '^[0-9a-f]{64}$' || exit 1
case "$family" in
    lede|openwrt)
        case "$url" in https://downloads.openwrt.org/releases/*) ;; *) echo "untrusted OpenWrt SDK URL" >&2; exit 1 ;; esac
        ;;
    immortalwrt)
        case "$url" in https://downloads.immortalwrt.org/releases/*) ;; *) echo "untrusted ImmortalWrt SDK URL" >&2; exit 1 ;; esac
        ;;
esac

# OpenWrt 19.07 SDKs still enforce the obsolete Python 2 host prerequisite on
# current hosts even for this self-contained C package. Real 19.07.9 AArch64
# and 19.07.10 x86/MIPS samples all fail that same single prerequisite. Keep
# the exception release-series scoped, while the builder still validates that
# Python 2 is the only failed prerequisite before creating the host stamp.
#
# OpenWrt 19.07.10 x86_64 has an additional old static musl/binutils startup
# quirk. A real 32-bit x86/geode runtime test shows the same five-header/0x1000
# first LOAD layout can execute correctly there, while both MIPS endian variants
# run without the workaround. Keep build-id injection exact to the proven
# x86_64 sample unless another real sample demonstrates the same failure.
sdk_force_prereq=0
sdk_link_flags=''
sdk_emulator=''
case "$sample" in
    openwrt-19.07.*-*) sdk_force_prereq=1 ;;
esac
case "$sample" in
    openwrt-19.07.10-x86_64) sdk_link_flags='-Wl,--build-id=sha1' ;;
    openwrt-19.07.10-x86-geode) sdk_emulator='qemu-i386' ;;
    openwrt-19.07.10-ramips-mt76x8) sdk_emulator='qemu-mipsel' ;;
    openwrt-19.07.10-ar71xx-generic) sdk_emulator='qemu-mips' ;;
    openwrt-19.07.9-armvirt-64) sdk_emulator='qemu-aarch64' ;;
esac

for cmd in curl sha256sum tar file; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "required host tool missing: $cmd" >&2; exit 1; }
done
[ "$archive" != zst ] || command -v zstd >/dev/null 2>&1 || { echo "zstd is required for this SDK" >&2; exit 1; }
[ -z "$sdk_emulator" ] || command -v "$sdk_emulator" >/dev/null 2>&1 || {
    echo "required SDK runtime emulator missing: $sdk_emulator" >&2
    exit 1
}

tmp="$(mktemp -d "${TMPDIR:-/tmp}/remote-gate-sdk.XXXXXX")"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT INT TERM
sdk_root="$tmp/sdk"
archive_file="$tmp/sdk.tar.$archive"
mkdir -p "$sdk_root" "$OUT_DIR"

printf 'SDK sample: %s (%s %s %s, ABI %s)\n' "$sample" "$family" "$release" "$target" "$abi"
curl -fL --retry 3 --retry-delay 2 --connect-timeout 20 "$url" -o "$archive_file"
printf '%s  %s\n' "$sha256" "$archive_file" | sha256sum -c -

case "$archive" in
    xz) tar -xJf "$archive_file" --strip-components=1 -C "$sdk_root" ;;
    zst) tar --zstd -xf "$archive_file" --strip-components=1 -C "$sdk_root" ;;
esac

REMOTE_GATE_SDK_FORCE_PREREQ="$sdk_force_prereq" \
REMOTE_GATE_SDK_LINK_FLAGS="$sdk_link_flags" \
    sh "$BUILDER" "$sdk_root" "$abi" "$OUT_DIR"
binary="$OUT_DIR/remote-gate-mapper-$abi"
[ -x "$binary" ] || { echo "SDK runner did not produce expected mapper: $binary" >&2; exit 1; }

smoke_mapper() {
    runner="$1"
    smoke_binary="$2"
    smoke_label="$3"
    smoke_log="$tmp/smoke-$smoke_label.log"

    if [ "$runner" = direct ]; then
        set +e
        "$smoke_binary" >"$smoke_log" 2>&1
        smoke_status=$?
        set -e
        smoke_identity="$("$smoke_binary" --version 2>/dev/null)" || {
            echo "SDK mapper $smoke_label self-version failed" >&2
            return 1
        }
    else
        set +e
        "$runner" "$smoke_binary" >"$smoke_log" 2>&1
        smoke_status=$?
        set -e
        smoke_identity="$("$runner" "$smoke_binary" --version 2>/dev/null)" || {
            echo "SDK mapper $smoke_label self-version failed" >&2
            return 1
        }
    fi

    cat "$smoke_log"
    [ "$smoke_status" -eq 2 ] || {
        echo "SDK mapper $smoke_label smoke returned $smoke_status instead of 2" >&2
        return 1
    }
    grep -q '^usage:' "$smoke_log" || {
        echo "SDK mapper $smoke_label smoke did not print usage" >&2
        return 1
    }
    [ "$smoke_identity" = "remote-gate-mapper $version api=1" ] || {
        echo "SDK mapper $smoke_label self-version mismatch: $smoke_identity" >&2
        return 1
    }
    printf 'runtime_smoke=%s\n' "$smoke_label"
}

if [ -n "$sdk_emulator" ]; then
    smoke_mapper "$sdk_emulator" "$binary" "$sdk_emulator"
elif [ "$abi" = x86_64 ] && [ "$(uname -m 2>/dev/null || true)" = x86_64 ]; then
    smoke_mapper direct "$binary" host
fi

printf 'SDK compatibility sample passed: %s\n' "$sample"
