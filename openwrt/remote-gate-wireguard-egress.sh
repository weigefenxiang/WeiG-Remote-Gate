#!/bin/sh
set -eu
umask 077

RUNTIME_DIR="${REMOTE_GATE_RUNTIME_DIR:-/tmp/remote-gate}"
STATE_FILE="$RUNTIME_DIR/wireguard-egress.conf"
ERROR_FILE="$RUNTIME_DIR/wireguard-egress-error.conf"
LEGACY_STATE_FILE="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}/wireguard-egress.conf"
FIREWALL="/usr/lib/remote-gate/remote-gate-firewall.sh"
FW3_FILTER_CHAIN="WEIG_WG_EGRESS"
FW3_NAT_CHAIN="WEIG_WG_EGRESS_NAT"
FW3_FILTER_CHAIN6="WEIG_WG_EGRESS6"
FW3_NAT_CHAIN6="WEIG_WG_EGRESS_NAT6"
NFT_COMMENT="WeiG Remote Gate WG egress"
XTABLES_WAIT_SECONDS="${REMOTE_GATE_XTABLES_WAIT_SECONDS:-15}"
case "$XTABLES_WAIT_SECONDS" in ''|*[!0-9]*) XTABLES_WAIT_SECONDS=15 ;; esac
[ "$XTABLES_WAIT_SECONDS" -ge 1 ] || XTABLES_WAIT_SECONDS=15
[ "$XTABLES_WAIT_SECONDS" -le 60 ] || XTABLES_WAIT_SECONDS=60

sanitize_detail() {
    printf '%s' "$1" | tr '\r\n' '  ' | sed 's/[^A-Za-z0-9 ._:/(),+-]/_/g' | cut -c1-200
}

clear_error_state() { rm -f "$ERROR_FILE"; }

write_error_state() {
    [ "${ATTEMPT_ACTIVE:-0}" = 1 ] || return 0
    mkdir -p "$RUNTIME_DIR"
    detail="$(sanitize_detail "$1")"
    cat > "$ERROR_FILE" <<EOF_ERROR
STATE='failed'
MODE='${ATTEMPT_MODE:-}'
WAN_INTERFACE='${ATTEMPT_WAN:-}'
WG_INTERFACE='${ATTEMPT_WG:-}'
DETAIL='$detail'
EXPIRES_AT='${ATTEMPT_EXPIRES_AT:-0}'
EOF_ERROR
    chmod 600 "$ERROR_FILE"
}

fail() {
    write_error_state "$*"
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'USAGE'
Usage:
  remote-gate-wireguard-egress.sh enable <wireguard-interface> <wan-interface> [ttl-seconds] [ipv4|ipv6|dual]
  remote-gate-wireguard-egress.sh disable
  remote-gate-wireguard-egress.sh sync
  remote-gate-wireguard-egress.sh status
  remote-gate-wireguard-egress.sh status-json
  remote-gate-wireguard-egress.sh cleanup-legacy

Examples:
  remote-gate-wireguard-egress.sh enable WG_HOME WAN2 300 ipv4
  remote-gate-wireguard-egress.sh enable WG_HOME WAN2 300 dual

This helper creates runtime-only forwarding, masquerading and policy routing.
It never commits new network/firewall UCI sections. Runtime state lives under
/tmp, so a reboot always returns Internet egress to OFF.

IPv6/dual mode requires a ULA IPv6 subnet on the WireGuard interface and a
working IPv6 default route on the selected WAN. IPv6 Internet egress uses
runtime NAT66 so a private WireGuard ULA can leave through the selected WAN.
USAGE
}

valid_name() { case "$1" in ''|*[!A-Za-z0-9_.-]*) return 1 ;; *) return 0 ;; esac; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
valid_mode() { case "$1" in ipv4|ipv6|dual) return 0 ;; *) return 1 ;; esac; }
mode_has_v4() { case "$1" in ipv4|dual) return 0 ;; *) return 1 ;; esac; }
mode_has_v6() { case "$1" in ipv6|dual) return 0 ;; *) return 1 ;; esac; }

