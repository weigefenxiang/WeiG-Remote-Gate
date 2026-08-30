#!/bin/sh
set -eu

STATE_ROOT="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}/firewall"
BACKEND_FILE="$STATE_ROOT/backend"
DEVICES_V4_FILE="$STATE_ROOT/protected-devices-v4"
DEVICES_V6_FILE="$STATE_ROOT/protected-devices-v6"
LEGACY_DEVICES_FILE="$STATE_ROOT/protected-devices"
PORTS_FILE="$STATE_ROOT/protected-ports"
AUTH_FILE="$STATE_ROOT/authorization"
FW3_CHAIN_V4="WEIG_REMOTE_GATE"
FW3_CHAIN_V6="WEIG_REMOTE_GATE_V6"
FW3_AUTH_SET_V4="weig_remote_gate_auth_v4"
FW3_AUTH_SET_V6="weig_remote_gate_auth_v6"
FW4_TABLE_INCLUDE="/usr/share/nftables.d/table-pre/90-weig-remote-gate-sets.nft"
FW4_INPUT_INCLUDE="/usr/share/nftables.d/chain-pre/input/90-weig-remote-gate.nft"
INCLUDE_SCRIPT="/usr/lib/remote-gate/remote-gate-firewall-include.sh"
TAG="remote-gate"

fail() { logger -t "$TAG" "$*" 2>/dev/null || true; printf 'ERROR: %s\n' "$*" >&2; exit 1; }

valid_ipv4() {
    printf '%s\n' "$1" | awk -F. '
        NF != 4 { exit 1 }
        {
            for (i=1; i<=4; i++) {
                if ($i !~ /^[0-9]+$/ || $i < 0 || $i > 255) exit 1
            }
        }
    '
}

valid_ipv6() {
    case "$1" in
        *:*) ;;
        *) return 1 ;;
    esac
    case "$1" in
        *[!0-9A-Fa-f:.]*) return 1 ;;
    esac
    return 0
}

valid_device() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
valid_family() { case "$1" in ipv4|ipv6) return 0 ;; *) return 1 ;; esac; }
valid_scope() { case "$1" in wg|wg_ping) return 0 ;; *) return 1 ;; esac; }
valid_ttl() {
    valid_uint "$1" || return 1
    case "$1" in
        60|300|900|1800) return 0 ;;
    esac
    [ "$1" -ge 1800 ] && [ "$1" -le 43200 ] || return 1
    [ $(( $1 % 1800 )) -eq 0 ]
}

fw3_ipv6_capable() {
    command -v ip6tables >/dev/null 2>&1 || return 1
    ip6tables -m set -h >/dev/null 2>&1 || return 1
    ipset help 2>&1 | grep -q 'inet6' || return 1
}

ensure_state() {
    mkdir -p "$STATE_ROOT"
    chmod 700 "$STATE_ROOT" 2>/dev/null || true
    if [ ! -f "$DEVICES_V4_FILE" ] && [ -f "$LEGACY_DEVICES_FILE" ]; then
        cp "$LEGACY_DEVICES_FILE" "$DEVICES_V4_FILE"
    fi
    [ -f "$DEVICES_V4_FILE" ] || : > "$DEVICES_V4_FILE"
    [ -f "$DEVICES_V6_FILE" ] || : > "$DEVICES_V6_FILE"
    [ -f "$PORTS_FILE" ] || : > "$PORTS_FILE"
    chmod 600 "$DEVICES_V4_FILE" "$DEVICES_V6_FILE" "$PORTS_FILE" 2>/dev/null || true
}

detect_backend() {
    if command -v fw4 >/dev/null 2>&1 && command -v nft >/dev/null 2>&1; then
        printf '%s\n' 'fw4-nftables'
        return 0
    fi
    if command -v fw3 >/dev/null 2>&1 && command -v iptables >/dev/null 2>&1 && command -v ipset >/dev/null 2>&1; then
        if iptables -m set -h >/dev/null 2>&1; then
            printf '%s\n' 'fw3-iptables'
            return 0
        fi
    fi
    return 1
}

