#!/bin/sh
# Keep protected WAN/WireGuard policy and local WireGuard return routing current.
STATE_DIR="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}"
FW_STATE_DIR="$STATE_DIR/firewall"
AUTH_FILE_V4="$FW_STATE_DIR/authorization-ipv4"
AUTH_FILE_V6="$FW_STATE_DIR/authorization-ipv6"
AUTH_DIR_V4="$FW_STATE_DIR/authorization-ipv4.d"
AUTH_DIR_V6="$FW_STATE_DIR/authorization-ipv6.d"
LEGACY_AUTH_FILE="$FW_STATE_DIR/authorization"
VERIFY_ROUTE_FILE_V4="$STATE_DIR/return-route-verify-ipv4"
VERIFY_ROUTE_FILE_V6="$STATE_DIR/return-route-verify-ipv6"
LEGACY_RETURN_STATE_FILE_V4="$STATE_DIR/return-route-ipv4"
LEGACY_RETURN_STATE_FILE_V6="$STATE_DIR/return-route-ipv6"
RETURN_STATE_DIR_V4="$STATE_DIR/return-route-ipv4.d"
RETURN_STATE_DIR_V6="$STATE_DIR/return-route-ipv6.d"
TAG="remote-gate"

valid_device() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
valid_table() { case "$1" in ''|*[!A-Za-z0-9_.-]*) return 1 ;; *) return 0 ;; esac; }
valid_family() { case "$1" in ipv4|ipv6) return 0 ;; *) return 1 ;; esac; }
valid_ipv4() { printf '%s\n' "$1" | awk -F. 'NF != 4 { exit 1 } { for (i=1;i<=4;i++) if ($i !~ /^[0-9]+$/ || $i<0 || $i>255) exit 1 }'; }
valid_ipv6() { case "$1" in *:*) ;; *) return 1 ;; esac; case "$1" in *[!0-9A-Fa-f:.]*) return 1 ;; esac; }

family_auth_file() { case "$1" in ipv4) printf '%s\n' "$AUTH_FILE_V4" ;; ipv6) printf '%s\n' "$AUTH_FILE_V6" ;; *) return 1 ;; esac; }
family_auth_dir() { case "$1" in ipv4) printf '%s\n' "$AUTH_DIR_V4" ;; ipv6) printf '%s\n' "$AUTH_DIR_V6" ;; *) return 1 ;; esac; }
family_verify_route_file() { case "$1" in ipv4) printf '%s\n' "$VERIFY_ROUTE_FILE_V4" ;; ipv6) printf '%s\n' "$VERIFY_ROUTE_FILE_V6" ;; *) return 1 ;; esac; }
family_return_state_dir() { case "$1" in ipv4) printf '%s\n' "$RETURN_STATE_DIR_V4" ;; ipv6) printf '%s\n' "$RETURN_STATE_DIR_V6" ;; *) return 1 ;; esac; }
family_legacy_return_state_file() { case "$1" in ipv4) printf '%s\n' "$LEGACY_RETURN_STATE_FILE_V4" ;; ipv6) printf '%s\n' "$LEGACY_RETURN_STATE_FILE_V6" ;; *) return 1 ;; esac; }
route_state_key() { printf '%s' "$1" | sed 's/[^A-Za-z0-9_.-]/_/g'; }
return_state_file_for_source() { local rg_dir rg_key; rg_dir="$(family_return_state_dir "$1")" || return 1; rg_key="$(route_state_key "$2")"; [ -n "$rg_key" ] || return 1; printf '%s/%s\n' "$rg_dir" "$rg_key"; }

migrate_legacy_auth() {
    if [ -r "$LEGACY_AUTH_FILE" ]; then
        local rg_family rg_target
        rg_family="$(sed -n '5p' "$LEGACY_AUTH_FILE")"; [ -n "$rg_family" ] || rg_family=ipv4
        if valid_family "$rg_family"; then rg_target="$(family_auth_file "$rg_family")"; [ -e "$rg_target" ] || cp "$LEGACY_AUTH_FILE" "$rg_target"; fi
        rm -f "$LEGACY_AUTH_FILE"
    fi
    local rg_family rg_file rg_dir rg_source rg_target
    for rg_family in ipv4 ipv6; do
        rg_file="$(family_auth_file "$rg_family")"; rg_dir="$(family_auth_dir "$rg_family")"; mkdir -p "$rg_dir"
        [ -r "$rg_file" ] || continue
        rg_source="$(sed -n '1p' "$rg_file")"
        case "$rg_family" in ipv4) valid_ipv4 "$rg_source" ;; ipv6) valid_ipv6 "$rg_source" ;; esac || { rm -f "$rg_file"; continue; }
        rg_target="$rg_dir/$(route_state_key "$rg_source")"; [ -e "$rg_target" ] || cp "$rg_file" "$rg_target"; rm -f "$rg_file"; chmod 600 "$rg_target" 2>/dev/null || true
    done
}