interface_status() { ubus call "network.interface.$1" status 2>/dev/null; }
interface_up() { interface_status "$1" | jsonfilter -e '@.up' 2>/dev/null | grep -qx 'true'; }
l3_device() { interface_status "$1" | jsonfilter -e '@.l3_device' 2>/dev/null | sed -n '1p'; }
xtables4() { iptables -w "$XTABLES_WAIT_SECONDS" "$@"; }
xtables6() { ip6tables -w "$XTABLES_WAIT_SECONDS" "$@"; }

wireguard_subnet4() {
    logical="$1"
    device="$(l3_device "$logical")"
    [ -n "$device" ] || device="$logical"
    ip -4 route show dev "$device" scope link 2>/dev/null |
        awk '$1 ~ /^[0-9]+(\.[0-9]+){3}\/[0-9]+$/ { print $1; exit }'
}

wireguard_subnet6() {
    logical="$1"
    device="$(l3_device "$logical")"
    [ -n "$device" ] || device="$logical"

    # The interface address is authoritative. OpenWrt/Linux commonly reports a
    # WireGuard ULA as `scope global`, so filtering routes by `scope link`
    # incorrectly rejects a valid fd00::/8 address.
    ula="$(ip -6 addr show dev "$device" 2>/dev/null | awk '
        $1 == "inet6" {
            cidr=$2; addr=tolower(cidr); sub(/\/.*/, "", addr)
            if (addr ~ /^(fc|fd)/) { print cidr; exit }
        }')"
    [ -n "$ula" ] || return 1

    prefix="${ula#*/}"
    route="$(ip -6 route show dev "$device" 2>/dev/null | awk -v suffix="/$prefix" '
        tolower($1) ~ /^(fc|fd)/ && index($1, suffix) { print $1; exit }')"
    if [ -n "$route" ]; then
        printf '%s\n' "$route"
    else
        # Fallback is still useful on kernels that omit the connected route;
        # iproute2/nftables normalize a CIDR when installing the runtime rule.
        printf '%s\n' "$ula"
    fi
}

detect_backend() {
    [ -x "$FIREWALL" ] || fail "Missing $FIREWALL"
    "$FIREWALL" detect 2>/dev/null || fail "Unsupported firewall backend"
}

