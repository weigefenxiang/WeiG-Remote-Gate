#!/bin/sh
set -eu
umask 077

STATE_DIR="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}"
STATE_FILE="$STATE_DIR/wireguard-egress.conf"
ROUTE_TABLE="51820"
RULE_BASE="11010"
WG_ZONE_SECTION="remote_gate_wg_egress_zone"
FORWARD_SECTION="remote_gate_wg_egress_forward"
NAT_SECTION="remote_gate_wg_egress_nat"
ROUTE_SECTION="remote_gate_wg_egress_default"
RULE10_SECTION="remote_gate_wg_egress_main10"
RULE100_SECTION="remote_gate_wg_egress_main100"
RULE169_SECTION="remote_gate_wg_egress_main169"
RULE172_SECTION="remote_gate_wg_egress_main172"
RULE192_SECTION="remote_gate_wg_egress_main192"
RULE_DEFAULT_SECTION="remote_gate_wg_egress_default_rule"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

usage() {
    cat <<'USAGE'
Usage:
  remote-gate-wireguard-egress.sh enable <wireguard-interface> <wan-interface>
  remote-gate-wireguard-egress.sh disable
  remote-gate-wireguard-egress.sh status

Example:
  remote-gate-wireguard-egress.sh enable WG_HOME WAN2

This optional helper is separate from Remote Gate INPUT protection. It adds
WG -> WAN forwarding, selective IPv4 masquerading, and source policy routing
so WireGuard clients can use the selected home WAN IPv4 as their Internet exit.
USAGE
}

valid_name() {
    case "$1" in ''|*[!A-Za-z0-9_.-]*) return 1 ;; *) return 0 ;; esac
}

interface_up() {
    ubus call "network.interface.$1" status 2>/dev/null | jsonfilter -e '@.up' 2>/dev/null | grep -qx 'true'
}

l3_device() {
    ubus call "network.interface.$1" status 2>/dev/null | jsonfilter -e '@.l3_device' 2>/dev/null | sed -n '1p'
}

zone_section_for_network() {
    target="$1"
    uci show firewall 2>/dev/null | sed -n 's/^firewall\.\([^=]*\)=zone$/\1/p' | while IFS= read -r section; do
        networks="$(uci -q get "firewall.$section.network" 2>/dev/null || true)"
        for network in $networks; do
            if [ "$network" = "$target" ]; then
                printf '%s\n' "$section"
                exit 0
            fi
        done
    done
}

zone_name() {
    section="$1"
    name="$(uci -q get "firewall.$section.name" 2>/dev/null || true)"
    [ -n "$name" ] && printf '%s\n' "$name" || printf '%s\n' "$section"
}

wireguard_subnet() {
    logical="$1"
    device="$(l3_device "$logical")"
    [ -n "$device" ] || device="$logical"
    ip -4 route show dev "$device" scope link 2>/dev/null | awk '$1 ~ /^[0-9]+(\.[0-9]+){3}\/[0-9]+$/ { print $1; exit }'
}

save_state() {
    mkdir -p "$STATE_DIR"
    cat > "$STATE_FILE" <<EOF_STATE
ENABLED='1'
WG_INTERFACE='$1'
WAN_INTERFACE='$2'
WG_SUBNET='$3'
WG_ZONE_OWNED='$4'
WG_ZONE_NAME='$5'
WAN_ZONE_NAME='$6'
ROUTE_TABLE='$ROUTE_TABLE'
EOF_STATE
    chmod 600 "$STATE_FILE"
}

reload_network() {
    if ubus call network reload >/dev/null 2>&1; then
        :
    elif [ -x /etc/init.d/network ]; then
        /etc/init.d/network reload >/dev/null 2>&1 || true
    fi
}

reload_firewall() {
    [ -x /etc/init.d/firewall ] || return 0
    /etc/init.d/firewall reload >/dev/null 2>&1 || /etc/init.d/firewall restart >/dev/null 2>&1
}

