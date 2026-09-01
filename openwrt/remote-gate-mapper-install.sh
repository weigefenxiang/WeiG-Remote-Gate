#!/bin/sh
set -eu
umask 077

LIB_DIR="${REMOTE_GATE_LIB_DIR:-/usr/lib/remote-gate}"
PLATFORM="${REMOTE_GATE_PLATFORM:-$LIB_DIR/remote-gate-platform.sh}"
VERSION_FILE="${REMOTE_GATE_VERSION_FILE:-$LIB_DIR/VERSION}"
DEST="${REMOTE_GATE_MAPPER_DEST:-$LIB_DIR/remote-gate-mapper}"
META="${REMOTE_GATE_MAPPER_META:-$LIB_DIR/remote-gate-mapper.meta}"
DEFAULT_RELEASE_BASE="https://github.com/weigefenxiang/WeiG-Remote-Gate/releases/download"
RELEASE_BASE="${REMOTE_GATE_MAPPER_RELEASE_BASE:-$DEFAULT_RELEASE_BASE}"
MANIFEST_OVERRIDE="${REMOTE_GATE_MAPPER_MANIFEST_FILE:-}"
ASSET_DIR_OVERRIDE="${REMOTE_GATE_MAPPER_ASSET_DIR:-}"
MAPPER_API=1

usage() {
    echo "usage: $0 install-release|install-local <binary>|current|status-json" >&2
    exit 2
}

valid_token() { case "$1" in ''|*[!A-Za-z0-9_.+-]*) return 1 ;; *) return 0 ;; esac; }
read_version() {
    [ -r "$VERSION_FILE" ] || return 1
    value="$(sed -n '1p' "$VERSION_FILE" | tr -d '\r\n')"
    valid_token "$value" || return 1
    printf '%s\n' "$value"
}
read_abi() {
    [ -r "$PLATFORM" ] || return 1
    value="$(sh "$PLATFORM" mapper-abi 2>/dev/null || true)"
    valid_token "$value" || return 1
    printf '%s\n' "$value"
}
sha_file() {
    command -v sha256sum >/dev/null 2>&1 || return 1
    sha256sum "$1" | awk '{print $1}'
}
identity_binary() {
    binary="$1"; version="$2"
    [ -f "$binary" ] || return 1
    chmod 0700 "$binary" || return 1
    identity="$("$binary" --version 2>/dev/null)" || return 1
    [ "$identity" = "remote-gate-mapper $version api=$MAPPER_API" ]
}
smoke_binary() {
    binary="$1"; version="$2"; log="$3"
    identity_binary "$binary" "$version" || return 1
    set +e
    "$binary" >"$log" 2>&1
    rc=$?
    set -e
    [ "$rc" -eq 2 ] || return 1
    grep -q '^usage:' "$log"
}
write_meta() {
    tmp="$1"; version="$2"; abi="$3"; class="$4"; asset="$5"; sha="$6"; source="$7"
    {
        printf 'schema=1\n'
        printf 'version=%s\n' "$version"
        printf 'mapper_api=%s\n' "$MAPPER_API"
        printf 'package_abi=%s\n' "$abi"
        printf 'build_class=%s\n' "$class"
        printf 'asset=%s\n' "$asset"
        printf 'sha256=%s\n' "$sha"
        printf 'source=%s\n' "$source"
    } > "$tmp"
    chmod 0644 "$tmp"
}
install_candidate() {
    candidate="$1"; version="$2"; abi="$3"; class="$4"; asset="$5"; sha="$6"; source="$7"; work="$8"
    log="$work/smoke.log"
    smoke_binary "$candidate" "$version" "$log" || { echo "mapper target smoke/self-version failed for ABI $abi" >&2; return 1; }
    mkdir -p "$(dirname "$DEST")"
    staged="${DEST}.new.$$"
    staged_meta="${META}.new.$$"
    trap 'rm -f "$staged" "$staged_meta"' EXIT INT TERM
    cp "$candidate" "$staged"
    chmod 0755 "$staged"
    write_meta "$staged_meta" "$version" "$abi" "$class" "$asset" "$sha" "$source"
    mv -f "$staged" "$DEST"
    mv -f "$staged_meta" "$META"
    trap - EXIT INT TERM
    printf 'Mapper installed: version=%s ABI=%s api=%s source=%s\n' "$version" "$abi" "$MAPPER_API" "$source"
}

meta_value() { sed -n "s/^$1=//p" "$META" 2>/dev/null | sed -n '1p'; }
current() {
    [ -x "$DEST" ] && [ -r "$META" ] || return 1
    version="$(read_version)" || return 1
    abi="$(read_abi)" || return 1
    [ "$(meta_value schema)" = 1 ] || return 1
    [ "$(meta_value version)" = "$version" ] || return 1
    [ "$(meta_value mapper_api)" = "$MAPPER_API" ] || return 1
    [ "$(meta_value package_abi)" = "$abi" ] || return 1
    sha="$(meta_value sha256)"
    printf '%s\n' "$sha" | grep -Eq '^[0-9a-f]{64}$' || return 1
    [ "$(sha_file "$DEST")" = "$sha" ] || return 1
    identity_binary "$DEST" "$version"
}
quarantine_invalid() {
    [ -e "$DEST" ] || return 0
    current && return 0
    chmod 0644 "$DEST" 2>/dev/null || true
    return 0
}