cleanup_legacy_uci() {
    changed=0
    for section in remote_gate_wg_egress_zone remote_gate_wg_egress_forward remote_gate_wg_egress_nat; do
        if uci -q get "firewall.$section" >/dev/null 2>&1; then
            uci -q delete "firewall.$section" >/dev/null 2>&1 || true
            changed=1
        fi
    done
    for section in remote_gate_wg_egress_default remote_gate_wg_egress_main10 remote_gate_wg_egress_main100 remote_gate_wg_egress_main169 remote_gate_wg_egress_main172 remote_gate_wg_egress_main192 remote_gate_wg_egress_default_rule; do
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

fw3_cleanup4() {
    command -v iptables >/dev/null 2>&1 || return 0
    while xtables4 -C FORWARD -j "$FW3_FILTER_CHAIN" >/dev/null 2>&1; do xtables4 -D FORWARD -j "$FW3_FILTER_CHAIN" >/dev/null 2>&1 || break; done
    xtables4 -F "$FW3_FILTER_CHAIN" >/dev/null 2>&1 || true
    xtables4 -X "$FW3_FILTER_CHAIN" >/dev/null 2>&1 || true
    while xtables4 -t nat -C POSTROUTING -j "$FW3_NAT_CHAIN" >/dev/null 2>&1; do xtables4 -t nat -D POSTROUTING -j "$FW3_NAT_CHAIN" >/dev/null 2>&1 || break; done
    xtables4 -t nat -F "$FW3_NAT_CHAIN" >/dev/null 2>&1 || true
    xtables4 -t nat -X "$FW3_NAT_CHAIN" >/dev/null 2>&1 || true
}

fw3_cleanup6() {
    command -v ip6tables >/dev/null 2>&1 || return 0
    while xtables6 -C FORWARD -j "$FW3_FILTER_CHAIN6" >/dev/null 2>&1; do xtables6 -D FORWARD -j "$FW3_FILTER_CHAIN6" >/dev/null 2>&1 || break; done
    xtables6 -F "$FW3_FILTER_CHAIN6" >/dev/null 2>&1 || true
    xtables6 -X "$FW3_FILTER_CHAIN6" >/dev/null 2>&1 || true
    while xtables6 -t nat -C POSTROUTING -j "$FW3_NAT_CHAIN6" >/dev/null 2>&1; do xtables6 -t nat -D POSTROUTING -j "$FW3_NAT_CHAIN6" >/dev/null 2>&1 || break; done
    xtables6 -t nat -F "$FW3_NAT_CHAIN6" >/dev/null 2>&1 || true
    xtables6 -t nat -X "$FW3_NAT_CHAIN6" >/dev/null 2>&1 || true
}

fw3_cleanup() { fw3_cleanup4; fw3_cleanup6; }

fw3_install4() {
    wg_dev="$1"; wan_dev="$2"; subnet="$3"
    fw3_cleanup4
    xtables4 -N "$FW3_FILTER_CHAIN" || return 1
    xtables4 -A "$FW3_FILTER_CHAIN" -i "$wg_dev" -o "$wan_dev" -s "$subnet" -j ACCEPT || return 1
    xtables4 -A "$FW3_FILTER_CHAIN" -i "$wan_dev" -o "$wg_dev" -d "$subnet" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT || return 1
    xtables4 -I FORWARD 1 -j "$FW3_FILTER_CHAIN" || return 1
    xtables4 -t nat -N "$FW3_NAT_CHAIN" || return 1
    xtables4 -t nat -A "$FW3_NAT_CHAIN" -s "$subnet" -o "$wan_dev" -j MASQUERADE || return 1
    xtables4 -t nat -I POSTROUTING 1 -j "$FW3_NAT_CHAIN" || return 1
}

fw3_install6() {
    wg_dev="$1"; wan_dev="$2"; subnet="$3"
    command -v ip6tables >/dev/null 2>&1 || return 1
    xtables6 -t nat -L POSTROUTING >/dev/null 2>&1 || return 1
    fw3_cleanup6
    xtables6 -N "$FW3_FILTER_CHAIN6" || return 1
    xtables6 -A "$FW3_FILTER_CHAIN6" -i "$wg_dev" -o "$wan_dev" -s "$subnet" -j ACCEPT || return 1
    xtables6 -A "$FW3_FILTER_CHAIN6" -i "$wan_dev" -o "$wg_dev" -d "$subnet" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT || return 1
    xtables6 -I FORWARD 1 -j "$FW3_FILTER_CHAIN6" || return 1
    xtables6 -t nat -N "$FW3_NAT_CHAIN6" || return 1
    xtables6 -t nat -A "$FW3_NAT_CHAIN6" -s "$subnet" -o "$wan_dev" -j MASQUERADE || return 1
    xtables6 -t nat -I POSTROUTING 1 -j "$FW3_NAT_CHAIN6" || return 1
}

nft_delete_comment_rules() {
    chain="$1"
    nft -a list chain inet fw4 "$chain" 2>/dev/null |
        awk -v marker="$NFT_COMMENT" 'index($0, marker) { for (i=1; i<=NF; i++) if ($i=="handle") print $(i+1) }' |
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

fw4_install4() {
    wg_dev="$1"; wan_dev="$2"; subnet="$3"
    nft insert rule inet fw4 forward iifname "$wg_dev" oifname "$wan_dev" ip saddr "$subnet" counter accept comment "$NFT_COMMENT v4 outbound" || return 1
    nft insert rule inet fw4 forward iifname "$wan_dev" oifname "$wg_dev" ip daddr "$subnet" ct state established,related counter accept comment "$NFT_COMMENT v4 return" || return 1
    nft insert rule inet fw4 srcnat oifname "$wan_dev" ip saddr "$subnet" counter masquerade comment "$NFT_COMMENT v4 nat" || return 1
}

fw4_install6() {
    wg_dev="$1"; wan_dev="$2"; subnet="$3"
    nft insert rule inet fw4 forward iifname "$wg_dev" oifname "$wan_dev" ip6 saddr "$subnet" counter accept comment "$NFT_COMMENT v6 outbound" || return 1
    nft insert rule inet fw4 forward iifname "$wan_dev" oifname "$wg_dev" ip6 daddr "$subnet" ct state established,related counter accept comment "$NFT_COMMENT v6 return" || return 1
    nft insert rule inet fw4 srcnat oifname "$wan_dev" ip6 saddr "$subnet" counter masquerade comment "$NFT_COMMENT v6 nat66" || return 1
}

priority_used() {
    flag="$1"; priority="$2"
    ip "$flag" rule show 2>/dev/null | grep -Eq "^${priority}:"
}

choose_rule_base() {
    flag="$1"; base=80
    while [ "$base" -le 380 ]; do
        ok=1
        for offset in 0 1 2 3 4 10; do
            priority="$((base + offset))"
            if priority_used "$flag" "$priority"; then ok=0; break; fi
        done
        [ "$ok" -eq 1 ] && { printf '%s\n' "$base"; return 0; }
        base="$((base + 20))"
    done
    return 1
}

table_in_use() {
    flag="$1"; table="$2"
    ip "$flag" rule show 2>/dev/null | grep -Eq "lookup ${table}([[:space:]]|$)" && return 0
    [ -n "$(ip "$flag" route show table "$table" 2>/dev/null || true)" ]
}

choose_route_table() {
    flag="$1"; start="$2"; end="$3"; table="$start"
    while [ "$table" -le "$end" ]; do
        table_in_use "$flag" "$table" || { printf '%s\n' "$table"; return 0; }
        table="$((table + 1))"
    done
    return 1
}

install_route_table() {
    flag="$1"; wan_dev="$2"; table="$3"
    route="$(ip "$flag" route show default dev "$wan_dev" 2>/dev/null | sed -n '1p')"
    [ -n "$route" ] || return 1

    if [ "$flag" = "-6" ]; then
        # ISP IPv6 defaults may be source-specific, for example:
        # `default from 2408:.../64 via fe80::1`. The WG ULA source cannot
        # match that `from` clause, so build an unqualified runtime default
        # from the same next-hop and bind link-local gateways to the WAN dev.
        gateway="$(printf '%s\n' "$route" | awk '{for (i=1;i<=NF;i++) if ($i=="via") {print $(i+1); exit}}')"
        if [ -n "$gateway" ]; then
            ip -6 route replace table "$table" default via "$gateway" dev "$wan_dev"
        else
            ip -6 route replace table "$table" default dev "$wan_dev"
        fi
        return $?
    fi

    args="${route#default }"
    # shellcheck disable=SC2086
    ip "$flag" route replace table "$table" default $args
}

install_rules4() {
    wg_dev="$1"; subnet="$2"; table="$3"; base="$4"
    ip -4 rule add priority "$((base + 0))" iif "$wg_dev" to 10.0.0.0/8 lookup main || return 1
    ip -4 rule add priority "$((base + 1))" iif "$wg_dev" to 100.64.0.0/10 lookup main || return 1
    ip -4 rule add priority "$((base + 2))" iif "$wg_dev" to 169.254.0.0/16 lookup main || return 1
    ip -4 rule add priority "$((base + 3))" iif "$wg_dev" to 172.16.0.0/12 lookup main || return 1
    ip -4 rule add priority "$((base + 4))" iif "$wg_dev" to 192.168.0.0/16 lookup main || return 1
    ip -4 rule add priority "$((base + 10))" from "$subnet" iif "$wg_dev" lookup "$table" || return 1
    ip -4 route flush cache >/dev/null 2>&1 || true
}

install_rules6() {
    wg_dev="$1"; subnet="$2"; table="$3"; base="$4"
    ip -6 rule add priority "$((base + 0))" iif "$wg_dev" to ::1/128 lookup main || return 1
    ip -6 rule add priority "$((base + 1))" iif "$wg_dev" to fc00::/7 lookup main || return 1
    ip -6 rule add priority "$((base + 2))" iif "$wg_dev" to fe80::/10 lookup main || return 1
    ip -6 rule add priority "$((base + 3))" iif "$wg_dev" to ff00::/8 lookup main || return 1
    ip -6 rule add priority "$((base + 10))" from "$subnet" iif "$wg_dev" lookup "$table" || return 1
    ip -6 route flush cache >/dev/null 2>&1 || true
}

remove_rules_from_state() {
    [ -r "$STATE_FILE" ] || return 0
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    if mode_has_v4 "${MODE:-ipv4}" && valid_uint "${RULE_BASE4:-}" && valid_uint "${ROUTE_TABLE4:-}" && [ -n "${WG_DEVICE:-}" ] && [ -n "${WG_SUBNET4:-}" ]; then
        base="$RULE_BASE4"; table="$ROUTE_TABLE4"; wg="$WG_DEVICE"; subnet="$WG_SUBNET4"
        ip -4 rule del priority "$((base + 0))" iif "$wg" to 10.0.0.0/8 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 1))" iif "$wg" to 100.64.0.0/10 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 2))" iif "$wg" to 169.254.0.0/16 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 3))" iif "$wg" to 172.16.0.0/12 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 4))" iif "$wg" to 192.168.0.0/16 lookup main >/dev/null 2>&1 || true
        ip -4 rule del priority "$((base + 10))" from "$subnet" iif "$wg" lookup "$table" >/dev/null 2>&1 || true
        ip -4 route flush table "$table" >/dev/null 2>&1 || true
        ip -4 route flush cache >/dev/null 2>&1 || true
    fi
    if mode_has_v6 "${MODE:-ipv4}" && valid_uint "${RULE_BASE6:-}" && valid_uint "${ROUTE_TABLE6:-}" && [ -n "${WG_DEVICE:-}" ] && [ -n "${WG_SUBNET6:-}" ]; then
        base="$RULE_BASE6"; table="$ROUTE_TABLE6"; wg="$WG_DEVICE"; subnet="$WG_SUBNET6"
        ip -6 rule del priority "$((base + 0))" iif "$wg" to ::1/128 lookup main >/dev/null 2>&1 || true
        ip -6 rule del priority "$((base + 1))" iif "$wg" to fc00::/7 lookup main >/dev/null 2>&1 || true
        ip -6 rule del priority "$((base + 2))" iif "$wg" to fe80::/10 lookup main >/dev/null 2>&1 || true
        ip -6 rule del priority "$((base + 3))" iif "$wg" to ff00::/8 lookup main >/dev/null 2>&1 || true
        ip -6 rule del priority "$((base + 10))" from "$subnet" iif "$wg" lookup "$table" >/dev/null 2>&1 || true
        ip -6 route flush table "$table" >/dev/null 2>&1 || true
        ip -6 route flush cache >/dev/null 2>&1 || true
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
MODE='$MODE'
WG_INTERFACE='$WG_INTERFACE'
WG_DEVICE='$WG_DEVICE'
WAN_INTERFACE='$WAN_INTERFACE'
WAN_DEVICE='$WAN_DEVICE'
WG_SUBNET4='$WG_SUBNET4'
WG_SUBNET6='$WG_SUBNET6'
FIREWALL_BACKEND='$FIREWALL_BACKEND'
ROUTE_TABLE4='$ROUTE_TABLE4'
ROUTE_TABLE6='$ROUTE_TABLE6'
RULE_BASE4='$RULE_BASE4'
RULE_BASE6='$RULE_BASE6'
EXPIRES_AT='$EXPIRES_AT'
TOKEN='$TOKEN'
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