backend() {
    if [ -r "$BACKEND_FILE" ]; then
        b="$(sed -n '1p' "$BACKEND_FILE")"
        case "$b" in
            fw4-nftables)
                command -v fw4 >/dev/null 2>&1 && command -v nft >/dev/null 2>&1 && { printf '%s\n' "$b"; return 0; }
                ;;
            fw3-iptables)
                command -v fw3 >/dev/null 2>&1 && command -v iptables >/dev/null 2>&1 && command -v ipset >/dev/null 2>&1 && { printf '%s\n' "$b"; return 0; }
                ;;
        esac
    fi
    detect_backend
}

register_include() {
    b="$1"
    command -v uci >/dev/null 2>&1 || fail "uci is required"
    uci -q delete firewall.remote_gate 2>/dev/null || true
    uci set firewall.remote_gate='include'
    uci set firewall.remote_gate.type='script'
    uci set firewall.remote_gate.path="$INCLUDE_SCRIPT"
    uci set firewall.remote_gate.enabled='1'
    case "$b" in
        fw3-iptables) uci set firewall.remote_gate.reload='1' ;;
        fw4-nftables) uci set firewall.remote_gate.fw4_compatible='1' ;;
    esac
    uci commit firewall
}

unregister_include() {
    if command -v uci >/dev/null 2>&1; then
        uci -q delete firewall.remote_gate 2>/dev/null || true
        uci commit firewall 2>/dev/null || true
    fi
}

write_fw4_includes() {
    auto_includes="$(uci -q get firewall.@defaults[0].auto_includes 2>/dev/null || true)"
    [ "$auto_includes" != "0" ] || fail "firewall auto_includes=0; fw4 backend requires automatic nft includes"
    mkdir -p "$(dirname "$FW4_TABLE_INCLUDE")" "$(dirname "$FW4_INPUT_INCLUDE")"
    cat > "$FW4_TABLE_INCLUDE" <<'NFT'
set weig_remote_gate_protected_ifname_v4 {
    type ifname
}

set weig_remote_gate_protected_ifname_v6 {
    type ifname
}

set weig_remote_gate_protected_udp_port {
    type inet_service
}

set weig_remote_gate_auth_ipv4 {
    type ipv4_addr
    flags timeout
}

set weig_remote_gate_auth_ipv6 {
    type ipv6_addr
    flags timeout
}

set weig_remote_gate_auth_ifname {
    type ifname
}

set weig_remote_gate_auth_ping_ifname {
    type ifname
}

set weig_remote_gate_auth_udp_port {
    type inet_service
}
NFT
    cat > "$FW4_INPUT_INCLUDE" <<'NFT'
iifname @weig_remote_gate_auth_ping_ifname ip saddr @weig_remote_gate_auth_ipv4 icmp type echo-request counter accept comment "!WeiG Remote Gate: authorized IPv4 ICMP"
iifname @weig_remote_gate_protected_ifname_v4 icmp type echo-request counter drop comment "!WeiG Remote Gate: protected IPv4 ICMP"
iifname @weig_remote_gate_auth_ifname ip saddr @weig_remote_gate_auth_ipv4 udp dport @weig_remote_gate_auth_udp_port counter accept comment "!WeiG Remote Gate: authorized IPv4 WireGuard"
iifname @weig_remote_gate_protected_ifname_v4 udp dport @weig_remote_gate_protected_udp_port counter drop comment "!WeiG Remote Gate: protected IPv4 WireGuard"

iifname @weig_remote_gate_auth_ping_ifname ip6 saddr @weig_remote_gate_auth_ipv6 icmpv6 type echo-request counter accept comment "!WeiG Remote Gate: authorized IPv6 ICMP"
iifname @weig_remote_gate_protected_ifname_v6 icmpv6 type echo-request counter drop comment "!WeiG Remote Gate: protected IPv6 ICMP"
iifname @weig_remote_gate_auth_ifname ip6 saddr @weig_remote_gate_auth_ipv6 udp dport @weig_remote_gate_auth_udp_port counter accept comment "!WeiG Remote Gate: authorized IPv6 WireGuard"
iifname @weig_remote_gate_protected_ifname_v6 udp dport @weig_remote_gate_protected_udp_port counter drop comment "!WeiG Remote Gate: protected IPv6 WireGuard"
NFT
}

