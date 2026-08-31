#!/bin/sh
set -eu
umask 077

RUNTIME_DIR="${REMOTE_GATE_RUNTIME_DIR:-/tmp/remote-gate}"
STATE_FILE="$RUNTIME_DIR/wireguard-egress.conf"
LEGACY_STATE_FILE="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}/wireguard-egress.conf"
FIREWALL="/usr/lib/remote-gate/remote-gate-firewall.sh"
FW3_FILTER_CHAIN="WEIG_WG_EGRESS"
FW3_NAT_CHAIN="WEIG_WG_EGRESS_NAT"
NFT_COMMENT="WeiG Remote Gate WG egress"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

usage() {
    cat <<'USAGE'
Usage:
  remote-gate-wireguard-egress.sh enable <wireguard-interface> <wan-interface> [ttl-seconds]
  remote-gate-wireguard-egress.sh disable
  remote-gate-wireguard-egress.sh sync
  remote-gate-wireguard-egress.sh status
  remote-gate-wireguard-egress.sh cleanup-legacy

Example:
  remote-gate-wireguard-egress.sh enable WG_HOME WAN2 300

This helper creates runtime-only IPv4 forwarding, masquerading and policy
routing. It never commits new network/firewall UCI sections. Runtime state is
kept under /tmp, so a reboot always returns Internet egress to OFF.
USAGE
}

valid_name() { case "$1" in ''|*[!A-Za-z0-9_.-]*) return 1 ;; *) return 0 ;; esac; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }

interface_status() {
    ubus call "network.interface.$1" status 2>/dev/null
}

interface_up() {
    interface_status "$1" | jsonfilter -e '@.up' 2>/dev/null | grep -qx 'true'
}

l3_device() {
    interface_status "$1" | jsonfilter -e '@.l3_device' 2>/dev/null | sed -n '1p'
}

wireguard_subnet() {
    logical="$1"
    device="$(l3_device "$logical")"
    [ -n "$device" ] || device="$logical"
    ip -4 route show dev "$device" scope link 2>/dev/null |
        awk '$1 ~ /^[0-9]+(\.[0-9]+){3}\/[0-9]+$/ { print $1; exit }'
}

detect_backend() {
    [ -x "$FIREWALL" ] || fail "Missing $FIREWALL"
    "$FIREWALL" detect 2>/dev/null || fail "Unsupported firewall backend"
}

cleanup_legacy_uci() {
    changed=0
    for section in \
        remote_gate_wg_egress_zone \
        remote_gate_wg_egress_forward \
        remote_gate_wg_egress_nat
    do
        if uci -q get "firewall.$section" >/dev/null 2>&1; then
            uci -q delete "firewall.$section" >/dev/null 2>&1 || true
            changed=1
        fi
    done
    for section in \
        remote_gate_wg_egress_default \
        remote_gate_wg_egress_main10 \
        remote_gate_wg_egress_main100 \
        remote_gate_wg_egress_main169 \
        remote_gate_wg_egress_main172 \
        remote_gate_wg_egress_main192 \
        remote_gate_wg_egress_default_rule
    do
        if uci -q get "network.$section" >/dev/null 2>&1; then
            uci -q delete "network.$section" >/dev/null 2>&1 || true
            changed=1
        fi
    done
    rm -f "$LEGACY_STATE_FILE"
    if [ "$changed" -eq 1 ]; then
        uci commit firewall
        uci commit network
        ubus call network reload >/dev/null 2>&1 || true
        [ -x /etc/init.d/firewall ] && /etc/init.d/firewall reload >/dev/null 2>&1 || true
        printf 'Legacy persistent WireGuard egress UCI sections removed.\n'
    fi
}

fw3_cleanup() {
    command -v iptables >/dev/null 2>&1 || return 0
    while iptables -C FORWARD -j "$FW3_FILTER_CHAIN" >/dev/null 2>&1; do
        iptables -D FORWARD -j "$FW3_FILTER_CHAIN" >/dev/null 2>&1 || break
    done
    iptables -F "$FW3_FILTER_CHAIN" >/dev/null 2>&1 || true
    iptables -X "$FW3_FILTER_CHAIN" >/dev/null 2>&1 || true

    while iptables -t nat -C POSTROUTING -j "$FW3_NAT_CHAIN" >/dev/null 2>&1; do
        iptables -t nat -D POSTROUTING -j "$FW3_NAT_CHAIN" >/dev/null 2>&1 || break
    done
    iptables -t nat -F "$FW3_NAT_CHAIN" >/dev/null 2>&1 || true
    iptables -t nat -X "$FW3_NAT_CHAIN" >/dev/null 2>&1 || true
}

