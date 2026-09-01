#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
MATRIX="${REMOTE_GATE_SDK_COMPAT_MATRIX:-$ROOT/sdk-compat-matrix.tsv}"
BUILDER="$ROOT/build-openwrt-sdk.sh"
OUT_DIR="${2:-$ROOT/dist-sdk}"

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || {
    echo "usage: $0 <sample> [output-dir]" >&2
    exit 2
}

sample="$1"
case "$sample" in ''|*[!A-Za-z0-9_.+-]*) exit 2 ;; esac
[ -r "$MATRIX" ] && [ -x "$BUILDER" ] || exit 1

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

for cmd in curl sha256sum tar file; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "required host tool missing: $cmd" >&2; exit 1; }
done
[ "$archive" != zst ] || command -v zstd >/dev/null 2>&1 || { echo "zstd is required for this SDK" >&2; exit 1; }

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

sh "$BUILDER" "$sdk_root" "$abi" "$OUT_DIR"
binary="$OUT_DIR/remote-gate-mapper-$abi"
[ -x "$binary" ] || { echo "SDK runner did not produce expected mapper: $binary" >&2; exit 1; }

if [ "$abi" = x86_64 ] && [ "$(uname -m 2>/dev/null || true)" = x86_64 ]; then
    log="$tmp/smoke.log"
    set +e
    "$binary" >"$log" 2>&1
    status=$?
    set -e
    cat "$log"
    [ "$status" -eq 2 ] || { echo "SDK mapper host smoke returned $status instead of 2" >&2; exit 1; }
    grep -q '^usage:' "$log" || { echo "SDK mapper host smoke did not print usage" >&2; exit 1; }
fi

printf 'SDK compatibility sample passed: %s\n' "$sample"