rollback() {
    message="$1"
    runtime_cleanup "${FIREWALL_BACKEND:-}"
    fail "$message"
}

enable_egress() {
    [ "$#" -ge 2 ] && [ "$#" -le 4 ] || { usage >&2; exit 2; }
    wg="$1"; wan="$2"; ttl="${3:-300}"; mode="${4:-ipv4}"
    valid_name "$wg" || fail "Invalid WireGuard logical interface: $wg"
    valid_name "$wan" || fail "Invalid WAN logical interface: $wan"
    valid_uint "$ttl" || fail "TTL must be an integer"
    valid_mode "$mode" || fail "Mode must be ipv4, ipv6 or dual"
    [ "$ttl" -ge 30 ] && [ "$ttl" -le 43200 ] || fail "TTL must be between 30 and 43200 seconds"

    ATTEMPT_ACTIVE=1
    ATTEMPT_MODE="$mode"
    ATTEMPT_WAN="$wan"
    ATTEMPT_WG="$wg"
    ATTEMPT_EXPIRES_AT="$(( $(date +%s) + ttl ))"
    clear_error_state

    for cmd in uci ubus jsonfilter ip; do command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"; done
    [ "$(uci -q get "network.$wg.proto" 2>/dev/null || true)" = wireguard ] || fail "$wg is not a WireGuard interface"
    interface_up "$wg" || fail "$wg is not up"
    interface_up "$wan" || fail "$wan is not up"

    wg_dev="$(l3_device "$wg")"; [ -n "$wg_dev" ] || wg_dev="$wg"
    wan_dev="$(l3_device "$wan")"; [ -n "$wan_dev" ] || fail "Cannot resolve L3 device for $wan"
    subnet4=""; subnet6=""
    if mode_has_v4 "$mode"; then
        subnet4="$(wireguard_subnet4 "$wg")"
        [ -n "$subnet4" ] || fail "Cannot detect the IPv4 subnet of $wg"
        ip -4 route show default dev "$wan_dev" 2>/dev/null | grep -q '^default' || fail "No IPv4 default route found on $wan"
    fi
    if mode_has_v6 "$mode"; then
        subnet6="$(wireguard_subnet6 "$wg")"
        [ -n "$subnet6" ] || fail "WireGuard IPv6 ULA subnet missing on $wg"
        ip -6 route show default dev "$wan_dev" 2>/dev/null | grep -q '^default' || fail "No IPv6 default route found on $wan"
    fi

    cleanup_legacy_uci >/dev/null 2>&1 || true
    old_backend=""
    [ ! -r "$STATE_FILE" ] || old_backend="$(sed -n "s/^FIREWALL_BACKEND='\([^']*\)'/\1/p" "$STATE_FILE" | sed -n '1p')"
    runtime_cleanup "$old_backend"

    backend="$(detect_backend)"
    table4=""; table6=""; base4=""; base6=""
    if mode_has_v4 "$mode"; then
        table4="$(choose_route_table -4 51820 51879)" || fail "No free IPv4 policy routing table in 51820-51879"
        base4="$(choose_rule_base -4)" || fail "No free high-priority IPv4 rule block"
    fi
    if mode_has_v6 "$mode"; then
        table6="$(choose_route_table -6 52020 52079)" || fail "No free IPv6 policy routing table in 52020-52079"
        base6="$(choose_rule_base -6)" || fail "No free high-priority IPv6 rule block"
    fi

    MODE="$mode"; WG_INTERFACE="$wg"; WG_DEVICE="$wg_dev"; WAN_INTERFACE="$wan"; WAN_DEVICE="$wan_dev"
    WG_SUBNET4="$subnet4"; WG_SUBNET6="$subnet6"; FIREWALL_BACKEND="$backend"
    ROUTE_TABLE4="$table4"; ROUTE_TABLE6="$table6"; RULE_BASE4="$base4"; RULE_BASE6="$base6"
    EXPIRES_AT="$(( $(date +%s) + ttl ))"; TOKEN="$$-$(date +%s)"
    save_state

    if mode_has_v4 "$mode"; then
        install_route_table -4 "$wan_dev" "$table4" || rollback "Cannot build IPv4 default route through $wan"
        install_rules4 "$wg_dev" "$subnet4" "$table4" "$base4" || rollback "Cannot install IPv4 policy rules"
    fi
    if mode_has_v6 "$mode"; then
        install_route_table -6 "$wan_dev" "$table6" || rollback "Cannot build IPv6 default route through $wan"
        install_rules6 "$wg_dev" "$subnet6" "$table6" "$base6" || rollback "Cannot install IPv6 policy rules"
    fi

    case "$backend" in
        fw3-iptables)
            if mode_has_v4 "$mode"; then fw3_install4 "$wg_dev" "$wan_dev" "$subnet4" || rollback "IPv4 egress firewall installation failed"; fi
            if mode_has_v6 "$mode"; then fw3_install6 "$wg_dev" "$wan_dev" "$subnet6" || rollback "IPv6 NAT66 is unavailable in ip6tables"; fi
            ;;
        fw4-nftables)
            nft list chain inet fw4 forward >/dev/null 2>&1 || rollback "fw4 forward chain unavailable"
            nft list chain inet fw4 srcnat >/dev/null 2>&1 || rollback "fw4 srcnat chain unavailable"
            fw4_cleanup
            if mode_has_v4 "$mode"; then fw4_install4 "$wg_dev" "$wan_dev" "$subnet4" || rollback "IPv4 nft egress installation failed"; fi
            if mode_has_v6 "$mode"; then fw4_install6 "$wg_dev" "$wan_dev" "$subnet6" || rollback "IPv6 nft NAT66 installation failed"; fi
            ;;
        *) rollback "Unsupported firewall backend: $backend" ;;
    esac

    ATTEMPT_ACTIVE=0
    clear_error_state
    schedule_expiry "$TOKEN" "$ttl"
    printf '\nWireGuard home %s egress enabled (runtime only).\n' "$mode"
    printf 'WireGuard: %s\n' "$wg"
    [ -n "$subnet4" ] && printf 'IPv4 subnet: %s\n' "$subnet4"
    [ -n "$subnet6" ] && printf 'IPv6 subnet: %s\n' "$subnet6"
    printf 'Selected WAN: %s (%s)\n' "$wan" "$wan_dev"
    printf 'Firewall backend: %s\n' "$backend"
    [ -n "$table4" ] && printf 'IPv4 routing table: %s · rule base %s\n' "$table4" "$base4"
    [ -n "$table6" ] && printf 'IPv6 routing table: %s · rule base %s\n' "$table6" "$base6"
    printf 'Expires in: %ss\n' "$ttl"
    printf 'Reboot behavior: OFF (no persistent UCI egress rules).\n'
    case "$mode" in
        ipv4) printf '\nClient full tunnel: AllowedIPs = 0.0.0.0/0\n' ;;
        ipv6) printf '\nClient full tunnel: AllowedIPs = ::/0\n' ;;
        dual) printf '\nClient full tunnel: AllowedIPs = 0.0.0.0/0, ::/0\n' ;;
    esac
}

