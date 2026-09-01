#!/bin/sh
set -eu
umask 077

LIB_DIR="${REMOTE_GATE_LIB_DIR:-/usr/lib/remote-gate}"
STATE_DIR="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}"
PLATFORM="${REMOTE_GATE_PLATFORM:-$LIB_DIR/remote-gate-platform.sh}"
VERSION_FILE="${REMOTE_GATE_VERSION_FILE:-$LIB_DIR/VERSION}"
DEST="${REMOTE_GATE_MAPPER_DEST:-$LIB_DIR/remote-gate-mapper}"
META="${REMOTE_GATE_MAPPER_META:-$LIB_DIR/remote-gate-mapper.meta}"
BACKUP_DIR="${REMOTE_GATE_MAPPER_BACKUP_DIR:-$STATE_DIR/mapper-backup}"
BACKUP_DEST="$BACKUP_DIR/remote-gate-mapper"
BACKUP_META="$BACKUP_DIR/remote-gate-mapper.meta"
MAPPING="${REMOTE_GATE_MAPPING_HELPER:-$LIB_DIR/remote-gate-mapping.sh}"
AGENT="${REMOTE_GATE_AGENT_HELPER:-$LIB_DIR/remote-gate-agent.sh}"
DEFAULT_RELEASE_BASE="https://github.com/weigefenxiang/WeiG-Remote-Gate/releases/download"
RELEASE_BASE="${REMOTE_GATE_MAPPER_RELEASE_BASE:-$DEFAULT_RELEASE_BASE}"
MANIFEST_OVERRIDE="${REMOTE_GATE_MAPPER_MANIFEST_FILE:-}"
ASSET_DIR_OVERRIDE="${REMOTE_GATE_MAPPER_ASSET_DIR:-}"
DEFAULT_DEV_RELEASE_BASE="https://github.com/weigefenxiang/WeiG-Remote-Gate/releases/download"
DEV_RELEASE_BASE="${REMOTE_GATE_MAPPER_DEV_RELEASE_BASE:-$DEFAULT_DEV_RELEASE_BASE}"
DEV_MANIFEST_OVERRIDE="${REMOTE_GATE_MAPPER_DEV_MANIFEST_FILE:-}"
DEV_ASSET_DIR_OVERRIDE="${REMOTE_GATE_MAPPER_DEV_ASSET_DIR:-}"
MAPPER_API=1

usage() {
    echo "usage: $0 install|install-release|install-dev|install-local <binary>|update|repair|rollback|uninstall|current|status|status-json" >&2
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
    [ -f "$binary" ] && [ -x "$binary" ] || return 1
    identity="$("$binary" --version 2>/dev/null)" || return 1
    [ "$identity" = "remote-gate-mapper $version api=$MAPPER_API" ]
}
smoke_binary() {
    binary="$1"; version="$2"; log="$3"
    chmod 0700 "$binary" || return 1
    identity_binary "$binary" "$version" || return 1
    set +e
    "$binary" >"$log" 2>&1
    rc=$?
    set -e
    [ "$rc" -eq 2 ] || return 1
    grep -q '^usage:' "$log"
}
meta_value_from() { sed -n "s/^$2=//p" "$1" 2>/dev/null | sed -n '1p'; }
meta_value() { meta_value_from "$META" "$1"; }
validate_pair() {
    binary="$1"; meta="$2"
    [ -x "$binary" ] && [ -r "$meta" ] || return 1
    version="$(read_version)" || return 1
    abi="$(read_abi)" || return 1
    [ "$(meta_value_from "$meta" schema)" = 1 ] || return 1
    [ "$(meta_value_from "$meta" version)" = "$version" ] || return 1
    [ "$(meta_value_from "$meta" mapper_api)" = "$MAPPER_API" ] || return 1
    [ "$(meta_value_from "$meta" package_abi)" = "$abi" ] || return 1
    vp_sha="$(meta_value_from "$meta" sha256)"
    printf '%s\n' "$vp_sha" | grep -Eq '^[0-9a-f]{64}$' || return 1
    [ "$(sha_file "$binary")" = "$vp_sha" ] || return 1
    identity_binary "$binary" "$version"
}
current() { validate_pair "$DEST" "$META"; }
backup_available() { validate_pair "$BACKUP_DEST" "$BACKUP_META"; }