configure_main_lookup_rule() {
    section="$1" dest="$2" priority="$3" wg="$4"
    uci -q delete "network.$section" >/dev/null 2>&1 || true
    uci set "network.$section=rule"
    uci set "network.$section.in=$wg"
    uci set "network.$section.dest=$dest"
    uci set "network.$section.lookup=main"
    uci set "network.$section.priority=$priority"
}

enable_egress() {
    [ "$#" -eq 2 ] || { usage >&2; exit 2; }
    wg="$1" wan="$2"
    valid_name "$wg" || fail "Invalid WireGuard logical interface: $wg"
    valid_name "$wan" || fail "Invalid WAN logical interface: $wan"
    command -v uci >/dev/null 2>&1 || fail "uci is required"
    command -v ubus >/dev/null 2>&1 || fail "ubus is required"
    command -v jsonfilter >/dev/null 2>&1 || fail "jsonfilter is required"
    command -v ip >/dev/null 2>&1 || fail "ip is required"

    [ "$(uci -q get "network.$wg.proto" 2>/dev/null || true)" = wireguard ] || fail "$wg is not a WireGuard interface"
    interface_up "$wg" || fail "$wg is not up"
    interface_up "$wan" || fail "$wan is not up"

    subnet="$(wireguard_subnet "$wg")"
    [ -n "$subnet" ] || fail "Cannot detect the IPv4 subnet of $wg"

    wan_zone_section="$(zone_section_for_network "$wan" | sed -n '1p')"
    [ -n "$wan_zone_section" ] || fail "Cannot find a firewall zone containing WAN interface $wan"
    wan_zone="$(zone_name "$wan_zone_section")"

    wg_zone_section="$(zone_section_for_network "$wg" | sed -n '1p')"
    wg_owned=0
    if [ -n "$wg_zone_section" ]; then
        wg_zone="$(zone_name "$wg_zone_section")"
    else
        wg_owned=1
        wg_zone="remote_gate_wg"
        uci -q delete "firewall.$WG_ZONE_SECTION" >/dev/null 2>&1 || true
        uci set "firewall.$WG_ZONE_SECTION=zone"
        uci set "firewall.$WG_ZONE_SECTION.name=$wg_zone"
        uci add_list "firewall.$WG_ZONE_SECTION.network=$wg"
        uci set "firewall.$WG_ZONE_SECTION.input=ACCEPT"
        uci set "firewall.$WG_ZONE_SECTION.output=ACCEPT"
        uci set "firewall.$WG_ZONE_SECTION.forward=ACCEPT"
    fi

    info "WireGuard: $wg ($subnet)"
    info "Internet exit: $wan via firewall zone $wan_zone"

    uci -q delete "firewall.$FORWARD_SECTION" >/dev/null 2>&1 || true
    uci set "firewall.$FORWARD_SECTION=forwarding"
    uci set "firewall.$FORWARD_SECTION.src=$wg_zone"
    uci set "firewall.$FORWARD_SECTION.dest=$wan_zone"

    uci -q delete "firewall.$NAT_SECTION" >/dev/null 2>&1 || true
    uci set "firewall.$NAT_SECTION=nat"
    uci set "firewall.$NAT_SECTION.name=Remote Gate WireGuard IPv4 egress"
    uci set "firewall.$NAT_SECTION.family=ipv4"
    uci set "firewall.$NAT_SECTION.proto=all"
    uci set "firewall.$NAT_SECTION.src=$wan_zone"
    uci set "firewall.$NAT_SECTION.src_ip=$subnet"
    uci set "firewall.$NAT_SECTION.target=MASQUERADE"

    uci -q delete "network.$ROUTE_SECTION" >/dev/null 2>&1 || true
    uci set "network.$ROUTE_SECTION=route"
    uci set "network.$ROUTE_SECTION.interface=$wan"
    uci set "network.$ROUTE_SECTION.target=0.0.0.0/0"
    uci set "network.$ROUTE_SECTION.table=$ROUTE_TABLE"

    configure_main_lookup_rule "$RULE10_SECTION" 10.0.0.0/8 $((RULE_BASE + 0)) "$wg"
    configure_main_lookup_rule "$RULE100_SECTION" 100.64.0.0/10 $((RULE_BASE + 1)) "$wg"
    configure_main_lookup_rule "$RULE169_SECTION" 169.254.0.0/16 $((RULE_BASE + 2)) "$wg"
    configure_main_lookup_rule "$RULE172_SECTION" 172.16.0.0/12 $((RULE_BASE + 3)) "$wg"
    configure_main_lookup_rule "$RULE192_SECTION" 192.168.0.0/16 $((RULE_BASE + 4)) "$wg"

    uci -q delete "network.$RULE_DEFAULT_SECTION" >/dev/null 2>&1 || true
    uci set "network.$RULE_DEFAULT_SECTION=rule"
    uci set "network.$RULE_DEFAULT_SECTION.in=$wg"
    uci set "network.$RULE_DEFAULT_SECTION.src=$subnet"
    uci set "network.$RULE_DEFAULT_SECTION.dest=0.0.0.0/0"
    uci set "network.$RULE_DEFAULT_SECTION.lookup=$ROUTE_TABLE"
    uci set "network.$RULE_DEFAULT_SECTION.priority=$((RULE_BASE + 10))"

    uci commit firewall
    uci commit network
    save_state "$wg" "$wan" "$subnet" "$wg_owned" "$wg_zone" "$wan_zone"

    reload_network
    sleep 1
    reload_firewall

    printf '\nWireGuard home IPv4 egress enabled.\n'
    printf 'WireGuard subnet: %s\n' "$subnet"
    printf 'Selected WAN: %s\n' "$wan"
    printf 'Routing table: %s\n' "$ROUTE_TABLE"
    printf '\nClient setting for a full IPv4 tunnel:\n'
    printf '  AllowedIPs = 0.0.0.0/0\n'
    printf '\nLAN/private IPv4 ranges continue to use the router main table.\n'
}

