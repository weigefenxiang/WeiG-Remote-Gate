#!/bin/sh
# Keep protected WAN/WireGuard policy and local WireGuard return routing current.
STATE_DIR="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}"
FW_STATE_DIR="$STATE_DIR/firewall"
AUTH_FILE_V4="$FW_STATE_DIR/authorization-ipv4"
AUTH_FILE_V6="$FW_STATE_DIR/authorization-ipv6"
LEGACY_AUTH_FILE="$FW_STATE_DIR/authorization"
VERIFY_ROUTE_FILE_V4="$STATE_DIR/return-route-verify-ipv4"
VERIFY_ROUTE_FILE_V6="$STATE_DIR/return-route-verify-ipv6"
RETURN_STATE_FILE_V4="$STATE_DIR/return-route-ipv4"
RETURN_STATE_FILE_V6="$STATE_DIR/return-route-ipv6"
TAG="remote-gate"

valid_device() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
valid_table() { case "$1" in ''|*[!A-Za-z0-9_.-]*) return 1 ;; *) return 0 ;; esac; }
valid_family() { case "$1" in ipv4|ipv6) return 0 ;; *) return 1 ;; esac; }
valid_ipv4() { printf '%s\n' "$1" | awk -F. 'NF != 4 { exit 1 } { for (i=1;i<=4;i++) if ($i !~ /^[0-9]+$/ || $i<0 || $i>255) exit 1 }'; }
valid_ipv6() { case "$1" in *:*) ;; *) return 1 ;; esac; case "$1" in *[!0-9A-Fa-f:.]*) return 1 ;; esac; }

family_auth_file() { case "$1" in ipv4) printf '%s\n' "$AUTH_FILE_V4" ;; ipv6) printf '%s\n' "$AUTH_FILE_V6" ;; *) return 1 ;; esac; }
family_verify_route_file() { case "$1" in ipv4) printf '%s\n' "$VERIFY_ROUTE_FILE_V4" ;; ipv6) printf '%s\n' "$VERIFY_ROUTE_FILE_V6" ;; *) return 1 ;; esac; }
family_return_state_file() { case "$1" in ipv4) printf '%s\n' "$RETURN_STATE_FILE_V4" ;; ipv6) printf '%s\n' "$RETURN_STATE_FILE_V6" ;; *) return 1 ;; esac; }

migrate_legacy_auth() {
    [ -r "$LEGACY_AUTH_FILE" ] || return 0
    local rg_family rg_target
    rg_family="$(sed -n '5p' "$LEGACY_AUTH_FILE")"; [ -n "$rg_family" ] || rg_family=ipv4
    valid_family "$rg_family" || { rm -f "$LEGACY_AUTH_FILE"; return 0; }
    rg_target="$(family_auth_file "$rg_family")"
    [ -e "$rg_target" ] || cp "$LEGACY_AUTH_FILE" "$rg_target"
    rm -f "$LEGACY_AUTH_FILE"
}

route_dev() { printf '%s\n' "$1" | awk '{ for (i=1;i<=NF;i++) if ($i=="dev") { print $(i+1); exit } }'; }

candidate_tables() {
    local rg_flag="$1" rg_wanted="$2"
    ip "$rg_flag" rule show 2>/dev/null | awk -v dev="$rg_wanted" '{ match_dev=0; table=""; for (i=1;i<=NF;i++) { if ($i=="iif" && $(i+1)==dev) match_dev=1; if ($i=="lookup") table=$(i+1) } if (match_dev && table!="") print table }'
}
choose_priority() {
    local rg_flag="$1" rg_rules rg_priority
    rg_rules="$(ip "$rg_flag" rule show 2>/dev/null || true)"; rg_priority=900
    while [ "$rg_priority" -le 999 ]; do if ! printf '%s\n' "$rg_rules" | grep -Eq "^${rg_priority}:"; then printf '%s\n' "$rg_priority"; return 0; fi; rg_priority=$((rg_priority+1)); done
    return 1
}
choose_owned_table() {
    local rg_flag="$1" rg_table rg_rules rg_routes
    rg_table=51880
    while [ "$rg_table" -le 51979 ]; do
        rg_rules="$(ip "$rg_flag" rule show 2>/dev/null || true)"; rg_routes="$(ip "$rg_flag" route show table "$rg_table" 2>/dev/null || true)"
        if ! printf '%s\n' "$rg_rules" | grep -Eq "lookup ${rg_table}([[:space:]]|$)" && [ -z "$rg_routes" ]; then printf '%s\n' "$rg_table"; return 0; fi
        rg_table=$((rg_table+1))
    done
    return 1
}