fw3_install() {
    wg_dev="$1"; wan_dev="$2"; subnet="$3"
    fw3_cleanup
    iptables -N "$FW3_FILTER_CHAIN"
    iptables -A "$FW3_FILTER_CHAIN" -i "$wg_dev" -o "$wan_dev" -s "$subnet" -j ACCEPT
    iptables -A "$FW3_FILTER_CHAIN" -i "$wan_dev" -o "$wg_dev" -d "$subnet" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    iptables -I FORWARD 1 -j "$FW3_FILTER_CHAIN"

    iptables -t nat -N "$FW3_NAT_CHAIN"
    iptables -t nat -A "$FW3_NAT_CHAIN" -s "$subnet" -o "$wan_dev" -j MASQUERADE
    iptables -t nat -I POSTROUTING 1 -j "$FW3_NAT_CHAIN"
}

nft_delete_comment_rules() {
    chain="$1"
    nft -a list chain inet fw4 "$chain" 2>/dev/null |
        awk -v marker="$NFT_COMMENT" '
            index($0, marker) {
                for (i=1; i<=NF; i++) if ($i=="handle") print $(i+1)
            }' |
        while IFS= read -r handle; do
            case "$handle" in ''|*[!0-9]*) continue ;; esac
            nft delete rule inet fw4 "$chain" handle "$handle" >/dev/null 2>&1 || true
        done
}

fw4_cleanup() {
    command -v nft >/dev/null 2>&1 || return 0
    nft_delete_comment_rules forward
    nft_delete_comment_rules srcnat
}

fw4_install() {
    wg_dev="$1"; wan_dev="$2"; subnet="$3"
    nft list chain inet fw4 forward >/dev/null 2>&1 || fail "fw4 forward chain unavailable"
    nft list chain inet fw4 srcnat >/dev/null 2>&1 || fail "fw4 srcnat chain unavailable"
    fw4_cleanup
    nft insert rule inet fw4 forward iifname "$wg_dev" oifname "$wan_dev" ip saddr "$subnet" counter accept comment "$NFT_COMMENT outbound"
    nft insert rule inet fw4 forward iifname "$wan_dev" oifname "$wg_dev" ip daddr "$subnet" ct state established,related counter accept comment "$NFT_COMMENT return"
    nft insert rule inet fw4 srcnat oifname "$wan_dev" ip saddr "$subnet" counter masquerade comment "$NFT_COMMENT nat"
}

priority_used() {
    priority="$1"
    ip -4 rule show 2>/dev/null | grep -Eq "^${priority}:"
}

choose_rule_base() {
    base=80
    while [ "$base" -le 380 ]; do
        ok=1
        for offset in 0 1 2 3 4 10; do
            priority="$((base + offset))"
            if priority_used "$priority"; then ok=0; break; fi
        done
        [ "$ok" -eq 1 ] && { printf '%s\n' "$base"; return 0; }
        base="$((base + 20))"
    done
    return 1
}

table_in_use() {
    table="$1"
    ip -4 rule show 2>/dev/null | grep -Eq "lookup ${table}([[:space:]]|$)" && return 0
    [ -n "$(ip -4 route show table "$table" 2>/dev/null || true)" ]
}

choose_route_table() {
    table=51820
    while [ "$table" -le 51879 ]; do
        table_in_use "$table" || { printf '%s\n' "$table"; return 0; }
        table="$((table + 1))"
    done
    return 1
}

install_route_table() {
    wan_dev="$1"; table="$2"
    route="$(ip -4 route show default dev "$wan_dev" 2>/dev/null | sed -n '1p')"
    [ -n "$route" ] || fail "No IPv4 default route found on $wan_dev"
    args="${route#default }"
    # shellcheck disable=SC2086
    ip -4 route replace table "$table" default $args
}

install_rules() {
    wg_dev="$1"; subnet="$2"; table="$3"; base="$4"
    ip -4 rule add priority "$((base + 0))" iif "$wg_dev" to 10.0.0.0/8 lookup main
    ip -4 rule add priority "$((base + 1))" iif "$wg_dev" to 100.64.0.0/10 lookup main
    ip -4 rule add priority "$((base + 2))" iif "$wg_dev" to 169.254.0.0/16 lookup main
    ip -4 rule add priority "$((base + 3))" iif "$wg_dev" to 172.16.0.0/12 lookup main
    ip -4 rule add priority "$((base + 4))" iif "$wg_dev" to 192.168.0.0/16 lookup main
    ip -4 rule add priority "$((base + 10))" from "$subnet" iif "$wg_dev" lookup "$table"
    ip -4 route flush cache >/dev/null 2>&1 || true
}