disable_egress() {
    backend=""
    [ ! -r "$STATE_FILE" ] || backend="$(sed -n "s/^FIREWALL_BACKEND='\([^']*\)'/\1/p" "$STATE_FILE" | sed -n '1p')"
    runtime_cleanup "$backend"
    clear_error_state
    printf 'WireGuard home Internet egress disabled.\n'
}

sync_egress() {
    [ -r "$STATE_FILE" ] || return 0
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    now="$(date +%s)"; expires="${EXPIRES_AT:-0}"
    case "$expires" in ''|*[!0-9]*) expires=0 ;; esac
    if [ "$expires" -le "$now" ]; then
        runtime_cleanup "${FIREWALL_BACKEND:-}"
        logger -t remote-gate "WireGuard egress expired and was cleared" 2>/dev/null || true
        return 0
    fi

    mode="${MODE:-ipv4}"; wg="${WG_INTERFACE:-}"; wan="${WAN_INTERFACE:-}"; remaining="$((expires - now))"
    valid_mode "$mode" && [ -n "$wg" ] && [ -n "$wan" ] || { runtime_cleanup "${FIREWALL_BACKEND:-}"; return 1; }
    rule_ok=1
    if mode_has_v4 "$mode"; then
        valid_uint "${RULE_BASE4:-}" && valid_uint "${ROUTE_TABLE4:-}" && ip -4 rule show 2>/dev/null | grep -Eq "^$((RULE_BASE4 + 10)):.*lookup ${ROUTE_TABLE4}([[:space:]]|$)" || rule_ok=0
    fi
    if mode_has_v6 "$mode"; then
        valid_uint "${RULE_BASE6:-}" && valid_uint "${ROUTE_TABLE6:-}" && ip -6 rule show 2>/dev/null | grep -Eq "^$((RULE_BASE6 + 10)):.*lookup ${ROUTE_TABLE6}([[:space:]]|$)" || rule_ok=0
    fi
    firewall_ok=0
    case "${FIREWALL_BACKEND:-}" in
        fw3-iptables)
            if mode_has_v4 "$mode"; then xtables4 -C FORWARD -j "$FW3_FILTER_CHAIN" >/dev/null 2>&1 || rule_ok=0; fi
            if mode_has_v6 "$mode"; then xtables6 -C FORWARD -j "$FW3_FILTER_CHAIN6" >/dev/null 2>&1 || rule_ok=0; fi
            [ "$rule_ok" -eq 1 ] && firewall_ok=1
            ;;
        fw4-nftables)
            nft -a list chain inet fw4 forward 2>/dev/null | grep -Fq "$NFT_COMMENT" && firewall_ok=1
            ;;
    esac
    [ "$rule_ok" -eq 1 ] && [ "$firewall_ok" -eq 1 ] && return 0

    runtime_cleanup "${FIREWALL_BACKEND:-}"
    enable_egress "$wg" "$wan" "$remaining" "$mode"
}