fw4_check_order() {
    rendered="$(fw4 -q print)" || return 1
    gate_line="$(printf '%s\n' "$rendered" | grep -n '!WeiG Remote Gate: protected IPv4 ICMP' | sed -n '1s/:.*//p')"
    [ -n "$gate_line" ] || gate_line="$(printf '%s\n' "$rendered" | grep -n '!WeiG Remote Gate: protected IPv6 ICMP' | sed -n '1s/:.*//p')"
    state_line="$(printf '%s\n' "$rendered" | grep -n '!fw4: Handle inbound flows' | sed -n '1s/:.*//p')"
    [ -n "$gate_line" ] && [ -n "$state_line" ] && [ "$gate_line" -lt "$state_line" ]
}

fw3_ensure_set() {
    name="$1"; family="$2"
    if ipset list "$name" >/dev/null 2>&1; then
        return 0
    fi
    ipset create "$name" hash:ip family "$family" timeout 1800 >/dev/null
}

fw3_ensure_sets() {
    fw3_ensure_set "$FW3_AUTH_SET_V4" inet
    if fw3_ipv6_capable; then
        fw3_ensure_set "$FW3_AUTH_SET_V6" inet6
    fi
}

clear_auth_vars() {
    AUTH_IP=""
    AUTH_DEVICE=""
    AUTH_PORT="0"
    AUTH_EXPIRES="0"
    AUTH_REMAINING="0"
    AUTH_FAMILY=""
    AUTH_SCOPE=""
}

read_auth() {
    clear_auth_vars
    [ -r "$AUTH_FILE" ] || return 0
    AUTH_IP="$(sed -n '1p' "$AUTH_FILE")"
    AUTH_DEVICE="$(sed -n '2p' "$AUTH_FILE")"
    AUTH_PORT="$(sed -n '3p' "$AUTH_FILE")"
    AUTH_EXPIRES="$(sed -n '4p' "$AUTH_FILE")"
    AUTH_FAMILY="$(sed -n '5p' "$AUTH_FILE")"
    AUTH_SCOPE="$(sed -n '6p' "$AUTH_FILE")"
    [ -n "$AUTH_FAMILY" ] || AUTH_FAMILY="ipv4"
    [ -n "$AUTH_SCOPE" ] || AUTH_SCOPE="wg_ping"
    now="$(date +%s)"

    valid_family "$AUTH_FAMILY" || { clear_auth_vars; rm -f "$AUTH_FILE"; return 0; }
    valid_scope "$AUTH_SCOPE" || { clear_auth_vars; rm -f "$AUTH_FILE"; return 0; }
    if [ "$AUTH_FAMILY" = "ipv4" ]; then
        valid_ipv4 "$AUTH_IP" || { clear_auth_vars; rm -f "$AUTH_FILE"; return 0; }
    else
        valid_ipv6 "$AUTH_IP" || { clear_auth_vars; rm -f "$AUTH_FILE"; return 0; }
    fi
    if ! valid_device "$AUTH_DEVICE" || ! valid_uint "$AUTH_PORT" || ! valid_uint "$AUTH_EXPIRES" || [ "$AUTH_EXPIRES" -le "$now" ]; then
        clear_auth_vars
        rm -f "$AUTH_FILE"
        return 0
    fi
    AUTH_REMAINING="$((AUTH_EXPIRES - now))"
}