remove_rules_from_state() {
    [ -r "$STATE_FILE" ] || return 0
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    base="${RULE_BASE:-}"
    table="${ROUTE_TABLE:-}"
    wg="${WG_DEVICE:-}"
    subnet="${WG_SUBNET:-}"
    if valid_uint "$base" && valid_uint "$table" && [ -n "$wg" ] && [ -n "$subnet" ]; then
        ip -4 rule del priority "$((base + 0))" iif "$wg" to 10.0.0.0/8 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 1))" iif "$wg" to 100.64.0.0/10 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 2))" iif "$wg" to 169.254.0.0/16 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 3))" iif "$wg" to 172.16.0.0/12 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 4))" iif "$wg" to 192.168.0.0/16 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 10))" from "$subnet" iif "$wg" lookup "$table" >/dev/null 2>&1 || true
        ip -4 route flush table "$table" >/dev/null 2>&1 || true
        ip -4 route flush cache >/dev/null 2>&1 || true
    fi
}

runtime_cleanup() {
    backend="${1:-}"
    [ -n "$backend" ] || backend="$(detect_backend 2>/dev/null || true)"
    remove_rules_from_state
    case "$backend" in
        fw3-iptables) fw3_cleanup ;;
        fw4-nftables) fw4_cleanup ;;
    esac
    rm -f "$STATE_FILE"
}

save_state() {
    mkdir -p "$RUNTIME_DIR"
    cat > "$STATE_FILE" <<EOF_STATE
ENABLED='1'
WG_INTERFACE='$1'
WG_DEVICE='$2'
WAN_INTERFACE='$3'
WAN_DEVICE='$4'
WG_SUBNET='$5'
FIREWALL_BACKEND='$6'
ROUTE_TABLE='$7'
RULE_BASE='$8'
EXPIRES_AT='$9'
TOKEN='${10}'
EOF_STATE
    chmod 600 "$STATE_FILE"
}

schedule_expiry() {
    token="$1"; ttl="$2"
    (
        sleep "$ttl"
        [ -r "$STATE_FILE" ] || exit 0
        current="$(sed -n "s/^TOKEN='\([^']*\)'/\1/p" "$STATE_FILE" | sed -n '1p')"
        [ "$current" = "$token" ] || exit 0
        "$0" disable >/dev/null 2>&1 || true
    ) >/dev/null 2>&1 &
}

enable_egress() {
    [ "$#" -ge 2 ] && [ "$#" -le 3 ] || { usage >&2; exit 2; }
    wg="$1"; wan="$2"; ttl="${3:-300}"
    valid_name "$wg" || fail "Invalid WireGuard logical interface: $wg"
    valid_name "$wan" || fail "Invalid WAN logical interface: $wan"
    valid_uint "$ttl" || fail "TTL must be an integer"
    [ "$ttl" -ge 30 ] && [ "$ttl" -le 43200 ] || fail "TTL must be between 30 and 43200 seconds"

    for cmd in uci ubus jsonfilter ip; do command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"; done
    [ "$(uci -q get "network.$wg.proto" 2>/dev/null || true)" = wireguard ] || fail "$wg is not a WireGuard interface"
    interface_up "$wg" || fail "$wg is not up"
    interface_up "$wan" || fail "$wan is not up"

    wg_dev="$(l3_device "$wg")"; [ -n "$wg_dev" ] || wg_dev="$wg"
    wan_dev="$(l3_device "$wan")"; [ -n "$wan_dev" ] || fail "Cannot resolve L3 device for $wan"
    subnet="$(wireguard_subnet "$wg")"; [ -n "$subnet" ] || fail "Cannot detect the IPv4 subnet of $wg"

    cleanup_legacy_uci >/dev/null 2>&1 || true
    old_backend=""
    if [ -r "$STATE_FILE" ]; then
        old_backend="$(sed -n "s/^FIREWALL_BACKEND='\([^']*\)'/\1/p" "$STATE_FILE" | sed -n '1p')"
    fi
    runtime_cleanup "$old_backend"

    backend="$(detect_backend)"
    table="$(choose_route_table)" || fail "No free policy routing table in 51820-51879"
    base="$(choose_rule_base)" || fail "No free high-priority IPv4 rule block"
    expires_at="$(( $(date +%s) + ttl ))"
    token="$$-$(date +%s)"

    install_route_table "$wan_dev" "$table"
    install_rules "$wg_dev" "$subnet" "$table" "$base"
    case "$backend" in
        fw3-iptables) fw3_install "$wg_dev" "$wan_dev" "$subnet" ;;
        fw4-nftables) fw4_install "$wg_dev" "$wan_dev" "$subnet" ;;
        *) fail "Unsupported firewall backend: $backend" ;;
    esac
    save_state "$wg" "$wg_dev" "$wan" "$wan_dev" "$subnet" "$backend" "$table" "$base" "$expires_at" "$token"
    schedule_expiry "$token" "$ttl"

    printf '\nWireGuard home IPv4 egress enabled (runtime only).\n'
    printf 'WireGuard: %s (%s)\n' "$wg" "$subnet"
    printf 'Selected WAN: %s (%s)\n' "$wan" "$wan_dev"
    printf 'Firewall backend: %s\n' "$backend"
    printf 'Routing table: %s\n' "$table"
    printf 'Rule base: %s\n' "$base"
    printf 'Expires in: %ss\n' "$ttl"
    printf 'Reboot behavior: OFF (no persistent UCI egress rules).\n'
    printf '\nClient full IPv4 tunnel:\n  AllowedIPs = 0.0.0.0/0\n'
}