error_state_valid() {
    [ -r "$ERROR_FILE" ] || return 1
    # shellcheck disable=SC1090
    . "$ERROR_FILE"
    now="$(date +%s)"; expires="${EXPIRES_AT:-0}"
    case "$expires" in ''|*[!0-9]*) expires=0 ;; esac
    if [ "$expires" -le "$now" ]; then clear_error_state; return 1; fi
    return 0
}

status_egress() {
    if [ -r "$STATE_FILE" ]; then
        # shellcheck disable=SC1090
        . "$STATE_FILE"
        now="$(date +%s)"; expires="${EXPIRES_AT:-0}"
        case "$expires" in ''|*[!0-9]*) expires=0 ;; esac
        if [ "$expires" -le "$now" ]; then runtime_cleanup "${FIREWALL_BACKEND:-}"; else
            remaining="$((expires - now))"
            printf 'enabled\nMode: %s\n' "${MODE:-ipv4}"
            printf 'WireGuard: %s\nWAN: %s\nWAN device: %s\n' "${WG_INTERFACE:-unknown}" "${WAN_INTERFACE:-unknown}" "${WAN_DEVICE:-unknown}"
            [ -n "${WG_SUBNET4:-}" ] && printf 'IPv4 subnet: %s\n' "$WG_SUBNET4"
            [ -n "${WG_SUBNET6:-}" ] && printf 'IPv6 subnet: %s\n' "$WG_SUBNET6"
            printf 'Expires in: %ss\nPersistent UCI egress rules: no\n' "$remaining"
            return 0
        fi
    fi
    if error_state_valid; then
        printf 'failed\nMode: %s\nWAN: %s\nWireGuard: %s\nDetail: %s\n' "${MODE:-unknown}" "${WAN_INTERFACE:-unknown}" "${WG_INTERFACE:-unknown}" "${DETAIL:-unknown}"
        return 0
    fi
    printf 'disabled\n'
}