clear_return_route_family() {
    local rg_family="$1" rg_state rg_source rg_table rg_priority rg_mode rg_flag rg_target
    rg_state="$(family_return_state_file "$rg_family")"; [ -r "$rg_state" ] || return 0
    rg_source="$(sed -n '2p' "$rg_state")"; rg_table="$(sed -n '5p' "$rg_state")"; rg_priority="$(sed -n '6p' "$rg_state")"; rg_mode="$(sed -n '7p' "$rg_state")"
    case "$rg_family" in ipv4) rg_flag=-4; rg_target="$rg_source/32" ;; ipv6) rg_flag=-6; rg_target="$rg_source/128" ;; esac
    if valid_table "$rg_table" && valid_uint "$rg_priority"; then
        ip "$rg_flag" rule del priority "$rg_priority" iif lo to "$rg_target" lookup "$rg_table" >/dev/null 2>&1 || true
        [ "$rg_mode" != owned ] || ip "$rg_flag" route del table "$rg_table" "$rg_target" >/dev/null 2>&1 || true
    fi
    rm -f "$rg_state"
}
clear_return_routes() { clear_return_route_family ipv4; clear_return_route_family ipv6; }

read_source_file() {
    local rg_file="$1" rg_family="$2" rg_source rg_device rg_port rg_expires rg_file_family rg_now
    [ -r "$rg_file" ] || return 1
    rg_source="$(sed -n '1p' "$rg_file")"; rg_device="$(sed -n '2p' "$rg_file")"; rg_port="$(sed -n '3p' "$rg_file")"; rg_expires="$(sed -n '4p' "$rg_file")"; rg_file_family="$(sed -n '5p' "$rg_file")"
    [ -n "$rg_file_family" ] || rg_file_family="$rg_family"
    rg_now="$(date +%s)"
    [ "$rg_file_family" = "$rg_family" ] && valid_device "$rg_device" && valid_uint "$rg_port" && [ "$rg_port" -ge 1 ] && [ "$rg_port" -le 65535 ] && valid_uint "$rg_expires" && [ "$rg_expires" -gt "$rg_now" ] || return 1
    case "$rg_family" in ipv4) valid_ipv4 "$rg_source" ;; ipv6) valid_ipv6 "$rg_source" ;; esac || return 1
    ip link show "$rg_device" >/dev/null 2>&1 || return 1
    printf '%s %s %s %s\n' "$rg_source" "$rg_device" "$rg_port" "$rg_expires"
}

read_route_source() {
    local rg_family="$1" rg_verify rg_auth rg_record
    migrate_legacy_auth
    rg_verify="$(family_verify_route_file "$rg_family")"; rg_auth="$(family_auth_file "$rg_family")"
    rg_record="$(read_source_file "$rg_verify" "$rg_family" 2>/dev/null || true)"
    if [ -n "$rg_record" ]; then printf '%s verify\n' "$rg_record"; return 0; fi
    [ -e "$rg_verify" ] && rm -f "$rg_verify"
    rg_record="$(read_source_file "$rg_auth" "$rg_family" 2>/dev/null || true)"
    if [ -n "$rg_record" ]; then printf '%s auth\n' "$rg_record"; return 0; fi
    return 1
}

