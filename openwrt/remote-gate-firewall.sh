#!/bin/sh
set -eu

STATE_ROOT="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}/firewall"
BACKEND_FILE="$STATE_ROOT/backend"
DEVICES_FILE="$STATE_ROOT/protected-devices"
PORTS_FILE="$STATE_ROOT/protected-ports"
AUTH_FILE="$STATE_ROOT/authorization"
FW3_CHAIN="WEIG_REMOTE_GATE"
FW3_AUTH_SET="weig_remote_gate_auth_v4"
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

valid_device() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }

ensure_state() {
    mkdir -p "$STATE_ROOT"
    chmod 700 "$STATE_ROOT" 2>/dev/null || true
    [ -f "$DEVICES_FILE" ] || : > "$DEVICES_FILE"
    [ -f "$PORTS_FILE" ] || : > "$PORTS_FILE"
    chmod 600 "$DEVICES_FILE" "$PORTS_FILE" 2>/dev/null || true
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
set weig_remote_gate_protected_ifname {
    type ifname
}

set weig_remote_gate_protected_udp_port {
    type inet_service
}

set weig_remote_gate_auth_ipv4 {
    type ipv4_addr
    flags timeout
}

set weig_remote_gate_auth_ifname {
    type ifname
}

set weig_remote_gate_auth_udp_port {
    type inet_service
}
NFT
    cat > "$FW4_INPUT_INCLUDE" <<'NFT'
iifname @weig_remote_gate_auth_ifname ip saddr @weig_remote_gate_auth_ipv4 icmp type echo-request counter accept comment "!WeiG Remote Gate: authorized ICMP"
iifname @weig_remote_gate_protected_ifname icmp type echo-request counter drop comment "!WeiG Remote Gate: protected ICMP"
iifname @weig_remote_gate_auth_ifname ip saddr @weig_remote_gate_auth_ipv4 udp dport @weig_remote_gate_auth_udp_port counter accept comment "!WeiG Remote Gate: authorized WireGuard"
iifname @weig_remote_gate_protected_ifname udp dport @weig_remote_gate_protected_udp_port counter drop comment "!WeiG Remote Gate: protected WireGuard"
NFT
}

fw4_check_order() {
    rendered="$(fw4 -q print)" || return 1
    gate_line="$(printf '%s\n' "$rendered" | grep -n '!WeiG Remote Gate: protected ICMP' | sed -n '1s/:.*//p')"
    state_line="$(printf '%s\n' "$rendered" | grep -n '!fw4: Handle inbound flows' | sed -n '1s/:.*//p')"
    [ -n "$gate_line" ] && [ -n "$state_line" ] && [ "$gate_line" -lt "$state_line" ]
}

fw3_ensure_set() {
    ipset -exist create "$FW3_AUTH_SET" hash:ip family inet timeout 1800 >/dev/null
}

read_auth() {
    AUTH_IP=""; AUTH_DEVICE=""; AUTH_PORT="0"; AUTH_EXPIRES="0"; AUTH_REMAINING="0"
    [ -r "$AUTH_FILE" ] || return 0
    AUTH_IP="$(sed -n '1p' "$AUTH_FILE")"
    AUTH_DEVICE="$(sed -n '2p' "$AUTH_FILE")"
    AUTH_PORT="$(sed -n '3p' "$AUTH_FILE")"
    AUTH_EXPIRES="$(sed -n '4p' "$AUTH_FILE")"
    now="$(date +%s)"
    if ! valid_ipv4 "$AUTH_IP" || ! valid_device "$AUTH_DEVICE" || ! valid_uint "$AUTH_PORT" || ! valid_uint "$AUTH_EXPIRES" || [ "$AUTH_EXPIRES" -le "$now" ]; then
        AUTH_IP=""; AUTH_DEVICE=""; AUTH_PORT="0"; AUTH_EXPIRES="0"; AUTH_REMAINING="0"
        rm -f "$AUTH_FILE"
        return 0
    fi
    AUTH_REMAINING="$((AUTH_EXPIRES - now))"
}

fw3_remove_jump() {
    while iptables -C INPUT -j "$FW3_CHAIN" >/dev/null 2>&1; do
        iptables -D INPUT -j "$FW3_CHAIN" >/dev/null 2>&1 || break
    done
}

