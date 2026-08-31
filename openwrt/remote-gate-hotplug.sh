#!/bin/sh
# Keep protected WAN/WireGuard policy and local WireGuard return routing current.
STATE_DIR="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}"
AUTH_FILE="$STATE_DIR/firewall/authorization"
RETURN_STATE_FILE="$STATE_DIR/return-route"
TAG="remote-gate"

valid_device() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
valid_table() { case "$1" in ''|*[!A-Za-z0-9_.-]*) return 1 ;; *) return 0 ;; esac; }
valid_ipv4() {
    printf '%s\n' "$1" | awk -F. '
        NF != 4 { exit 1 }
        { for (i=1; i<=4; i++) if ($i !~ /^[0-9]+$/ || $i < 0 || $i > 255) exit 1 }
    '
}
valid_ipv6() {
    case "$1" in *:*) ;; *) return 1 ;; esac
    case "$1" in *[!0-9A-Fa-f:.]*) return 1 ;; esac
}

route_dev() {
    printf '%s\n' "$1" | awk '{ for (i=1; i<=NF; i++) if ($i == "dev") { print $(i+1); exit } }'
}

candidate_tables() {
    flag="$1"; wanted="$2"
    ip "$flag" rule show 2>/dev/null | awk -v dev="$wanted" '
        {
            match_dev=0
            table=""
            for (i=1; i<=NF; i++) {
                if ($i == "iif" && $(i+1) == dev) match_dev=1
                if ($i == "lookup") table=$(i+1)
            }
            if (match_dev && table != "") print table
        }
    '
}

choose_priority() {
    flag="$1"
    rules="$(ip "$flag" rule show 2>/dev/null || true)"
    priority=900
    while [ "$priority" -le 999 ]; do
        if ! printf '%s\n' "$rules" | grep -Eq "^${priority}:"; then
            printf '%s\n' "$priority"
            return 0
        fi
        priority=$((priority + 1))
    done
    return 1
}

choose_owned_table() {
    flag="$1"
    table=51880
    while [ "$table" -le 51979 ]; do
        rules="$(ip "$flag" rule show 2>/dev/null || true)"
        routes="$(ip "$flag" route show table "$table" 2>/dev/null || true)"
        if ! printf '%s\n' "$rules" | grep -Eq "lookup ${table}([[:space:]]|$)" && [ -z "$routes" ]; then
            printf '%s\n' "$table"
            return 0
        fi
        table=$((table + 1))
    done
    return 1
}

clear_return_route() {
    [ -r "$RETURN_STATE_FILE" ] || return 0

    family="$(sed -n '1p' "$RETURN_STATE_FILE")"
    source_ip="$(sed -n '2p' "$RETURN_STATE_FILE")"
    table="$(sed -n '5p' "$RETURN_STATE_FILE")"
    priority="$(sed -n '6p' "$RETURN_STATE_FILE")"
    mode="$(sed -n '7p' "$RETURN_STATE_FILE")"

    case "$family" in
        ipv4) flag=-4; target="$source_ip/32" ;;
        ipv6) flag=-6; target="$source_ip/128" ;;
        *) flag=""; target="" ;;
    esac

    if [ -n "$flag" ] && [ -n "$target" ] && valid_table "$table" && valid_uint "$priority"; then
        ip "$flag" rule del priority "$priority" iif lo to "$target" lookup "$table" >/dev/null 2>&1 || true
        if [ "$mode" = "owned" ]; then
            ip "$flag" route del table "$table" "$target" >/dev/null 2>&1 || true
        fi
    fi
    rm -f "$RETURN_STATE_FILE"
}

read_authorization() {
    [ -r "$AUTH_FILE" ] || return 1
    source_ip="$(sed -n '1p' "$AUTH_FILE")"
    device="$(sed -n '2p' "$AUTH_FILE")"
    port="$(sed -n '3p' "$AUTH_FILE")"
    expires="$(sed -n '4p' "$AUTH_FILE")"
    family="$(sed -n '5p' "$AUTH_FILE")"
    [ -n "$family" ] || family=ipv4

    valid_device "$device" || return 1
    valid_uint "$port" || return 1
    [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || return 1
    valid_uint "$expires" || return 1
    [ "$expires" -gt "$(date +%s)" ] || return 1
    case "$family" in
        ipv4) valid_ipv4 "$source_ip" || return 1 ;;
        ipv6) valid_ipv6 "$source_ip" || return 1 ;;
        *) return 1 ;;
    esac
    ip link show "$device" >/dev/null 2>&1 || return 1
    return 0
}

existing_table_for_device() {
    flag="$1"; source="$2"; wanted="$3"
    for table in $(candidate_tables "$flag" "$wanted"); do
        valid_table "$table" || continue
        route="$(ip "$flag" route get "$source" table "$table" 2>/dev/null | sed -n '1p')"
        if [ "$(route_dev "$route")" = "$wanted" ]; then
            printf '%s\n' "$table"
            return 0
        fi
    done
    return 1
}