existing_table_for_device() {
    local rg_flag="$1" rg_source="$2" rg_wanted="$3" rg_table rg_route
    for rg_table in $(candidate_tables "$rg_flag" "$rg_wanted"); do
        valid_table "$rg_table" || continue
        rg_route="$(ip "$rg_flag" route get "$rg_source" table "$rg_table" 2>/dev/null | sed -n '1p')"
        [ "$(route_dev "$rg_route")" = "$rg_wanted" ] && { printf '%s\n' "$rg_table"; return 0; }
    done
    return 1
}
install_owned_route() {
    local rg_flag="$1" rg_source="$2" rg_target="$3" rg_wanted="$4" rg_table="$5" rg_route rg_gateway rg_local_src
    rg_route="$(ip "$rg_flag" route get "$rg_source" oif "$rg_wanted" 2>/dev/null | sed -n '1p')"; [ "$(route_dev "$rg_route")" = "$rg_wanted" ] || return 1
    rg_gateway="$(printf '%s\n' "$rg_route" | awk '{ for (i=1;i<=NF;i++) if ($i=="via") { print $(i+1); exit } }')"
    rg_local_src="$(printf '%s\n' "$rg_route" | awk '{ for (i=1;i<=NF;i++) if ($i=="src") { print $(i+1); exit } }')"
    if [ -n "$rg_gateway" ] && [ -n "$rg_local_src" ]; then ip "$rg_flag" route add table "$rg_table" "$rg_target" via "$rg_gateway" dev "$rg_wanted" src "$rg_local_src"
    elif [ -n "$rg_gateway" ]; then ip "$rg_flag" route add table "$rg_table" "$rg_target" via "$rg_gateway" dev "$rg_wanted"
    elif [ -n "$rg_local_src" ]; then ip "$rg_flag" route add table "$rg_table" "$rg_target" dev "$rg_wanted" src "$rg_local_src"
    else ip "$rg_flag" route add table "$rg_table" "$rg_target" dev "$rg_wanted"; fi
}

return_route_sync_family() {
    local rg_family="$1" rg_record rg_source rg_device rg_port rg_expires rg_origin rg_flag rg_target rg_state rg_old_sig rg_old_priority rg_table rg_mode rg_current rg_signature rg_priority
    command -v ip >/dev/null 2>&1 || return 1
    rg_record="$(read_route_source "$rg_family" 2>/dev/null || true)"
    if [ -z "$rg_record" ]; then clear_return_route_family "$rg_family"; return 0; fi
    set -- $rg_record; rg_source="$1"; rg_device="$2"; rg_port="$3"; rg_expires="$4"; rg_origin="$5"
    case "$rg_family" in ipv4) rg_flag=-4; rg_target="$rg_source/32" ;; ipv6) rg_flag=-6; rg_target="$rg_source/128" ;; esac
    rg_state="$(family_return_state_file "$rg_family")"

    rg_table="$(existing_table_for_device "$rg_flag" "$rg_source" "$rg_device" 2>/dev/null || true)"; rg_mode=existing
    if [ -z "$rg_table" ]; then
        rg_current="$(ip "$rg_flag" route get "$rg_source" 2>/dev/null | sed -n '1p')"
        if [ "$(route_dev "$rg_current")" = "$rg_device" ]; then clear_return_route_family "$rg_family"; return 0; fi
        rg_table="$(choose_owned_table "$rg_flag")" || { logger -t "$TAG" "no free routing table for $rg_family local WireGuard return path" 2>/dev/null || true; return 1; }; rg_mode=owned
    fi
    rg_signature="$rg_family|$rg_source|$rg_device|$rg_port|$rg_table|$rg_mode|$rg_origin"
    if [ -r "$rg_state" ]; then
        rg_old_sig="$(sed -n '8p' "$rg_state")"; rg_old_priority="$(sed -n '6p' "$rg_state")"; rg_current="$(ip "$rg_flag" route get "$rg_source" iif lo 2>/dev/null | sed -n '1p')"
        if [ "$rg_old_sig" = "$rg_signature" ] && valid_uint "$rg_old_priority" && [ "$(route_dev "$rg_current")" = "$rg_device" ]; then return 0; fi
        clear_return_route_family "$rg_family"
    fi
    rg_priority="$(choose_priority "$rg_flag")" || return 1; mkdir -p "$STATE_DIR"
    if [ "$rg_mode" = owned ]; then install_owned_route "$rg_flag" "$rg_source" "$rg_target" "$rg_device" "$rg_table" || { logger -t "$TAG" "cannot build $rg_family return route to $rg_source through $rg_device" 2>/dev/null || true; return 1; }; fi
    ip "$rg_flag" rule add priority "$rg_priority" iif lo to "$rg_target" lookup "$rg_table" || { [ "$rg_mode" != owned ] || ip "$rg_flag" route del table "$rg_table" "$rg_target" >/dev/null 2>&1 || true; return 1; }
    { printf '%s\n' "$rg_family"; printf '%s\n' "$rg_source"; printf '%s\n' "$rg_device"; printf '%s\n' "$rg_port"; printf '%s\n' "$rg_table"; printf '%s\n' "$rg_priority"; printf '%s\n' "$rg_mode"; printf '%s\n' "$rg_signature"; } > "$rg_state"
    chmod 600 "$rg_state" 2>/dev/null || true
}
return_route_sync() { return_route_sync_family ipv4; return_route_sync_family ipv6; }

