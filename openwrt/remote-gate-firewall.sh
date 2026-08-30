#!/bin/sh
set -eu

STATE_FILE="/tmp/remote-gate.active"
TABLE_INCLUDE="/usr/share/nftables.d/table-pre/90-weig-remote-gate-sets.nft"
CHAIN_INCLUDE="/usr/share/nftables.d/chain-pre/input_wan/90-weig-remote-gate.nft"
TAG="remote-gate"

fail() { logger -t "$TAG" "$*"; printf 'ERROR: %s\n' "$*" >&2; exit 1; }

validate_ipv4() {
    printf '%s\n' "$1" | awk -F. '
        NF != 4 { exit 1 }
        {
            for (i=1; i<=4; i++) {
                if ($i !~ /^[0-9]+$/ || $i < 0 || $i > 255) exit 1
            }
        }
    '
}

validate_device() {
    case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac
}

validate_uint() {
    case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac
}

install_rules() {
    command -v nft >/dev/null 2>&1 || fail "nft is required"
    command -v fw4 >/dev/null 2>&1 || fail "firewall4/fw4 is required"

    auto_includes="$(uci -q get firewall.@defaults[0].auto_includes 2>/dev/null || true)"
    [ "$auto_includes" != "0" ] || fail "firewall auto_includes=0; WeiG Remote Gate requires firewall4 automatic nft includes"

    mkdir -p "$(dirname "$TABLE_INCLUDE")" "$(dirname "$CHAIN_INCLUDE")"

    cat > "$TABLE_INCLUDE" <<'EOF'
set weig_remote_gate_ipv4 {
    type ipv4_addr
    flags timeout
}

set weig_remote_gate_ifname {
    type ifname
    flags timeout
}

set weig_remote_gate_udp_port {
    type inet_service
    flags timeout
}
EOF

    cat > "$CHAIN_INCLUDE" <<'EOF'
ip saddr @weig_remote_gate_ipv4 iifname @weig_remote_gate_ifname icmp type echo-request counter accept comment "!WeiG Remote Gate: temporary ICMP"
ip saddr @weig_remote_gate_ipv4 iifname @weig_remote_gate_ifname udp dport @weig_remote_gate_udp_port counter accept comment "!WeiG Remote Gate: temporary WireGuard"
EOF

    fw4 -q check || fail "firewall4 rendered ruleset check failed"
    fw4 -q print | grep -q 'weig_remote_gate_ipv4' || fail "firewall4 did not include WeiG Remote Gate rules"

    /etc/init.d/firewall reload
    nft list set inet fw4 weig_remote_gate_ipv4 >/dev/null 2>&1 || fail "WeiG Remote Gate nft set missing after reload"
    rm -f "$STATE_FILE"
    logger -t "$TAG" "firewall4 integration installed"
}

clear_rules() {
    if nft list set inet fw4 weig_remote_gate_ipv4 >/dev/null 2>&1; then
        nft flush set inet fw4 weig_remote_gate_ipv4 2>/dev/null || true
        nft flush set inet fw4 weig_remote_gate_ifname 2>/dev/null || true
        nft flush set inet fw4 weig_remote_gate_udp_port 2>/dev/null || true
    fi
    rm -f "$STATE_FILE"
    logger -t "$TAG" "temporary authorization cleared"
}

activate() {
    source_ip="$1"
    device="$2"
    port="$3"
    ttl="$4"

    validate_ipv4 "$source_ip" || fail "invalid IPv4"
    validate_device "$device" || fail "invalid WAN device"
    validate_uint "$port" || fail "invalid UDP port"
    validate_uint "$ttl" || fail "invalid TTL"
    [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || fail "UDP port out of range"
    [ "$ttl" -ge 30 ] && [ "$ttl" -le 1800 ] || fail "TTL must be between 30 and 1800 seconds"
    ip link show "$device" >/dev/null 2>&1 || fail "WAN device does not exist: $device"
    nft list set inet fw4 weig_remote_gate_ipv4 >/dev/null 2>&1 || fail "WeiG Remote Gate firewall integration is not loaded"

    # v0.1 intentionally permits only one active authorization at a time.
    nft -f - <<EOF
flush set inet fw4 weig_remote_gate_ipv4
flush set inet fw4 weig_remote_gate_ifname
flush set inet fw4 weig_remote_gate_udp_port
add element inet fw4 weig_remote_gate_ipv4 { $source_ip timeout ${ttl}s }
add element inet fw4 weig_remote_gate_ifname { "$device" timeout ${ttl}s }
add element inet fw4 weig_remote_gate_udp_port { $port timeout ${ttl}s }
EOF

    now="$(date +%s)"
    expires="$((now + ttl))"
    {
        printf '%s\n' "$source_ip"
        printf '%s\n' "$device"
        printf '%s\n' "$port"
        printf '%s\n' "$expires"
    } > "$STATE_FILE"
    chmod 600 "$STATE_FILE"
    logger -t "$TAG" "temporary authorization active for $source_ip on $device UDP/$port (${ttl}s)"
}

status_json() {
    active=false
    source_ip=""
    device=""
    port=0
    expires_in=0

    if [ -r "$STATE_FILE" ]; then
        source_ip="$(sed -n '1p' "$STATE_FILE")"
        device="$(sed -n '2p' "$STATE_FILE")"
        port="$(sed -n '3p' "$STATE_FILE")"
        expires="$(sed -n '4p' "$STATE_FILE")"
        now="$(date +%s)"
        if validate_uint "$expires" && [ "$expires" -gt "$now" ] &&
           nft list set inet fw4 weig_remote_gate_ipv4 2>/dev/null | grep -Fq "$source_ip"; then
            active=true
            expires_in="$((expires - now))"
        fi
    fi

    if [ "$active" != "true" ]; then
        source_ip=""
        device=""
        port=0
        expires_in=0
        rm -f "$STATE_FILE"
    fi

    printf '{"active":%s,"source_ip":"%s","device":"%s","wg_port":%s,"expires_in":%s}\n' \
        "$active" "$source_ip" "$device" "$port" "$expires_in"
}

uninstall_rules() {
    clear_rules
    rm -f "$TABLE_INCLUDE" "$CHAIN_INCLUDE"
    fw4 -q check || fail "firewall4 check failed after removing WeiG Remote Gate includes"
    /etc/init.d/firewall reload
    logger -t "$TAG" "firewall4 integration removed"
}

case "${1:-}" in
    install) install_rules ;;
    activate)
        [ "$#" -eq 5 ] || fail "usage: $0 activate <source-ipv4> <wan-device> <udp-port> <ttl-seconds>"
        activate "$2" "$3" "$4" "$5"
        ;;
    clear) clear_rules ;;
    status-json) status_json ;;
    uninstall) uninstall_rules ;;
    *) fail "usage: $0 install|activate|clear|status-json|uninstall" ;;
esac