stop_runtime() {
    [ -x "$MAPPING" ] && sh "$MAPPING" stop-all >/dev/null 2>&1 || true
}
resync_firewall() {
    [ -x "$AGENT" ] && sh "$AGENT" sync-firewall >/dev/null 2>&1 || true
}
backup_current() {
    current || return 1
    mkdir -p "$BACKUP_DIR"
    cp "$DEST" "$BACKUP_DEST.new.$$"
    cp "$META" "$BACKUP_META.new.$$"
    chmod 0755 "$BACKUP_DEST.new.$$"
    chmod 0600 "$BACKUP_META.new.$$"
    mv -f "$BACKUP_DEST.new.$$" "$BACKUP_DEST"
    mv -f "$BACKUP_META.new.$$" "$BACKUP_META"
    return 0
}
clear_backup() { rm -rf "$BACKUP_DIR"; }
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
    chmod 0600 "$tmp"
}
restore_backup_internal() {
    backup_available || return 1
    stop_runtime
    mkdir -p "$(dirname "$DEST")"
    cp "$BACKUP_DEST" "${DEST}.rollback.$$"
    cp "$BACKUP_META" "${META}.rollback.$$"
    chmod 0755 "${DEST}.rollback.$$"
    chmod 0600 "${META}.rollback.$$"
    mv -f "${DEST}.rollback.$$" "$DEST"
    mv -f "${META}.rollback.$$" "$META"
    current || return 1
    resync_firewall
}
install_candidate() {
    candidate="$1"; version="$2"; abi="$3"; class="$4"; asset="$5"; ic_sha="$6"; source="$7"; work="$8"
    log="$work/smoke.log"
    smoke_binary "$candidate" "$version" "$log" || { echo "mapper target smoke/self-version failed for ABI $abi" >&2; return 1; }
    had_backup=0
    if backup_current; then had_backup=1; fi
    stop_runtime
    mkdir -p "$(dirname "$DEST")"
    staged="${DEST}.new.$$"
    staged_meta="${META}.new.$$"
    trap 'rm -f "$staged" "$staged_meta"' EXIT INT TERM
    cp "$candidate" "$staged"
    chmod 0755 "$staged"
    write_meta "$staged_meta" "$version" "$abi" "$class" "$asset" "$ic_sha" "$source"
    mv -f "$staged" "$DEST"
    mv -f "$staged_meta" "$META"
    trap - EXIT INT TERM
    if ! current; then
        echo "mapper post-install integrity validation failed" >&2
        [ "$had_backup" -eq 1 ] && restore_backup_internal >/dev/null 2>&1 || true
        return 1
    fi
    resync_firewall
    printf 'Mapper installed: version=%s ABI=%s api=%s source=%s\n' "$version" "$abi" "$MAPPER_API" "$source"
}

quarantine_invalid() {
    [ -e "$DEST" ] || return 0
    current && return 0
    chmod 0644 "$DEST" 2>/dev/null || true
    return 0
}