auth_policy_current() {
    [ -n "$AUTH_IP" ] || return 1
    case "$AUTH_FAMILY" in
        ipv4) device_file="$DEVICES_V4_FILE" ;;
        ipv6) device_file="$DEVICES_V6_FILE" ;;
        *) return 1 ;;
    esac
    grep -Fqx "$AUTH_DEVICE" "$device_file" 2>/dev/null || return 1
    grep -Fqx "$AUTH_PORT" "$PORTS_FILE" 2>/dev/null || return 1
    return 0
}

reconcile_auth_policy() {
    read_auth
    [ -n "$AUTH_IP" ] || return 0
    auth_policy_current && return 0
    logger -t "$TAG" "temporary authorization revoked because protected WAN/port policy changed" 2>/dev/null || true
    rm -f "$AUTH_FILE"
    clear_auth_vars
}

fw3_remove_jump_v4() {
    while iptables -C INPUT -j "$FW3_CHAIN_V4" >/dev/null 2>&1; do
        iptables -D INPUT -j "$FW3_CHAIN_V4" >/dev/null 2>&1 || break
    done
}

fw3_remove_jump_v6() {
    command -v ip6tables >/dev/null 2>&1 || return 0
    while ip6tables -C INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1; do
        ip6tables -D INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1 || break
    done
}