migrate_legacy_return_state() {
    local rg_family rg_old rg_source rg_target
    for rg_family in ipv4 ipv6; do
        rg_old="$(family_legacy_return_state_file "$rg_family")"; [ -r "$rg_old" ] || continue
        rg_source="$(sed -n '2p' "$rg_old")"
        if [ -n "$rg_source" ]; then rg_target="$(return_state_file_for_source "$rg_family" "$rg_source")"; mkdir -p "$(family_return_state_dir "$rg_family")"; [ -e "$rg_target" ] || mv "$rg_old" "$rg_target"; fi
        [ -e "$rg_old" ] && rm -f "$rg_old"
    done
}

ensure_route_state() {
    mkdir -p "$STATE_DIR" "$RETURN_STATE_DIR_V4" "$RETURN_STATE_DIR_V6" "$AUTH_DIR_V4" "$AUTH_DIR_V6"
    chmod 700 "$RETURN_STATE_DIR_V4" "$RETURN_STATE_DIR_V6" "$AUTH_DIR_V4" "$AUTH_DIR_V6" 2>/dev/null || true
    migrate_legacy_auth
    migrate_legacy_return_state
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

clear_return_route_state_file() {
    local rg_family="$1" rg_state="$2" rg_source rg_table rg_priority rg_mode rg_flag rg_target
    [ -r "$rg_state" ] || return 0
    rg_source="$(sed -n '2p' "$rg_state")"; rg_table="$(sed -n '5p' "$rg_state")"; rg_priority="$(sed -n '6p' "$rg_state")"; rg_mode="$(sed -n '7p' "$rg_state")"
    case "$rg_family" in ipv4) rg_flag=-4; rg_target="$rg_source/32" ;; ipv6) rg_flag=-6; rg_target="$rg_source/128" ;; esac
    if valid_table "$rg_table" && valid_uint "$rg_priority"; then
        ip "$rg_flag" rule del priority "$rg_priority" iif lo to "$rg_target" lookup "$rg_table" >/dev/null 2>&1 || true
        [ "$rg_mode" != owned ] || ip "$rg_flag" route del table "$rg_table" "$rg_target" >/dev/null 2>&1 || true
    fi
    rm -f "$rg_state"
}
clear_return_route_source() { local rg_family="$1" rg_source="$2" rg_state; rg_state="$(return_state_file_for_source "$rg_family" "$rg_source")" || return 0; clear_return_route_state_file "$rg_family" "$rg_state"; }
clear_return_route_family() {
    local rg_family="$1" rg_dir rg_state rg_old
    ensure_route_state
    rg_dir="$(family_return_state_dir "$rg_family")"
    for rg_state in "$rg_dir"/*; do [ -f "$rg_state" ] || continue; clear_return_route_state_file "$rg_family" "$rg_state"; done
    rg_old="$(family_legacy_return_state_file "$rg_family")"; [ -e "$rg_old" ] && clear_return_route_state_file "$rg_family" "$rg_old"
}
clear_return_routes() { clear_return_route_family ipv4; clear_return_route_family ipv6; }

read_source_file() {
    local rg_file="$1" rg_family="$2" rg_source rg_device rg_port rg_expires rg_file_family rg_now
    [ -r "$rg_file" ] || return 1
    rg_source="$(sed -n '1p' "$rg_file")"; rg_device="$(sed -n '2p' "$rg_file")"; rg_port="$(sed -n '3p' "$rg_file")"; rg_expires="$(sed -n '4p' "$rg_file")"; rg_file_family="$(sed -n '5p' "$rg_file")"
    [ -n "$rg_file_family" ] || rg_file_family="$rg_family"; rg_now="$(date +%s)"
    [ "$rg_file_family" = "$rg_family" ] && valid_device "$rg_device" && valid_uint "$rg_port" && [ "$rg_port" -ge 1 ] && [ "$rg_port" -le 65535 ] && valid_uint "$rg_expires" && [ "$rg_expires" -gt "$rg_now" ] || return 1
    case "$rg_family" in ipv4) valid_ipv4 "$rg_source" ;; ipv6) valid_ipv6 "$rg_source" ;; esac || return 1
    ip link show "$rg_device" >/dev/null 2>&1 || return 1
    printf '%s %s %s %s\n' "$rg_source" "$rg_device" "$rg_port" "$rg_expires"
}

read_route_sources() {
    local rg_family="$1" rg_verify rg_auth_dir rg_file rg_record
    ensure_route_state
    rg_verify="$(family_verify_route_file "$rg_family")"; rg_auth_dir="$(family_auth_dir "$rg_family")"
    rg_record="$(read_source_file "$rg_verify" "$rg_family" 2>/dev/null || true)"
    if [ -n "$rg_record" ]; then printf '%s verify\n' "$rg_record"; elif [ -e "$rg_verify" ]; then rm -f "$rg_verify"; fi
    for rg_file in "$rg_auth_dir"/*; do
        [ -f "$rg_file" ] || continue
        rg_record="$(read_source_file "$rg_file" "$rg_family" 2>/dev/null || true)"
        [ -n "$rg_record" ] && printf '%s auth\n' "$rg_record"
    done
}

table_default_device() { local rg_flag="$1" rg_table="$2"; ip "$rg_flag" route show table "$rg_table" 2>/dev/null | awk '$1=="default" { for (i=1;i<=NF;i++) if ($i=="dev") { print $(i+1); exit } }'; }
existing_table_for_device() {
    local rg_flag="$1" rg_wanted="$2" rg_table
    for rg_table in $(candidate_tables "$rg_flag" "$rg_wanted"); do valid_table "$rg_table" || continue; [ "$(table_default_device "$rg_flag" "$rg_table")" = "$rg_wanted" ] && { printf '%s\n' "$rg_table"; return 0; }; done
    return 1
}

device_global_ipv6_sources() { local rg_wanted="$1"; ip -6 addr show dev "$rg_wanted" scope global 2>/dev/null | awk '/inet6 / { sub(/\/.*/, "", $2); print $2 }'; }
route_lookup_for_device() {
    local rg_flag="$1" rg_source="$2" rg_wanted="$3" rg_route rg_local_src
    if [ "$rg_flag" = -6 ]; then
        for rg_local_src in $(device_global_ipv6_sources "$rg_wanted"); do rg_route="$(ip -6 route get "$rg_source" from "$rg_local_src" oif "$rg_wanted" 2>/dev/null | sed -n '1p')"; [ "$(route_dev "$rg_route")" = "$rg_wanted" ] && { printf '%s\n' "$rg_route"; return 0; }; done
        return 1
    fi
    rg_route="$(ip -4 route get "$rg_source" oif "$rg_wanted" 2>/dev/null | sed -n '1p')"; [ "$(route_dev "$rg_route")" = "$rg_wanted" ] || return 1; printf '%s\n' "$rg_route"
}
install_owned_route() {
    local rg_flag="$1" rg_source="$2" rg_target="$3" rg_wanted="$4" rg_table="$5" rg_route rg_gateway rg_local_src
    rg_route="$(route_lookup_for_device "$rg_flag" "$rg_source" "$rg_wanted" 2>/dev/null || true)"; [ "$(route_dev "$rg_route")" = "$rg_wanted" ] || return 1
    rg_gateway="$(printf '%s\n' "$rg_route" | awk '{ for (i=1;i<=NF;i++) if ($i=="via") { print $(i+1); exit } }')"; rg_local_src="$(printf '%s\n' "$rg_route" | awk '{ for (i=1;i<=NF;i++) if ($i=="src") { print $(i+1); exit } }')"
    if [ -n "$rg_gateway" ] && [ -n "$rg_local_src" ]; then ip "$rg_flag" route add table "$rg_table" "$rg_target" via "$rg_gateway" dev "$rg_wanted" src "$rg_local_src"
    elif [ -n "$rg_gateway" ]; then ip "$rg_flag" route add table "$rg_table" "$rg_target" via "$rg_gateway" dev "$rg_wanted"
    elif [ -n "$rg_local_src" ]; then ip "$rg_flag" route add table "$rg_table" "$rg_target" dev "$rg_wanted" src "$rg_local_src"
    else ip "$rg_flag" route add table "$rg_table" "$rg_target" dev "$rg_wanted"; fi
}