parse_release_manifest() {
    manifest="$1"; version="$2"; abi="$3"
    grep -Fqx '# schema=1' "$manifest" || { echo "invalid mapper release manifest schema" >&2; return 1; }
    manifest_version="$(sed -n 's/^# version=//p' "$manifest" | sed -n '1p')"
    manifest_tag="$(sed -n 's/^# tag=//p' "$manifest" | sed -n '1p')"
    manifest_api="$(sed -n 's/^# mapper_api=//p' "$manifest" | sed -n '1p')"
    [ "$manifest_version" = "$version" ] && [ "$manifest_tag" = "v$version" ] && [ "$manifest_api" = "$MAPPER_API" ] || {
        echo "mapper release manifest version/API mismatch" >&2
        return 1
    }
    awk -F '\t' -v wanted="$abi" '
        $0 !~ /^#/ && NF == 5 && $1 == wanted {
            if (found) exit 2
            print $2 "|" $3 "|" $4 "|" $5
            found = 1
        }
        END { if (!found) exit 1 }
    ' "$manifest"
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
            echo "custom mapper release base requires explicit opt-in" >&2; return 3;
        }
        command -v curl >/dev/null 2>&1 || { echo "curl unavailable; mapper release install disabled" >&2; return 3; }
        curl -fsSL --connect-timeout 20 "$RELEASE_BASE/v$version/remote-gate-mapper-manifest.tsv" -o "$manifest" || {
            echo "released mapper manifest unavailable for v$version" >&2; return 3;
        }
    fi
    row="$(parse_release_manifest "$manifest" "$version" "$abi")" || { echo "no unique released mapper for Package ABI $abi" >&2; return 3; }
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
        curl -fsSL --connect-timeout 20 "$RELEASE_BASE/v$version/$asset" -o "$candidate" || {
            echo "released mapper asset download failed: $asset" >&2; return 3;
        }
    fi
    actual_sha="$(sha_file "$candidate")" || return 1
    [ "$actual_sha" = "$expected_sha" ] || { echo "mapper SHA-256 mismatch for ABI $abi" >&2; return 1; }
    install_candidate "$candidate" "$version" "$abi" "$class" "$asset" "$actual_sha" released "$work"
    trap - EXIT INT TERM
    rm -rf "$work"
}

install_dev() {
    version="$(read_version)" || { echo "mapper VERSION unavailable" >&2; return 3; }
    abi="$(read_abi)" || { echo "mapper Package ABI unavailable" >&2; return 3; }
    command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum unavailable" >&2; return 3; }
    work="$(mktemp -d "${TMPDIR:-/tmp}/remote-gate-mapper-dev.XXXXXX")"
    trap 'rm -rf "$work"' EXIT INT TERM
    manifest="$work/dev-manifest.tsv"
    if [ -n "$DEV_MANIFEST_OVERRIDE" ]; then
        [ -r "$DEV_MANIFEST_OVERRIDE" ] || { echo "dev mapper manifest override is unreadable" >&2; return 3; }
        cp "$DEV_MANIFEST_OVERRIDE" "$manifest"
    else
        command -v curl >/dev/null 2>&1 || { echo "curl unavailable" >&2; return 3; }
        [ "$DEV_RELEASE_BASE" = "$DEFAULT_DEV_RELEASE_BASE" ] || [ "${REMOTE_GATE_ALLOW_CUSTOM_MAPPER_DEV_RELEASE_BASE:-0}" = 1 ] || {
            echo "custom dev mapper release base requires explicit opt-in" >&2; return 3;
        }
        dev_tag="mapper-dev-v$version"
        curl -fsSL --connect-timeout 20 "$DEV_RELEASE_BASE/$dev_tag/remote-gate-mapper-dev-manifest.tsv" -o "$manifest" || {
            echo "dev mapper manifest unavailable for $dev_tag" >&2; return 3;
        }
    fi
    grep -Fqx '# schema=1' "$manifest" || { echo "invalid dev mapper manifest schema" >&2; return 1; }
    [ "$(sed -n 's/^# version=//p' "$manifest" | sed -n '1p')" = "$version" ] || { echo "dev mapper version mismatch" >&2; return 1; }
    [ "$(sed -n 's/^# mapper_api=//p' "$manifest" | sed -n '1p')" = "$MAPPER_API" ] || { echo "dev mapper API mismatch" >&2; return 1; }
    row="$(awk -F '\t' -v wanted="$abi" '
        $0 !~ /^#/ && NF == 5 && $1 == wanted {
            if (found) exit 2
            print $2 "|" $3 "|" $4 "|" $5
            found=1
        }
        END { if (!found) exit 1 }
    ' "$manifest")" || { echo "no unique dev mapper for Package ABI $abi" >&2; return 3; }
    oldifs="$IFS"; IFS='|'; set -- $row; IFS="$oldifs"
    [ "$#" -eq 4 ] || return 1
    class="$1"; asset="$2"; expected_sha="$3"; status="$4"
    [ "$status" = dev-candidate ] || return 1
    valid_token "$class" && valid_token "$asset" || return 1
    printf '%s\n' "$expected_sha" | grep -Eq '^[0-9a-f]{64}$' || return 1
    downloaded="$work/dev-asset"
    candidate="$work/remote-gate-mapper"
    if [ -n "$DEV_ASSET_DIR_OVERRIDE" ]; then
        [ -r "$DEV_ASSET_DIR_OVERRIDE/$asset" ] || return 3
        cp "$DEV_ASSET_DIR_OVERRIDE/$asset" "$downloaded"
    else
        curl -fsSL --connect-timeout 20 "$DEV_RELEASE_BASE/mapper-dev-v$version/$asset" -o "$downloaded" || { echo "dev mapper asset download failed" >&2; return 3; }
    fi
    case "$asset" in
        *.gz)
            command -v gzip >/dev/null 2>&1 || { echo "gzip is required for the dev mapper asset" >&2; return 3; }
            gzip -dc "$downloaded" > "$candidate" || { echo "dev mapper asset decompression failed" >&2; return 1; }
            ;;
        *) cp "$downloaded" "$candidate" ;;
    esac
    actual_sha="$(sha_file "$candidate")" || return 1
    [ "$actual_sha" = "$expected_sha" ] || { echo "dev mapper SHA-256 mismatch for ABI $abi" >&2; return 1; }
    install_candidate "$candidate" "$version" "$abi" "$class" "$(basename "$asset")" "$actual_sha" dev "$work"
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