disable_egress() {
    backend=""
    if [ -r "$STATE_FILE" ]; then
        backend="$(sed -n "s/^FIREWALL_BACKEND='\([^']*\)'/\1/p" "$STATE_FILE" | sed -n '1p')"
    fi
    runtime_cleanup "$backend"
    printf 'WireGuard home IPv4 egress disabled.\n'
}

sync_egress() {
    [ -r "$STATE_FILE" ] || return 0
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    now="$(date +%s)"
    expires="${EXPIRES_AT:-0}"
    case "$expires" in ''|*[!0-9]*) expires=0 ;; esac
    if [ "$expires" -le "$now" ]; then
        runtime_cleanup "${FIREWALL_BACKEND:-}"
        logger -t remote-gate "WireGuard egress expired and was cleared" 2>/dev/null || true
        return 0
    fi

    wg="${WG_INTERFACE:-}"; wan="${WAN_INTERFACE:-}"
    remaining="$((expires - now))"
    [ -n "$wg" ] && [ -n "$wan" ] || { runtime_cleanup "${FIREWALL_BACKEND:-}"; return 1; }

    rule_ok=0
    if valid_uint "${RULE_BASE:-}" && valid_uint "${ROUTE_TABLE:-}"; then
        ip -4 rule show 2>/dev/null | grep -Eq "^$((RULE_BASE + 10)):.*lookup ${ROUTE_TABLE}([[:space:]]|$)" && rule_ok=1
    fi
    firewall_ok=0
    case "${FIREWALL_BACKEND:-}" in
        fw3-iptables)
            iptables -C FORWARD -j "$FW3_FILTER_CHAIN" >/dev/null 2>&1 && firewall_ok=1
            ;;
        fw4-nftables)
            nft -a list chain inet fw4 forward 2>/dev/null | grep -Fq "$NFT_COMMENT" && firewall_ok=1
            ;;
    esac
    [ "$rule_ok" -eq 1 ] && [ "$firewall_ok" -eq 1 ] && return 0

    runtime_cleanup "${FIREWALL_BACKEND:-}"
    enable_egress "$wg" "$wan" "$remaining"
}

status_egress() {
    if [ ! -r "$STATE_FILE" ]; then
        printf 'disabled\n'
        exit 0
    fi
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    now="$(date +%s)"
    expires="${EXPIRES_AT:-0}"
    case "$expires" in ''|*[!0-9]*) expires=0 ;; esac
    if [ "$expires" -le "$now" ]; then
        runtime_cleanup "${FIREWALL_BACKEND:-}"
        printf 'disabled\n'
        exit 0
    fi
    remaining="$((expires - now))"
    printf 'enabled\n'
    printf 'WireGuard: %s\n' "${WG_INTERFACE:-unknown}"
    printf 'Subnet: %s\n' "${WG_SUBNET:-unknown}"
    printf 'WAN: %s\n' "${WAN_INTERFACE:-unknown}"
    printf 'WAN device: %s\n' "${WAN_DEVICE:-unknown}"
    printf 'Firewall backend: %s\n' "${FIREWALL_BACKEND:-unknown}"
    printf 'Routing table: %s\n' "${ROUTE_TABLE:-unknown}"
    printf 'Rule base: %s\n' "${RULE_BASE:-unknown}"
    printf 'Expires in: %ss\n' "$remaining"
    printf 'Persistent UCI egress rules: no\n'
    printf '\nIPv4 rules:\n'
    if valid_uint "${RULE_BASE:-}"; then
        ip -4 rule show 2>/dev/null | awk -v lo="${RULE_BASE}" -v hi="$((RULE_BASE + 10))" '
            {
                p=$1; sub(/:$/, "", p);
                if (p+0 >= lo && p+0 <= hi) print
            }'
    fi
    printf '\nTable %s:\n' "${ROUTE_TABLE:-unknown}"
    valid_uint "${ROUTE_TABLE:-}" && ip -4 route show table "$ROUTE_TABLE" 2>/dev/null | sed -n '1,8p' || true
}

[ "$(id -u)" -eq 0 ] || fail "Run as root"
case "${1:-}" in
    enable) shift; enable_egress "$@" ;;
    disable) disable_egress ;;
    sync) sync_egress ;;
    status) status_egress ;;
    cleanup-legacy) cleanup_legacy_uci ;;
    help|--help|-h|'') usage ;;
    *) fail "Unknown action: $1" ;;
esac