disable_egress() {
    wg_owned=0
    if [ -r "$STATE_FILE" ]; then
        . "$STATE_FILE"
        wg_owned="${WG_ZONE_OWNED:-0}"
    fi

    for section in "$FORWARD_SECTION" "$NAT_SECTION"; do
        uci -q delete "firewall.$section" >/dev/null 2>&1 || true
    done
    if [ "$wg_owned" = 1 ]; then
        uci -q delete "firewall.$WG_ZONE_SECTION" >/dev/null 2>&1 || true
    fi
    for section in "$ROUTE_SECTION" "$RULE10_SECTION" "$RULE100_SECTION" "$RULE169_SECTION" "$RULE172_SECTION" "$RULE192_SECTION" "$RULE_DEFAULT_SECTION"; do
        uci -q delete "network.$section" >/dev/null 2>&1 || true
    done
    uci commit firewall
    uci commit network
    rm -f "$STATE_FILE"
    reload_network
    reload_firewall
    printf 'WireGuard home IPv4 egress disabled.\n'
}

status_egress() {
    if [ ! -r "$STATE_FILE" ]; then
        printf 'disabled\n'
        exit 0
    fi
    . "$STATE_FILE"
    printf 'enabled\n'
    printf 'WireGuard: %s\n' "${WG_INTERFACE:-unknown}"
    printf 'Subnet: %s\n' "${WG_SUBNET:-unknown}"
    printf 'WAN: %s\n' "${WAN_INTERFACE:-unknown}"
    printf 'WAN zone: %s\n' "${WAN_ZONE_NAME:-unknown}"
    printf 'Routing table: %s\n' "${ROUTE_TABLE:-51820}"
    printf '\nIPv4 rule:\n'
    ip -4 rule show 2>/dev/null | grep -E '(^|[[:space:]])(1101[0-9]|11020):' || true
    printf '\nTable %s default:\n' "${ROUTE_TABLE:-51820}"
    ip -4 route show table "${ROUTE_TABLE:-51820}" 2>/dev/null | sed -n '1,8p'
}

[ "$(id -u)" -eq 0 ] || fail "Run as root"
case "${1:-}" in
    enable) shift; enable_egress "$@" ;;
    disable) disable_egress ;;
    status) status_egress ;;
    help|--help|-h|'') usage ;;
    *) fail "Unknown action: $1" ;;
esac
