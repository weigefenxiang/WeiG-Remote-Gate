#!/bin/sh
# Shared post-update backup retention helper.
# Source this file, then call:
#   remote_gate_retain_backups <current-root> [legacy-root]
# Only project timestamp directories (YYYYMMDDTHHMMSSZ) are ever moved/deleted.

remote_gate_backup_warn() {
    printf 'WARN: %s\n' "$*" >&2
}

remote_gate_backup_keep() {
    value="${REMOTE_GATE_BACKUP_KEEP:-2}"
    case "$value" in
        ''|*[!0-9]*) value=2 ;;
    esac
    if [ "$value" -lt 1 ] || [ "$value" -gt 20 ]; then
        value=2
    fi
    printf '%s\n' "$value"
}

remote_gate_backup_name_valid() {
    printf '%s\n' "$1" | grep -Eq '^[0-9]{8}T[0-9]{6}Z$'
}

remote_gate_backup_candidates() {
    root="$1"
    [ -d "$root" ] || return 0
    for path in "$root"/*; do
        [ -d "$path" ] || continue
        name="${path##*/}"
        remote_gate_backup_name_valid "$name" || continue
        printf '%s|%s\n' "$name" "$path"
    done
}

remote_gate_backup_physical_root() {
    root="$1"
    [ -d "$root" ] || return 1
    (
        cd "$root" 2>/dev/null || exit 1
        pwd -P
    )
}

remote_gate_retain_backups() {
    current_root="$1"
    legacy_root="${2:-}"
    keep="$(remote_gate_backup_keep)"
    mkdir -p "$current_root" 2>/dev/null || {
        remote_gate_backup_warn "cannot create backup root: $current_root"
        return 0
    }

    current_physical="$(remote_gate_backup_physical_root "$current_root" 2>/dev/null || true)"
    legacy_physical=""
    if [ -n "$legacy_root" ] && [ -d "$legacy_root" ]; then
        legacy_physical="$(remote_gate_backup_physical_root "$legacy_root" 2>/dev/null || true)"
    fi

    roots_are_same=0
    if [ -n "$current_physical" ] && [ -n "$legacy_physical" ] && [ "$current_physical" = "$legacy_physical" ]; then
        roots_are_same=1
    fi

    tmp="${TMPDIR:-/tmp}/remote-gate-backup-retention.$$"
    : > "$tmp" 2>/dev/null || {
        remote_gate_backup_warn "cannot create retention scratch file"
        return 0
    }

    {
        remote_gate_backup_candidates "$current_root"
        if [ "$roots_are_same" -eq 0 ] && [ -n "$legacy_root" ] && [ "$legacy_root" != "$current_root" ]; then
            remote_gate_backup_candidates "$legacy_root"
        fi
    } | sort -r -t '|' -k1,1 > "$tmp" 2>/dev/null || {
        rm -f "$tmp"
        remote_gate_backup_warn "cannot sort backup candidates"
        return 0
    }

    count=0
    previous_name=""
    while IFS='|' read -r name path; do
        [ -n "$name" ] && [ -n "$path" ] || continue

        # A duplicate timestamp may exist in both current and legacy roots.
        # Prefer the current-root copy and remove only the duplicate project dir.
        if [ "$name" = "$previous_name" ]; then
            if [ "$roots_are_same" -eq 0 ] && [ "$path" != "$current_root/$name" ]; then
                rm -rf "$path" 2>/dev/null || remote_gate_backup_warn "failed to remove duplicate backup: $path"
            fi
            continue
        fi
        previous_name="$name"
        count=$((count + 1))

        if [ "$count" -le "$keep" ]; then
            if [ "$roots_are_same" -eq 0 ] && [ -n "$legacy_root" ] && [ "$path" = "$legacy_root/$name" ] && [ "$legacy_root" != "$current_root" ]; then
                target="$current_root/$name"
                if [ -e "$target" ]; then
                    rm -rf "$path" 2>/dev/null || remote_gate_backup_warn "failed to remove duplicate legacy backup: $path"
                elif ! mv "$path" "$target" 2>/dev/null; then
                    remote_gate_backup_warn "failed to migrate legacy backup: $path"
                fi
            fi
            continue
        fi

        rm -rf "$path" 2>/dev/null || remote_gate_backup_warn "failed to prune old backup: $path"
    done < "$tmp"
    rm -f "$tmp"

    if [ "$roots_are_same" -eq 0 ] && [ -n "$legacy_root" ] && [ "$legacy_root" != "$current_root" ] && [ -d "$legacy_root" ]; then
        rmdir "$legacy_root" 2>/dev/null || true
        legacy_parent="${legacy_root%/*}"
        [ "$legacy_parent" != "$legacy_root" ] && rmdir "$legacy_parent" 2>/dev/null || true
    fi

    return 0
}