fw3_rebuild_v4() {
    iptables -N "$FW3_CHAIN_V4" >/dev/null 2>&1 || true
    fw3_remove_jump_v4
    iptables -F "$FW3_CHAIN_V4"
    iptables -I INPUT 1 -j "$FW3_CHAIN_V4"
    ipset flush "$FW3_AUTH_SET_V4" >/dev/null 2>&1 || true

    read_auth
    if [ "$AUTH_FAMILY" = "ipv4" ] && [ -n "$AUTH_IP" ]; then
        ipset -exist add "$FW3_AUTH_SET_V4" "$AUTH_IP" timeout "$AUTH_REMAINING" >/dev/null
        if [ "$AUTH_SCOPE" = "wg_ping" ]; then
            iptables -A "$FW3_CHAIN_V4" -i "$AUTH_DEVICE" -p icmp --icmp-type echo-request -m set --match-set "$FW3_AUTH_SET_V4" src -j ACCEPT
        fi
        iptables -A "$FW3_CHAIN_V4" -i "$AUTH_DEVICE" -p udp --dport "$AUTH_PORT" -m set --match-set "$FW3_AUTH_SET_V4" src -j ACCEPT
    fi

    while IFS= read -r dev; do
        [ -n "$dev" ] || continue
        valid_device "$dev" || continue
        iptables -A "$FW3_CHAIN_V4" -i "$dev" -p icmp --icmp-type echo-request -j DROP
        while IFS= read -r port; do
            [ -n "$port" ] || continue
            valid_uint "$port" || continue
            [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || continue
            iptables -A "$FW3_CHAIN_V4" -i "$dev" -p udp --dport "$port" -j DROP
        done < "$PORTS_FILE"
    done < "$DEVICES_V4_FILE"
    iptables -A "$FW3_CHAIN_V4" -j RETURN
}

fw3_rebuild_v6() {
    fw3_ipv6_capable || {
        fw3_remove_jump_v6
        return 0
    }
    if [ ! -s "$DEVICES_V6_FILE" ]; then
        fw3_remove_jump_v6
        ip6tables -F "$FW3_CHAIN_V6" >/dev/null 2>&1 || true
        ip6tables -X "$FW3_CHAIN_V6" >/dev/null 2>&1 || true
        ipset flush "$FW3_AUTH_SET_V6" >/dev/null 2>&1 || true
        return 0
    fi
    ip6tables -N "$FW3_CHAIN_V6" >/dev/null 2>&1 || true
    fw3_remove_jump_v6
    ip6tables -F "$FW3_CHAIN_V6"
    ip6tables -I INPUT 1 -j "$FW3_CHAIN_V6"
    ipset flush "$FW3_AUTH_SET_V6" >/dev/null 2>&1 || true

    read_auth
    if [ "$AUTH_FAMILY" = "ipv6" ] && [ -n "$AUTH_IP" ]; then
        ipset -exist add "$FW3_AUTH_SET_V6" "$AUTH_IP" timeout "$AUTH_REMAINING" >/dev/null
        if [ "$AUTH_SCOPE" = "wg_ping" ]; then
            ip6tables -A "$FW3_CHAIN_V6" -i "$AUTH_DEVICE" -p ipv6-icmp --icmpv6-type echo-request -m set --match-set "$FW3_AUTH_SET_V6" src -j ACCEPT
        fi
        ip6tables -A "$FW3_CHAIN_V6" -i "$AUTH_DEVICE" -p udp --dport "$AUTH_PORT" -m set --match-set "$FW3_AUTH_SET_V6" src -j ACCEPT
    fi

    while IFS= read -r dev; do
        [ -n "$dev" ] || continue
        valid_device "$dev" || continue
        # Only Echo Request is controlled. NDP, RA, Packet Too Big and all other
        # ICMPv6 types immediately fall through to the original fw3 policy.
        ip6tables -A "$FW3_CHAIN_V6" -i "$dev" -p ipv6-icmp --icmpv6-type echo-request -j DROP
        while IFS= read -r port; do
            [ -n "$port" ] || continue
            valid_uint "$port" || continue
            [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || continue
            ip6tables -A "$FW3_CHAIN_V6" -i "$dev" -p udp --dport "$port" -j DROP
        done < "$PORTS_FILE"
    done < "$DEVICES_V6_FILE"
    ip6tables -A "$FW3_CHAIN_V6" -j RETURN
}

fw3_rebuild() {
    fw3_ensure_sets
    reconcile_auth_policy
    fw3_rebuild_v4
    fw3_rebuild_v6
}

fw3_verify() {
    iptables -C INPUT -j "$FW3_CHAIN_V4" >/dev/null 2>&1 || return 1
    first_rule="$(iptables -S INPUT | sed -n '2p')"
    [ "$first_rule" = "-A INPUT -j $FW3_CHAIN_V4" ] || return 1
    if [ -s "$DEVICES_V6_FILE" ]; then
        fw3_ipv6_capable || return 1
        ip6tables -C INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1 || return 1
        first_rule6="$(ip6tables -S INPUT | sed -n '2p')"
        [ "$first_rule6" = "-A INPUT -j $FW3_CHAIN_V6" ] || return 1
    elif command -v ip6tables >/dev/null 2>&1; then
        ip6tables -C INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1 && return 1
    fi
}

fw4_flush_set() { nft flush set inet fw4 "$1" >/dev/null 2>&1 || true; }

fw4_add_lines() {
    setname="$1"; file="$2"; kind="$3"
    [ -r "$file" ] || return 0
    while IFS= read -r value; do
        [ -n "$value" ] || continue
        case "$kind" in
            ifname)
                valid_device "$value" || continue
                nft -f - <<EOF
add element inet fw4 $setname { "$value" }
EOF
                ;;
            port)
                valid_uint "$value" || continue
                [ "$value" -ge 1 ] && [ "$value" -le 65535 ] || continue
                nft -f - <<EOF
add element inet fw4 $setname { $value }
EOF
                ;;
        esac
    done < "$file"
}