install_release() {
    version="$(read_version)" || { echo "mapper VERSION unavailable" >&2; return 3; }
    abi="$(read_abi)" || { echo "mapper Package ABI unavailable" >&2; return 3; }
    command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum unavailable; mapper release install disabled" >&2; return 3; }
    work="$(mktemp -d "${TMPDIR:-/tmp}/remote-gate-mapper.XXXXXX")"
    trap 'rm -rf "$work"' EXIT INT TERM
    manifest="$work/manifest.tsv"

    if [ -n "$MANIFEST_OVERRIDE" ]; then
        [ -r "$MANIFEST_OVERRIDE" ] || { echo "mapper manifest override is unreadable" >&2; return 3; }
        cp "$MANIFEST_OVERRIDE" "$manifest"
    else
        [ "$RELEASE_BASE" = "$DEFAULT_RELEASE_BASE" ] || [ "${REMOTE_GATE_ALLOW_CUSTOM_MAPPER_RELEASE_BASE:-0}" = 1 ] || {
            echo "custom mapper release base requires explicit opt-in" >&2
            return 3
        }
        command -v curl >/dev/null 2>&1 || { echo "curl unavailable; mapper release install disabled" >&2; return 3; }
        url="$RELEASE_BASE/v$version/remote-gate-mapper-manifest.tsv"
        curl -fsSL --connect-timeout 20 "$url" -o "$manifest" || {
            echo "released mapper manifest unavailable for v$version" >&2
            return 3
        }
    fi

    grep -Fqx '# schema=1' "$manifest" || { echo "invalid mapper release manifest schema" >&2; return 1; }
    manifest_version="$(sed -n 's/^# version=//p' "$manifest" | sed -n '1p')"
    manifest_tag="$(sed -n 's/^# tag=//p' "$manifest" | sed -n '1p')"
    manifest_api="$(sed -n 's/^# mapper_api=//p' "$manifest" | sed -n '1p')"
    [ "$manifest_version" = "$version" ] && [ "$manifest_tag" = "v$version" ] && [ "$manifest_api" = "$MAPPER_API" ] || {
        echo "mapper release manifest version/API mismatch" >&2
        return 1
    }

    row="$(awk -F '\t' -v wanted="$abi" '
        $0 !~ /^#/ && NF == 5 && $1 == wanted {
            if (found) exit 2
            print $2 "|" $3 "|" $4 "|" $5
            found = 1
        }
        END { if (!found) exit 1 }
    ' "$manifest")" || {
        echo "no unique released mapper for Package ABI $abi" >&2
        return 3
    }
    oldifs="$IFS"; IFS='|'; set -- $row; IFS="$oldifs"
    [ "$#" -eq 4 ] || return 1
    class="$1"; asset="$2"; expected_sha="$3"; status="$4"
    valid_token "$class" && valid_token "$asset" || return 1
    printf '%s\n' "$expected_sha" | grep -Eq '^[0-9a-f]{64}$' || return 1
    [ "$status" = released ] || { echo "mapper asset is not released" >&2; return 3; }

    candidate="$work/$asset"
    if [ -n "$ASSET_DIR_OVERRIDE" ]; then
        [ -r "$ASSET_DIR_OVERRIDE/$asset" ] || { echo "released mapper asset unavailable: $asset" >&2; return 3; }
        cp "$ASSET_DIR_OVERRIDE/$asset" "$candidate"
    else
        url="$RELEASE_BASE/v$version/$asset"
        curl -fsSL --connect-timeout 20 "$url" -o "$candidate" || {
            echo "released mapper asset download failed: $asset" >&2
            return 3
        }
    fi
    actual_sha="$(sha_file "$candidate")" || return 1
    [ "$actual_sha" = "$expected_sha" ] || { echo "mapper SHA-256 mismatch for ABI $abi" >&2; return 1; }
    install_candidate "$candidate" "$version" "$abi" "$class" "$asset" "$actual_sha" released "$work"
    trap - EXIT INT TERM
    rm -rf "$work"
}

install_local() {
    [ "$#" -eq 1 ] || usage
    source_binary="$1"
    [ -f "$source_binary" ] && [ -x "$source_binary" ] || { echo "local mapper source is not executable" >&2; return 1; }
    version="$(read_version)" || return 1
    abi="$(read_abi)" || return 1
    sha="$(sha_file "$source_binary")" || { echo "sha256sum is required for local mapper install" >&2; return 1; }
    work="$(mktemp -d "${TMPDIR:-/tmp}/remote-gate-mapper-local.XXXXXX")"
    trap 'rm -rf "$work"' EXIT INT TERM
    candidate="$work/remote-gate-mapper-local"
    cp "$source_binary" "$candidate"
    install_candidate "$candidate" "$version" "$abi" local "$(basename "$source_binary")" "$sha" local "$work"
    trap - EXIT INT TERM
    rm -rf "$work"
}

status_json() {
    if current; then ready=true; else ready=false; fi
    printf '{"ready":%s,"version":"%s","mapper_api":"%s","package_abi":"%s","source":"%s"}\n' \
        "$ready" "$(meta_value version)" "$(meta_value mapper_api)" "$(meta_value package_abi)" "$(meta_value source)"
}

case "${1:-}" in
    install-release)
        shift; [ "$#" -eq 0 ] || usage
        set +e
        install_release
        rc=$?
        set -e
        [ "$rc" -eq 0 ] || quarantine_invalid
        exit "$rc"
        ;;
    install-local) shift; install_local "$@" ;;
    current) shift; [ "$#" -eq 0 ] || usage; current ;;
    status-json) shift; [ "$#" -eq 0 ] || usage; status_json ;;
    *) usage ;;
esac