fw3_rebuild() {
    fw3_ensure_set
    iptables -N "$FW3_CHAIN" >/dev/null 2>&1 || true
    fw3_remove_jump
    iptables -F "$FW3_CHAIN"
    iptables -I INPUT 1 -j "$FW3_CHAIN"

    # v0.2 intentionally permits exactly one active source. Rebuild the auth set
    # from the single persisted authorization so an older client is revoked now,
    # not when its previous timeout would otherwise expire.
    ipset flush "$FW3_AUTH_SET" >/dev/null 2>&1 || true
    read_auth
    if [ -n "$AUTH_IP" ]; then
        ipset -exist add "$FW3_AUTH_SET" "$AUTH_IP" timeout "$AUTH_REMAINING" >/dev/null
        iptables -A "$FW3_CHAIN" -i "$AUTH_DEVICE" -p icmp --icmp-type echo-request -m set --match-set "$FW3_AUTH_SET" src -j ACCEPT
        iptables -A "$FW3_CHAIN" -i "$AUTH_DEVICE" -p udp --dport "$AUTH_PORT" -m set --match-set "$FW3_AUTH_SET" src -j ACCEPT
    fi

    while IFS= read -r dev; do
        [ -n "$dev" ] || continue
        valid_device "$dev" || continue
        iptables -A "$FW3_CHAIN" -i "$dev" -p icmp --icmp-type echo-request -j DROP
        while IFS= read -r port; do
            [ -n "$port" ] || continue
            valid_uint "$port" || continue
            [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || continue
            iptables -A "$FW3_CHAIN" -i "$dev" -p udp --dport "$port" -j DROP
        done < "$PORTS_FILE"
    done < "$DEVICES_FILE"
    iptables -A "$FW3_CHAIN" -j RETURN
}

fw3_verify() {
    iptables -C INPUT -j "$FW3_CHAIN" >/dev/null 2>&1 || return 1
    first_rule="$(iptables -S INPUT | sed -n '2p')"
    [ "$first_rule" = "-A INPUT -j $FW3_CHAIN" ]
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
    nft list set inet fw4 weig_remote_gate_protected_ifname >/dev/null 2>&1 || return 1
    for s in weig_remote_gate_protected_ifname weig_remote_gate_protected_udp_port weig_remote_gate_auth_ipv4 weig_remote_gate_auth_ifname weig_remote_gate_auth_udp_port; do
        fw4_flush_set "$s"
    done
    fw4_add_lines weig_remote_gate_protected_ifname "$DEVICES_FILE" ifname
    fw4_add_lines weig_remote_gate_protected_udp_port "$PORTS_FILE" port

    read_auth
    if [ -n "$AUTH_IP" ]; then
        nft -f - <<EOF
add element inet fw4 weig_remote_gate_auth_ipv4 { $AUTH_IP timeout ${AUTH_REMAINING}s }
add element inet fw4 weig_remote_gate_auth_ifname { "$AUTH_DEVICE" }
add element inet fw4 weig_remote_gate_auth_udp_port { $AUTH_PORT }
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
            fw3_ensure_set
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
            port) valid_uint "$value" || fail "invalid protected UDP port: $value"; [ "$value" -ge 1 ] && [ "$value" -le 65535 ] || fail "UDP port out of range: $value" ;;
        esac
        printf '%s\n' "$value" >> "$tmp"
    done
    sort -u "$tmp" > "$out"
    rm -f "$tmp"
    chmod 600 "$out"
}

sync_policy() {
    [ "$#" -eq 2 ] || fail "usage: $0 sync <public-wan-devices> <wireguard-udp-ports>"
    ensure_state
    normalize_list_to_file "$1" device "$DEVICES_FILE"
    normalize_list_to_file "$2" port "$PORTS_FILE"
    restore_rules
}