fw4_restore_sets() {
    nft list set inet fw4 weig_remote_gate_protected_ifname_v4 >/dev/null 2>&1 || return 1
    for s in \
        weig_remote_gate_protected_ifname_v4 \
        weig_remote_gate_protected_ifname_v6 \
        weig_remote_gate_protected_udp_port \
        weig_remote_gate_auth_ipv4 \
        weig_remote_gate_auth_ipv6 \
        weig_remote_gate_auth_ifname \
        weig_remote_gate_auth_ping_ifname \
        weig_remote_gate_auth_udp_port
    do
        fw4_flush_set "$s"
    done
    fw4_add_lines weig_remote_gate_protected_ifname_v4 "$DEVICES_V4_FILE" ifname
    fw4_add_lines weig_remote_gate_protected_ifname_v6 "$DEVICES_V6_FILE" ifname
    fw4_add_lines weig_remote_gate_protected_udp_port "$PORTS_FILE" port

    reconcile_auth_policy
    [ -n "$AUTH_IP" ] || return 0
    auth_set="weig_remote_gate_auth_ipv4"
    [ "$AUTH_FAMILY" = "ipv6" ] && auth_set="weig_remote_gate_auth_ipv6"
    nft -f - <<EOF
add element inet fw4 $auth_set { $AUTH_IP timeout ${AUTH_REMAINING}s }
add element inet fw4 weig_remote_gate_auth_ifname { "$AUTH_DEVICE" }
add element inet fw4 weig_remote_gate_auth_udp_port { $AUTH_PORT }
EOF
    if [ "$AUTH_SCOPE" = "wg_ping" ]; then
        nft -f - <<EOF
add element inet fw4 weig_remote_gate_auth_ping_ifname { "$AUTH_DEVICE" }
EOF
    fi
}

install_rules() {
    ensure_state
    b="$(detect_backend)" || fail "unsupported firewall: need fw4+nft or fw3+iptables+ipset"
    printf '%s\n' "$b" > "$BACKEND_FILE"
    chmod 600 "$BACKEND_FILE"
    register_include "$b"
    case "$b" in
        fw4-nftables)
            write_fw4_includes
            fw4 -q check || fail "firewall4 rendered ruleset check failed"
            fw4_check_order || fail "Remote Gate fw4 rules are not before conntrack established handling"
            /etc/init.d/firewall reload
            restore_rules
            fw4_check_order || fail "Remote Gate fw4 rule order validation failed after reload"
            ;;
        fw3-iptables)
            fw3_ensure_sets
            restore_rules
            fw3_verify || fail "Remote Gate fw3 INPUT guard is not first"
            ;;
    esac
    logger -t "$TAG" "installed firewall backend $b" 2>/dev/null || true
    printf '%s\n' "$b"
}

normalize_list_to_file() {
    input="$1"; kind="$2"; out="$3"; tmp="${out}.tmp.$$"
    : > "$tmp"
    for value in $input; do
        case "$kind" in
            device) valid_device "$value" || fail "invalid protected device: $value" ;;
            port)
                valid_uint "$value" || fail "invalid protected UDP port: $value"
                [ "$value" -ge 1 ] && [ "$value" -le 65535 ] || fail "UDP port out of range: $value"
                ;;
        esac
        printf '%s\n' "$value" >> "$tmp"
    done
    sort -u "$tmp" > "$out"
    rm -f "$tmp"
    chmod 600 "$out"
}

sync_policy() {
    ensure_state
    case "$#" in
        2)
            v4_devices="$1"; v6_devices=""; ports="$2"
            ;;
        3)
            v4_devices="$1"; v6_devices="$2"; ports="$3"
            ;;
        *) fail "usage: $0 sync <ipv4-devices> [ipv6-devices] <wireguard-udp-ports>" ;;
    esac
    if [ -n "$v6_devices" ] && ! fw3_ipv6_capable && [ "$(backend 2>/dev/null || true)" = "fw3-iptables" ]; then
        fail "IPv6 Gate requested but ip6tables/ipset inet6 support is unavailable"
    fi
    normalize_list_to_file "$v4_devices" device "$DEVICES_V4_FILE"
    normalize_list_to_file "$v6_devices" device "$DEVICES_V6_FILE"
    normalize_list_to_file "$ports" port "$PORTS_FILE"
    restore_rules
}