status_json() {
    if [ -r "$STATE_FILE" ]; then
        # shellcheck disable=SC1090
        . "$STATE_FILE"
        now="$(date +%s)"; expires="${EXPIRES_AT:-0}"
        case "$expires" in ''|*[!0-9]*) expires=0 ;; esac
        if [ "$expires" -gt "$now" ]; then
            printf '{"active":true,"state":"active","mode":"%s","wan":"%s","device":"%s","wg":"%s","ipv4_subnet":"%s","ipv6_subnet":"%s","detail":"","expires_in":%s}\n' \
                "${MODE:-ipv4}" "${WAN_INTERFACE:-}" "${WAN_DEVICE:-}" "${WG_INTERFACE:-}" "${WG_SUBNET4:-}" "${WG_SUBNET6:-}" "$((expires - now))"
            return 0
        fi
        runtime_cleanup "${FIREWALL_BACKEND:-}"
    fi
    if error_state_valid; then
        printf '{"active":false,"state":"failed","mode":"%s","wan":"%s","device":"","wg":"%s","ipv4_subnet":"","ipv6_subnet":"","detail":"%s","expires_in":%s}\n' \
            "${MODE:-}" "${WAN_INTERFACE:-}" "${WG_INTERFACE:-}" "${DETAIL:-}" "$((EXPIRES_AT - $(date +%s)))"
        return 0
    fi
    printf '{"active":false,"state":"inactive","mode":"","wan":"","device":"","wg":"","ipv4_subnet":"","ipv6_subnet":"","detail":"","expires_in":0}\n'
}

[ "$(id -u)" -eq 0 ] || fail "Run as root"
case "${1:-}" in
    enable) shift; enable_egress "$@" ;;
    disable) disable_egress ;;
    sync) sync_egress ;;
    status) status_egress ;;
    status-json) status_json ;;
    cleanup-legacy) cleanup_legacy_uci ;;
    help|--help|-h|'') usage ;;
    *) fail "Unknown action: $1" ;;
esac