activate() {
    source_ip="$1"; device="$2"; port="$3"; ttl="$4"
    valid_ipv4 "$source_ip" || fail "invalid IPv4"
    valid_device "$device" || fail "invalid WAN device"
    valid_uint "$port" || fail "invalid UDP port"
    valid_uint "$ttl" || fail "invalid TTL"
    [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || fail "UDP port out of range"
    [ "$ttl" -ge 30 ] && [ "$ttl" -le 1800 ] || fail "TTL must be between 30 and 1800 seconds"
    ip link show "$device" >/dev/null 2>&1 || fail "WAN device does not exist: $device"
    grep -Fqx "$device" "$DEVICES_FILE" 2>/dev/null || fail "WAN device is not in the protected public-WAN policy: $device"
    grep -Fqx "$port" "$PORTS_FILE" 2>/dev/null || fail "UDP port is not a discovered WireGuard listen port: $port"

    now="$(date +%s)"; expires="$((now + ttl))"
    {
        printf '%s\n' "$source_ip"
        printf '%s\n' "$device"
        printf '%s\n' "$port"
        printf '%s\n' "$expires"
    } > "$AUTH_FILE"
    chmod 600 "$AUTH_FILE"
    restore_rules
    logger -t "$TAG" "temporary authorization active for $source_ip on $device UDP/$port (${ttl}s)" 2>/dev/null || true
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
            nft list set inet fw4 weig_remote_gate_protected_ifname >/dev/null 2>&1 && fw4_check_order >/dev/null 2>&1
            ;;
        *) return 1 ;;
    esac
}

status_json() {
    ensure_state
    b="$(backend 2>/dev/null || printf 'unsupported')"
    ready=false
    ready_state && ready=true
    protected_devices="$(awk 'END{print NR+0}' "$DEVICES_FILE" 2>/dev/null)"
    protected_ports="$(awk 'END{print NR+0}' "$PORTS_FILE" 2>/dev/null)"
    read_auth
    active=false
    if [ -n "$AUTH_IP" ]; then
        case "$b" in
            fw3-iptables) ipset test "$FW3_AUTH_SET" "$AUTH_IP" >/dev/null 2>&1 && active=true ;;
            fw4-nftables) nft list set inet fw4 weig_remote_gate_auth_ipv4 2>/dev/null | grep -Fq "$AUTH_IP" && active=true ;;
        esac
    fi
    if [ "$active" != "true" ]; then
        AUTH_IP=""; AUTH_DEVICE=""; AUTH_PORT="0"; AUTH_REMAINING="0"
        rm -f "$AUTH_FILE" 2>/dev/null || true
    fi
    printf '{"backend":"%s","ready":%s,"active":%s,"source_ip":"%s","device":"%s","wg_port":%s,"expires_in":%s,"protected_devices":%s,"protected_ports":%s}\n' \
        "$b" "$ready" "$active" "$AUTH_IP" "$AUTH_DEVICE" "$AUTH_PORT" "$AUTH_REMAINING" "$protected_devices" "$protected_ports"
}

uninstall_rules() {
    b="$(backend 2>/dev/null || true)"
    unregister_include
    case "$b" in
        fw3-iptables)
            fw3_remove_jump
            iptables -F "$FW3_CHAIN" >/dev/null 2>&1 || true
            iptables -X "$FW3_CHAIN" >/dev/null 2>&1 || true
            ipset destroy "$FW3_AUTH_SET" >/dev/null 2>&1 || true
            ;;
        fw4-nftables)
            rm -f "$FW4_TABLE_INCLUDE" "$FW4_INPUT_INCLUDE"
            fw4 -q check >/dev/null 2>&1 || fail "firewall4 check failed after removing Remote Gate includes"
            /etc/init.d/firewall reload
            ;;
    esac
    rm -f "$BACKEND_FILE" "$AUTH_FILE" "$DEVICES_FILE" "$PORTS_FILE"
    logger -t "$TAG" "firewall integration removed; original firewall behavior restored" 2>/dev/null || true
}

case "${1:-}" in
    detect) detect_backend || { printf '%s\n' 'unsupported'; exit 1; } ;;
    install) install_rules ;;
    sync) shift; sync_policy "$@" ;;
    activate)
        [ "$#" -eq 5 ] || fail "usage: $0 activate <source-ipv4> <wan-device> <udp-port> <ttl-seconds>"
        activate "$2" "$3" "$4" "$5"
        ;;
    clear) clear_auth ;;
    restore) restore_rules ;;
    status-json) status_json ;;
    uninstall) uninstall_rules ;;
    *) fail "usage: $0 detect|install|sync|activate|clear|restore|status-json|uninstall" ;;
esac