activate() {
    source_ip="$1"; family="$2"; scope="$3"; device="$4"; port="$5"; ttl="$6"
    valid_family "$family" || fail "invalid IP family"
    valid_scope "$scope" || fail "invalid access scope"
    if [ "$family" = "ipv4" ]; then
        valid_ipv4 "$source_ip" || fail "invalid IPv4"
        device_file="$DEVICES_V4_FILE"
    else
        valid_ipv6 "$source_ip" || fail "invalid IPv6"
        [ "$(backend 2>/dev/null || true)" != "fw3-iptables" ] || fw3_ipv6_capable || fail "IPv6 Gate unavailable"
        device_file="$DEVICES_V6_FILE"
    fi
    valid_device "$device" || fail "invalid WAN device"
    valid_uint "$port" || fail "invalid UDP port"
    valid_uint "$ttl" || fail "invalid TTL"
    [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || fail "UDP port out of range"
    valid_ttl "$ttl" || fail "TTL must be 1m/5m/15m/30m or 30m steps up to 12h"
    ip link show "$device" >/dev/null 2>&1 || fail "WAN device does not exist: $device"
    grep -Fqx "$device" "$device_file" 2>/dev/null || fail "WAN device is not in the protected $family policy: $device"
    grep -Fqx "$port" "$PORTS_FILE" 2>/dev/null || fail "UDP port is not a discovered WireGuard listen port: $port"

    now="$(date +%s)"; expires="$((now + ttl))"
    {
        printf '%s\n' "$source_ip"
        printf '%s\n' "$device"
        printf '%s\n' "$port"
        printf '%s\n' "$expires"
        printf '%s\n' "$family"
        printf '%s\n' "$scope"
    } > "$AUTH_FILE"
    chmod 600 "$AUTH_FILE"
    restore_rules
    logger -t "$TAG" "temporary $family/$scope authorization active on $device UDP/$port (${ttl}s)" 2>/dev/null || true
}

clear_auth() {
    rm -f "$AUTH_FILE"
    b="$(backend 2>/dev/null || true)"
    case "$b" in
        fw3-iptables) fw3_rebuild ;;
        fw4-nftables) fw4_restore_sets ;;
    esac
    logger -t "$TAG" "temporary authorization cleared" 2>/dev/null || true
}

restore_rules() {
    ensure_state
    b="$(backend)" || return 1
    case "$b" in
        fw3-iptables) fw3_rebuild ;;
        fw4-nftables) fw4_restore_sets ;;
        *) return 1 ;;
    esac
}

ready_state() {
    b="$(backend 2>/dev/null || true)"
    case "$b" in
        fw3-iptables) fw3_verify >/dev/null 2>&1 ;;
        fw4-nftables)
            nft list set inet fw4 weig_remote_gate_protected_ifname_v4 >/dev/null 2>&1 && fw4_check_order >/dev/null 2>&1
            ;;
        *) return 1 ;;
    esac
}