install_owned_route() {
    flag="$1"; source="$2"; target="$3"; wanted="$4"; table="$5"
    forced_route="$(ip "$flag" route get "$source" oif "$wanted" 2>/dev/null | sed -n '1p')"
    [ "$(route_dev "$forced_route")" = "$wanted" ] || return 1

    gateway="$(printf '%s\n' "$forced_route" | awk '{ for (i=1; i<=NF; i++) if ($i == "via") { print $(i+1); exit } }')"
    local_src="$(printf '%s\n' "$forced_route" | awk '{ for (i=1; i<=NF; i++) if ($i == "src") { print $(i+1); exit } }')"

    if [ -n "$gateway" ] && [ -n "$local_src" ]; then
        ip "$flag" route add table "$table" "$target" via "$gateway" dev "$wanted" src "$local_src"
    elif [ -n "$gateway" ]; then
        ip "$flag" route add table "$table" "$target" via "$gateway" dev "$wanted"
    elif [ -n "$local_src" ]; then
        ip "$flag" route add table "$table" "$target" dev "$wanted" src "$local_src"
    else
        ip "$flag" route add table "$table" "$target" dev "$wanted"
    fi
}

return_route_sync() {
    command -v ip >/dev/null 2>&1 || return 1
    if ! read_authorization; then
        clear_return_route
        return 0
    fi

    case "$family" in
        ipv4) flag=-4; target="$source_ip/32" ;;
        ipv6) flag=-6; target="$source_ip/128" ;;
    esac

    if [ -r "$RETURN_STATE_FILE" ]; then
        old_family="$(sed -n '1p' "$RETURN_STATE_FILE")"
        old_source="$(sed -n '2p' "$RETURN_STATE_FILE")"
        old_device="$(sed -n '3p' "$RETURN_STATE_FILE")"
        old_port="$(sed -n '4p' "$RETURN_STATE_FILE")"
        if [ "$old_family|$old_source|$old_device|$old_port" != "$family|$source_ip|$device|$port" ]; then
            clear_return_route
        fi
    fi

    table="$(existing_table_for_device "$flag" "$source_ip" "$device" 2>/dev/null || true)"
    mode=existing
    if [ -z "$table" ]; then
        current_route="$(ip "$flag" route get "$source_ip" 2>/dev/null | sed -n '1p')"
        if [ "$(route_dev "$current_route")" = "$device" ]; then
            clear_return_route
            return 0
        fi
        table="$(choose_owned_table "$flag")" || {
            logger -t "$TAG" "no free routing table for local WireGuard return path" 2>/dev/null || true
            return 1
        }
        mode=owned
    fi

    signature="$family|$source_ip|$device|$port|$table|$mode"
    if [ -r "$RETURN_STATE_FILE" ]; then
        old_signature="$(sed -n '8p' "$RETURN_STATE_FILE")"
        old_priority="$(sed -n '6p' "$RETURN_STATE_FILE")"
        current_route="$(ip "$flag" route get "$source_ip" iif lo 2>/dev/null | sed -n '1p')"
        if [ "$old_signature" = "$signature" ] && valid_uint "$old_priority" && [ "$(route_dev "$current_route")" = "$device" ]; then
            return 0
        fi
        clear_return_route
    fi

    priority="$(choose_priority "$flag")" || {
        logger -t "$TAG" "no free rule priority for local WireGuard return path" 2>/dev/null || true
        return 1
    }
    mkdir -p "$STATE_DIR"

    if [ "$mode" = "owned" ]; then
        install_owned_route "$flag" "$source_ip" "$target" "$device" "$table" || {
            logger -t "$TAG" "cannot build local return route to $source_ip through $device" 2>/dev/null || true
            return 1
        }
    fi

    ip "$flag" rule add priority "$priority" iif lo to "$target" lookup "$table" || {
        [ "$mode" = "owned" ] && ip "$flag" route del table "$table" "$target" >/dev/null 2>&1 || true
        return 1
    }

    {
        printf '%s\n' "$family"
        printf '%s\n' "$source_ip"
        printf '%s\n' "$device"
        printf '%s\n' "$port"
        printf '%s\n' "$table"
        printf '%s\n' "$priority"
        printf '%s\n' "$mode"
        printf '%s\n' "$signature"
    } > "$RETURN_STATE_FILE"
    chmod 600 "$RETURN_STATE_FILE" 2>/dev/null || true
    logger -t "$TAG" "local WireGuard return route pinned to $device for $source_ip (UDP/$port)" 2>/dev/null || true
}

case "${1:-}" in
    return-route-sync)
        return_route_sync
        exit $?
        ;;
    return-route-clear)
        clear_return_route
        exit 0
        ;;
    return-route-loop)
        interval="${RETURN_ROUTE_INTERVAL:-2}"
        case "$interval" in ''|*[!0-9]*) interval=2 ;; esac
        [ "$interval" -ge 1 ] || interval=1
        while :; do
            return_route_sync || true
            sleep "$interval"
        done
        ;;
esac

# Keep the protected public-WAN/WireGuard policy current on interface changes.
case "${ACTION:-}" in
    ifup|ifupdate|update)
        [ -x /usr/lib/remote-gate/remote-gate-agent.sh ] || exit 0
        (
            /usr/lib/remote-gate/remote-gate-agent.sh sync-firewall >/dev/null 2>&1 || true
            "$0" return-route-sync >/dev/null 2>&1 || true
        ) &
        ;;
esac
exit 0