verify_route_set() {
    local rg_family="$1" rg_source="$2" rg_device="$3" rg_port="$4" rg_expires="$5" rg_file
    valid_family "$rg_family" || return 1; case "$rg_family" in ipv4) valid_ipv4 "$rg_source" ;; ipv6) valid_ipv6 "$rg_source" ;; esac || return 1
    valid_device "$rg_device" && valid_uint "$rg_port" && valid_uint "$rg_expires" && [ "$rg_expires" -gt "$(date +%s)" ] || return 1
    rg_file="$(family_verify_route_file "$rg_family")"; mkdir -p "$STATE_DIR"
    { printf '%s\n' "$rg_source"; printf '%s\n' "$rg_device"; printf '%s\n' "$rg_port"; printf '%s\n' "$rg_expires"; printf '%s\n' "$rg_family"; } > "$rg_file"; chmod 600 "$rg_file" 2>/dev/null || true
    return_route_sync_family "$rg_family"
}
verify_route_clear() { local rg_family="$1" rg_file; valid_family "$rg_family" || return 1; rg_file="$(family_verify_route_file "$rg_family")"; rm -f "$rg_file"; return_route_sync_family "$rg_family"; }

case "${1:-}" in
    return-route-sync) return_route_sync; exit $? ;;
    return-route-sync-family) valid_family "${2:-}" || exit 2; return_route_sync_family "$2"; exit $? ;;
    return-route-clear) clear_return_routes; exit 0 ;;
    return-route-verify-set) [ "$#" -eq 6 ] || exit 2; verify_route_set "$2" "$3" "$4" "$5" "$6"; exit $? ;;
    return-route-verify-clear) [ "$#" -eq 2 ] || exit 2; verify_route_clear "$2"; exit $? ;;
    return-route-loop)
        rg_interval="${RETURN_ROUTE_INTERVAL:-2}"; case "$rg_interval" in ''|*[!0-9]*) rg_interval=2 ;; esac; [ "$rg_interval" -ge 1 ] || rg_interval=1
        while :; do return_route_sync || true; sleep "$rg_interval"; done
        ;;
esac

case "${ACTION:-}" in
    ifup|ifupdate|update)
        [ -x /usr/lib/remote-gate/remote-gate-agent.sh ] || exit 0
        ( /usr/lib/remote-gate/remote-gate-agent.sh sync-firewall >/dev/null 2>&1 || true; "$0" return-route-sync >/dev/null 2>&1 || true ) &
        ;;
esac
exit 0