status_json() {
    ensure_state
    b="$(backend 2>/dev/null || printf 'unsupported')"
    ready=false
    ready_state && ready=true
    protected_v4="$(awk 'END{print NR+0}' "$DEVICES_V4_FILE" 2>/dev/null)"
    protected_v6="$(awk 'END{print NR+0}' "$DEVICES_V6_FILE" 2>/dev/null)"
    protected_ports="$(awk 'END{print NR+0}' "$PORTS_FILE" 2>/dev/null)"
    ipv6_capable=false
    case "$b" in
        fw3-iptables) fw3_ipv6_capable && ipv6_capable=true ;;
        fw4-nftables) ipv6_capable=true ;;
    esac

    reconcile_auth_policy
    active=false
    if [ -n "$AUTH_IP" ]; then
        case "$b:$AUTH_FAMILY" in
            fw3-iptables:ipv4) ipset test "$FW3_AUTH_SET_V4" "$AUTH_IP" >/dev/null 2>&1 && active=true ;;
            fw3-iptables:ipv6) ipset test "$FW3_AUTH_SET_V6" "$AUTH_IP" >/dev/null 2>&1 && active=true ;;
            fw4-nftables:ipv4) nft list set inet fw4 weig_remote_gate_auth_ipv4 2>/dev/null | grep -Fq "$AUTH_IP" && active=true ;;
            fw4-nftables:ipv6) nft list set inet fw4 weig_remote_gate_auth_ipv6 2>/dev/null | grep -Fq "$AUTH_IP" && active=true ;;
        esac
    fi
    if [ "$active" != "true" ]; then
        clear_auth_vars
        rm -f "$AUTH_FILE" 2>/dev/null || true
    fi

    printf '{"backend":"%s","ready":%s,"ipv6_capable":%s,"active":%s,"family":"%s","scope":"%s","source_ip":"%s","device":"%s","wg_port":%s,"expires_in":%s,"protected_devices_v4":%s,"protected_devices_v6":%s,"protected_ports":%s}\n' \
        "$b" "$ready" "$ipv6_capable" "$active" "$AUTH_FAMILY" "$AUTH_SCOPE" "$AUTH_IP" "$AUTH_DEVICE" "$AUTH_PORT" "$AUTH_REMAINING" "$protected_v4" "$protected_v6" "$protected_ports"
}

uninstall_rules() {
    b="$(backend 2>/dev/null || true)"
    unregister_include
    case "$b" in
        fw3-iptables)
            fw3_remove_jump_v4
            fw3_remove_jump_v6
            iptables -F "$FW3_CHAIN_V4" >/dev/null 2>&1 || true
            iptables -X "$FW3_CHAIN_V4" >/dev/null 2>&1 || true
            if command -v ip6tables >/dev/null 2>&1; then
                ip6tables -F "$FW3_CHAIN_V6" >/dev/null 2>&1 || true
                ip6tables -X "$FW3_CHAIN_V6" >/dev/null 2>&1 || true
            fi
            ipset destroy "$FW3_AUTH_SET_V4" >/dev/null 2>&1 || true
            ipset destroy "$FW3_AUTH_SET_V6" >/dev/null 2>&1 || true
            ;;
        fw4-nftables)
            rm -f "$FW4_TABLE_INCLUDE" "$FW4_INPUT_INCLUDE"
            fw4 -q check >/dev/null 2>&1 || fail "firewall4 check failed after removing Remote Gate includes"
            /etc/init.d/firewall reload
            ;;
    esac
    rm -f "$BACKEND_FILE" "$AUTH_FILE" "$DEVICES_V4_FILE" "$DEVICES_V6_FILE" "$LEGACY_DEVICES_FILE" "$PORTS_FILE"
    logger -t "$TAG" "firewall integration removed; original firewall behavior restored" 2>/dev/null || true
}

case "${1:-}" in
    detect) detect_backend || { printf '%s\n' 'unsupported'; exit 1; } ;;
    ipv6-capable)
        b="$(detect_backend 2>/dev/null || true)"
        case "$b" in
            fw4-nftables) printf '%s\n' yes ;;
            fw3-iptables) fw3_ipv6_capable && printf '%s\n' yes || { printf '%s\n' no; exit 1; } ;;
            *) printf '%s\n' no; exit 1 ;;
        esac
        ;;
    install) install_rules ;;
    sync) shift; sync_policy "$@" ;;
    activate)
        case "$#" in
            5)
                activate "$2" ipv4 wg_ping "$3" "$4" "$5"
                ;;
            7)
                activate "$2" "$3" "$4" "$5" "$6" "$7"
                ;;
            *) fail "usage: $0 activate <source> [family scope] <wan-device> <udp-port> <ttl-seconds>" ;;
        esac
        ;;
    clear) clear_auth ;;
    restore) restore_rules ;;
    status-json) status_json ;;
    uninstall) uninstall_rules ;;
    *) fail "usage: $0 detect|ipv6-capable|install|sync|activate|clear|restore|status-json|uninstall" ;;
esac