state_route_valid() {
    local rg_flag="$1" rg_target="$2" rg_wanted="$3" rg_table="$4" rg_priority="$5" rg_mode="$6" rg_rules rg_routes
    rg_rules="$(ip "$rg_flag" rule show 2>/dev/null || true)"; printf '%s\n' "$rg_rules" | grep -Eq "^${rg_priority}:.*iif lo.*to ${rg_target}.*lookup ${rg_table}([[:space:]]|$)" || return 1
    if [ "$rg_mode" = existing ]; then [ "$(table_default_device "$rg_flag" "$rg_table")" = "$rg_wanted" ]; return $?; fi
    rg_routes="$(ip "$rg_flag" route show table "$rg_table" "$rg_target" 2>/dev/null || true)"; [ "$(route_dev "$rg_routes")" = "$rg_wanted" ]
}

sync_return_route_record() {
    local rg_family="$1" rg_source="$2" rg_device="$3" rg_port="$4" rg_expires="$5" rg_origin="$6" rg_flag rg_target rg_state rg_old_sig rg_old_priority rg_table rg_mode rg_current rg_signature rg_priority
    case "$rg_family" in ipv4) rg_flag=-4; rg_target="$rg_source/32" ;; ipv6) rg_flag=-6; rg_target="$rg_source/128" ;; esac
    rg_state="$(return_state_file_for_source "$rg_family" "$rg_source")"
    rg_table="$(existing_table_for_device "$rg_flag" "$rg_device" 2>/dev/null || true)"; rg_mode=existing
    if [ -z "$rg_table" ]; then
        if [ "$rg_family" = ipv4 ]; then rg_current="$(ip -4 route get "$rg_source" 2>/dev/null | sed -n '1p')"; if [ "$(route_dev "$rg_current")" = "$rg_device" ]; then clear_return_route_state_file "$rg_family" "$rg_state"; return 0; fi; fi
        rg_table="$(choose_owned_table "$rg_flag")" || { logger -t "$TAG" "no free routing table for $rg_family local WireGuard return path" 2>/dev/null || true; return 1; }; rg_mode=owned
    fi
    rg_signature="$rg_family|$rg_source|$rg_device|$rg_port|$rg_table|$rg_mode|$rg_origin"
    if [ -r "$rg_state" ]; then
        rg_old_sig="$(sed -n '8p' "$rg_state")"; rg_old_priority="$(sed -n '6p' "$rg_state")"
        if [ "$rg_old_sig" = "$rg_signature" ] && valid_uint "$rg_old_priority" && state_route_valid "$rg_flag" "$rg_target" "$rg_device" "$rg_table" "$rg_old_priority" "$rg_mode"; then return 0; fi
        clear_return_route_state_file "$rg_family" "$rg_state"
    fi
    rg_priority="$(choose_priority "$rg_flag")" || return 1
    if [ "$rg_mode" = owned ]; then install_owned_route "$rg_flag" "$rg_source" "$rg_target" "$rg_device" "$rg_table" || { logger -t "$TAG" "cannot build $rg_family return route to $rg_source through $rg_device" 2>/dev/null || true; return 1; }; fi
    ip "$rg_flag" rule add priority "$rg_priority" iif lo to "$rg_target" lookup "$rg_table" || { [ "$rg_mode" != owned ] || ip "$rg_flag" route del table "$rg_table" "$rg_target" >/dev/null 2>&1 || true; return 1; }
    { printf '%s\n' "$rg_family"; printf '%s\n' "$rg_source"; printf '%s\n' "$rg_device"; printf '%s\n' "$rg_port"; printf '%s\n' "$rg_table"; printf '%s\n' "$rg_priority"; printf '%s\n' "$rg_mode"; printf '%s\n' "$rg_signature"; } > "$rg_state"; chmod 600 "$rg_state" 2>/dev/null || true
}

