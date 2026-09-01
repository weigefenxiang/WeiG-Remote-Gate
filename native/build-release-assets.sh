#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
ABI_MAP="$ROOT/mapper-abi-map.tsv"
VERSION_FILE="$ROOT/../VERSION"
CLASS_DIR="${1:-$ROOT/dist}"
OUT_DIR="${2:-$ROOT/release}"
RELEASE_COMMIT="${REMOTE_GATE_RELEASE_COMMIT:-unknown}"
MAPPER_API=1

[ -r "$ABI_MAP" ] && [ -r "$VERSION_FILE" ] || exit 1
version="$(sed -n '1p' "$VERSION_FILE" | tr -d '\r\n')"
case "$version" in ''|*[!0-9A-Za-z._+-]*) echo "invalid VERSION" >&2; exit 1 ;; esac
case "$RELEASE_COMMIT" in unknown|'') ;; *[!0-9a-f]*) echo "invalid release commit" >&2; exit 1 ;; esac

command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum is required" >&2; exit 1; }
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
manifest="$OUT_DIR/remote-gate-mapper-manifest.tsv"
{
    printf '# schema=1\n'
    printf '# version=%s\n' "$version"
    printf '# tag=v%s\n' "$version"
    printf '# mapper_api=%s\n' "$MAPPER_API"
    printf '# commit=%s\n' "$RELEASE_COMMIT"
    printf '# package_abi\tbuild_class\tasset\tsha256\tstatus\n'
} > "$manifest"

count=0
while IFS="$(printf '\t')" read -r abi class delivery; do
    [ -n "$abi" ] || continue
    case "$abi" in \#*) continue ;; esac
    [ "$delivery" = cross-candidate ] || continue
    case "$abi" in *[!A-Za-z0-9_.+-]*) echo "invalid package ABI in map: $abi" >&2; exit 1 ;; esac
    case "$class" in ''|*[!A-Za-z0-9_.+-]*) echo "invalid build class in map: $class" >&2; exit 1 ;; esac
    binary="$CLASS_DIR/remote-gate-mapper-$class"
    [ -x "$binary" ] || { echo "missing verified class binary: $class" >&2; exit 1; }
    asset="remote-gate-mapper-$abi"
    cp "$binary" "$OUT_DIR/$asset"
    chmod 0755 "$OUT_DIR/$asset"
    sha256="$(sha256sum "$OUT_DIR/$asset" | awk '{print $1}')"
    printf '%s\t%s\t%s\t%s\treleased\n' "$abi" "$class" "$asset" "$sha256" >> "$manifest"
    count=$((count + 1))
done < "$ABI_MAP"

[ "$count" -gt 0 ] || { echo "release manifest contains no mapper assets" >&2; exit 1; }
chmod 0644 "$manifest"
printf 'release_version=%s\n' "$version"
printf 'mapper_api=%s\n' "$MAPPER_API"
printf 'release_assets=%s\n' "$count"
printf '%s\n' "$manifest"