preferred_channel_install() {
    source_kind="$(meta_value source)"
    case "$source_kind" in
        dev) install_dev ;;
        local) echo "local mapper cannot be refreshed automatically; use install-local <binary>" >&2; return 3 ;;
        *) install_release ;;
    esac
}
update_mapper() {
    preferred_channel_install
}
repair_mapper() {
    if current; then
        echo "Mapper is already current."
        return 0
    fi
    preferred_channel_install
}
rollback_mapper() {
    backup_available || { echo "no valid mapper rollback backup is available" >&2; return 3; }
    restore_backup_internal || { echo "mapper rollback failed" >&2; return 1; }
    echo "Mapper rollback restored the previous validated binary."
}
uninstall_mapper() {
    stop_runtime
    rm -f "$DEST" "$META"
    clear_backup
    resync_firewall
    echo "Mapper uninstalled. Remote Gate Direct/Gate features remain installed."
}

status_json() {
    if current; then ready=true; else ready=false; fi
    if backup_available; then rollback=true; else rollback=false; fi
    printf '{"ready":%s,"version":"%s","mapper_api":"%s","package_abi":"%s","source":"%s","rollback_available":%s}\n' \
        "$ready" "$(meta_value version)" "$(meta_value mapper_api)" "$(meta_value package_abi)" "$(meta_value source)" "$rollback"
}
status_human() {
    if current; then state=current; else state=unavailable; fi
    if backup_available; then rollback=yes; else rollback=no; fi
    printf 'Mapper status: %s\n' "$state"
    printf 'Version: %s\n' "$(meta_value version)"
    printf 'Package ABI: %s\n' "$(meta_value package_abi)"
    printf 'API: %s\n' "$(meta_value mapper_api)"
    printf 'Source: %s\n' "$(meta_value source)"
    printf 'Rollback available: %s\n' "$rollback"
}

case "${1:-}" in
    install|install-release)
        shift; [ "$#" -eq 0 ] || usage
        set +e; install_release; rc=$?; set -e
        [ "$rc" -eq 0 ] || quarantine_invalid
        exit "$rc"
        ;;
    install-dev)
        shift; [ "$#" -eq 0 ] || usage
        set +e; install_dev; rc=$?; set -e
        [ "$rc" -eq 0 ] || quarantine_invalid
        exit "$rc"
        ;;
    install-local) shift; install_local "$@" ;;
    update) shift; [ "$#" -eq 0 ] || usage; update_mapper ;;
    repair) shift; [ "$#" -eq 0 ] || usage; repair_mapper ;;
    rollback) shift; [ "$#" -eq 0 ] || usage; rollback_mapper ;;
    uninstall) shift; [ "$#" -eq 0 ] || usage; uninstall_mapper ;;
    current) shift; [ "$#" -eq 0 ] || usage; current ;;
    status) shift; [ "$#" -eq 0 ] || usage; status_human ;;
    status-json) shift; [ "$#" -eq 0 ] || usage; status_json ;;
    *) usage ;;
esac