return_route_sync_family() {
    local rg_family="$1" rg_records rg_record rg_source rg_device rg_port rg_expires rg_origin rg_active rg_state rg_state_source rg_dir rg_key
    command -v ip >/dev/null 2>&1 || return 1
    ensure_route_state; rg_active="/tmp/remote-gate-return-active.$$.$rg_family"; : > "$rg_active"
    rg_records="$(read_route_sources "$rg_family" 2>/dev/null | awk '!seen[$1]++')"
    if [ -n "$rg_records" ]; then
        while IFS= read -r rg_record; do
            [ -n "$rg_record" ] || continue; set -- $rg_record; rg_source="$1"; rg_device="$2"; rg_port="$3"; rg_expires="$4"; rg_origin="$5"
            rg_key="$(route_state_key "$rg_source")"; printf '%s\n' "$rg_key" >> "$rg_active"
            sync_return_route_record "$rg_family" "$rg_source" "$rg_device" "$rg_port" "$rg_expires" "$rg_origin" || true
        done <<EOF2
$rg_records
EOF2
    fi
    rg_dir="$(family_return_state_dir "$rg_family")"
    for rg_state in "$rg_dir"/*; do
        [ -f "$rg_state" ] || continue; rg_key="$(basename "$rg_state")"
        grep -Fqx "$rg_key" "$rg_active" 2>/dev/null || clear_return_route_state_file "$rg_family" "$rg_state"
    done
    rm -f "$rg_active"
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
    ifup|ifupdate|update|ifdown)
        [ -x /usr/lib/remote-gate/remote-gate-agent.sh ] || exit 0
        ( /usr/lib/remote-gate/remote-gate-agent.sh sync-firewall >/dev/null 2>&1 || true; "$0" return-route-sync >/dev/null 2>&1 || true ) &
        ;;
esac
exit 0
