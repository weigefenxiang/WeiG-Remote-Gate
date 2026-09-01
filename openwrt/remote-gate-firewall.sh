#!/bin/sh
set -eu

STATE_ROOT="${REMOTE_GATE_STATE_DIR:-/etc/remote-gate-state}/firewall"
BACKEND_FILE="$STATE_ROOT/backend"
DEVICES_V4_FILE="$STATE_ROOT/protected-devices-v4"
DEVICES_V6_FILE="$STATE_ROOT/protected-devices-v6"
LEGACY_DEVICES_FILE="$STATE_ROOT/protected-devices"
PORTS_FILE="$STATE_ROOT/protected-ports"
MAPPED_INGRESS_V4_FILE="$STATE_ROOT/mapped-ingress-v4"
MAPPED_CONTROL_V4_FILE="$STATE_ROOT/mapped-control-v4"
LEGACY_AUTH_FILE="$STATE_ROOT/authorization"
AUTH_FILE_V4="$STATE_ROOT/authorization-ipv4"
AUTH_FILE_V6="$STATE_ROOT/authorization-ipv6"
AUTH_DIR_V4="$STATE_ROOT/authorization-ipv4.d"
AUTH_DIR_V6="$STATE_ROOT/authorization-ipv6.d"
VERIFY_FILE_V4="$STATE_ROOT/verification-ipv4"
VERIFY_FILE_V6="$STATE_ROOT/verification-ipv6"
FW3_CHAIN_V4="WEIG_REMOTE_GATE"
FW3_CHAIN_V6="WEIG_REMOTE_GATE_V6"
FW3_AUTH_SET_V4="weig_remote_gate_auth_v4"
FW3_AUTH_SET_V6="weig_remote_gate_auth_v6"
FW3_VERIFY_SET_V4="weig_remote_gate_verify_v4"
FW3_VERIFY_SET_V6="weig_remote_gate_verify_v6"
FW4_TABLE_INCLUDE="/usr/share/nftables.d/table-pre/90-weig-remote-gate-sets.nft"
FW4_INPUT_INCLUDE="/usr/share/nftables.d/chain-pre/input/90-weig-remote-gate.nft"
INCLUDE_SCRIPT="/usr/lib/remote-gate/remote-gate-firewall-include.sh"
RETURN_HELPER="${REMOTE_GATE_RETURN_HELPER:-/etc/hotplug.d/iface/95-remote-gate}"
VERIFY_CANDIDATE_SECONDS="${REMOTE_GATE_VERIFY_CANDIDATE_SECONDS:-8}"
VERIFY_DISCOVERY_SECONDS="${REMOTE_GATE_VERIFY_DISCOVERY_SECONDS:-12}"
case "$VERIFY_CANDIDATE_SECONDS" in ''|*[!0-9]*) VERIFY_CANDIDATE_SECONDS=8 ;; esac
case "$VERIFY_DISCOVERY_SECONDS" in ''|*[!0-9]*) VERIFY_DISCOVERY_SECONDS=12 ;; esac
[ "$VERIFY_CANDIDATE_SECONDS" -ge 1 ] && [ "$VERIFY_CANDIDATE_SECONDS" -le 30 ] || VERIFY_CANDIDATE_SECONDS=8
[ "$VERIFY_DISCOVERY_SECONDS" -ge 1 ] && [ "$VERIFY_DISCOVERY_SECONDS" -le 30 ] || VERIFY_DISCOVERY_SECONDS=12
TAG="remote-gate"

fail() { logger -t "$TAG" "$*" 2>/dev/null || true; printf 'ERROR: %s\n' "$*" >&2; exit 1; }

valid_ipv4() {
    printf '%s\n' "$1" | awk -F. '
        NF != 4 { exit 1 }
        { for (i=1; i<=4; i++) if ($i !~ /^[0-9]+$/ || $i < 0 || $i > 255) exit 1 }
    '
}
valid_ipv6() {
    case "$1" in *:*) ;; *) return 1 ;; esac
    case "$1" in *[!0-9A-Fa-f:.]*) return 1 ;; esac
    return 0
}
valid_device() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
valid_port() { valid_uint "$1" && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]; }
valid_family() { case "$1" in ipv4|ipv6) return 0 ;; *) return 1 ;; esac; }
valid_scope() { case "$1" in wg|wg_ping) return 0 ;; *) return 1 ;; esac; }
valid_source_kind() { case "$1" in legacy|wireguard_verified|web_verified|web_observed|web_candidate) return 0 ;; *) return 1 ;; esac; }
valid_ttl() {
    valid_uint "$1" || return 1
    case "$1" in 60|300|900|1800) return 0 ;; esac
    [ "$1" -ge 1800 ] && [ "$1" -le 43200 ] || return 1
    [ $(( $1 % 1800 )) -eq 0 ]
}

family_auth_file() {
    case "$1" in ipv4) printf '%s\n' "$AUTH_FILE_V4" ;; ipv6) printf '%s\n' "$AUTH_FILE_V6" ;; *) return 1 ;; esac
}
family_auth_dir() {
    case "$1" in ipv4) printf '%s\n' "$AUTH_DIR_V4" ;; ipv6) printf '%s\n' "$AUTH_DIR_V6" ;; *) return 1 ;; esac
}
auth_record_key() {
    printf '%s' "$1" | sed 's/[^A-Za-z0-9_.-]/_/g'
}
auth_record_file() {
    local rg_dir rg_key
    rg_dir="$(family_auth_dir "$1")" || return 1
    rg_key="$(auth_record_key "$2")"
    [ -n "$rg_key" ] || return 1
    printf '%s/%s\n' "$rg_dir" "$rg_key"
}
family_verify_file() {
    case "$1" in ipv4) printf '%s\n' "$VERIFY_FILE_V4" ;; ipv6) printf '%s\n' "$VERIFY_FILE_V6" ;; *) return 1 ;; esac
}
family_device_file() {
    case "$1" in ipv4) printf '%s\n' "$DEVICES_V4_FILE" ;; ipv6) printf '%s\n' "$DEVICES_V6_FILE" ;; *) return 1 ;; esac
}

protected_ingress_current() {
    local rg_family="$1" rg_dev="$2" rg_port="$3"
    valid_family "$rg_family" && valid_device "$rg_dev" && valid_port "$rg_port" || return 1
    grep -Fqx "$rg_port" "$PORTS_FILE" 2>/dev/null && return 0
    [ "$rg_family" = ipv4 ] || return 1
    grep -Fqx "${rg_dev}|${rg_port}" "$MAPPED_INGRESS_V4_FILE" 2>/dev/null
}

fw3_ipv6_capable() {
    command -v ip6tables >/dev/null 2>&1 || return 1
    ip6tables -m set -h >/dev/null 2>&1 || return 1
    ipset help hash:ip 2>&1 | grep -qi 'inet6' || return 1
    ipset help hash:net 2>&1 | grep -qi 'inet6' || return 1
}

migrate_family_auth_file() {
    local rg_family="$1" rg_legacy rg_source rg_target
    rg_legacy="$(family_auth_file "$rg_family")" || return 0
    [ -r "$rg_legacy" ] || return 0
    rg_source="$(sed -n '1p' "$rg_legacy")"
    case "$rg_family" in ipv4) valid_ipv4 "$rg_source" ;; ipv6) valid_ipv6 "$rg_source" ;; esac || { rm -f "$rg_legacy"; return 0; }
    rg_target="$(auth_record_file "$rg_family" "$rg_source")" || { rm -f "$rg_legacy"; return 0; }
    [ -e "$rg_target" ] || cp "$rg_legacy" "$rg_target"
    rm -f "$rg_legacy"
    chmod 600 "$rg_target" 2>/dev/null || true
}
migrate_legacy_auth() {
    if [ -r "$LEGACY_AUTH_FILE" ]; then
        local rg_family rg_target
        rg_family="$(sed -n '5p' "$LEGACY_AUTH_FILE")"
        [ -n "$rg_family" ] || rg_family=ipv4
        if valid_family "$rg_family"; then
            rg_target="$(family_auth_file "$rg_family")"
            [ -e "$rg_target" ] || cp "$LEGACY_AUTH_FILE" "$rg_target"
        fi
        rm -f "$LEGACY_AUTH_FILE"
    fi
    migrate_family_auth_file ipv4
    migrate_family_auth_file ipv6
}

ensure_state() {
    mkdir -p "$STATE_ROOT" "$AUTH_DIR_V4" "$AUTH_DIR_V6"
    chmod 700 "$STATE_ROOT" "$AUTH_DIR_V4" "$AUTH_DIR_V6" 2>/dev/null || true
    if [ ! -f "$DEVICES_V4_FILE" ] && [ -f "$LEGACY_DEVICES_FILE" ]; then
        cp "$LEGACY_DEVICES_FILE" "$DEVICES_V4_FILE"
    fi
    [ -f "$DEVICES_V4_FILE" ] || : > "$DEVICES_V4_FILE"
    [ -f "$DEVICES_V6_FILE" ] || : > "$DEVICES_V6_FILE"
    [ -f "$PORTS_FILE" ] || : > "$PORTS_FILE"
    [ -f "$MAPPED_INGRESS_V4_FILE" ] || : > "$MAPPED_INGRESS_V4_FILE"
    [ -f "$MAPPED_CONTROL_V4_FILE" ] || : > "$MAPPED_CONTROL_V4_FILE"
    chmod 600 "$DEVICES_V4_FILE" "$DEVICES_V6_FILE" "$PORTS_FILE" "$MAPPED_INGRESS_V4_FILE" "$MAPPED_CONTROL_V4_FILE" 2>/dev/null || true
    migrate_legacy_auth
}

detect_backend() {
    if command -v fw4 >/dev/null 2>&1 && command -v nft >/dev/null 2>&1; then
        printf '%s\n' 'fw4-nftables'; return 0
    fi
    if command -v fw3 >/dev/null 2>&1 && command -v iptables >/dev/null 2>&1 && command -v ipset >/dev/null 2>&1; then
        iptables -m set -h >/dev/null 2>&1 && { printf '%s\n' 'fw3-iptables'; return 0; }
    fi
    return 1
}
backend() {
    local rg_b
    if [ -r "$BACKEND_FILE" ]; then
        rg_b="$(sed -n '1p' "$BACKEND_FILE")"
        case "$rg_b" in
            fw4-nftables) command -v fw4 >/dev/null 2>&1 && command -v nft >/dev/null 2>&1 && { printf '%s\n' "$rg_b"; return 0; } ;;
            fw3-iptables) command -v fw3 >/dev/null 2>&1 && command -v iptables >/dev/null 2>&1 && command -v ipset >/dev/null 2>&1 && { printf '%s\n' "$rg_b"; return 0; } ;;
        esac
    fi
    detect_backend
}

register_include() {
    local rg_b="$1"
    command -v uci >/dev/null 2>&1 || fail "uci is required"
    uci -q delete firewall.remote_gate 2>/dev/null || true
    uci set firewall.remote_gate='include'
    uci set firewall.remote_gate.type='script'
    uci set firewall.remote_gate.path="$INCLUDE_SCRIPT"
    uci set firewall.remote_gate.enabled='1'
    case "$rg_b" in fw3-iptables) uci set firewall.remote_gate.reload='1' ;; fw4-nftables) uci set firewall.remote_gate.fw4_compatible='1' ;; esac
    uci commit firewall
}
unregister_include() {
    command -v uci >/dev/null 2>&1 || return 0
    uci -q delete firewall.remote_gate 2>/dev/null || true
    uci commit firewall 2>/dev/null || true
}

LIB_DIR="${REMOTE_GATE_LIB_DIR:-$(CDPATH= cd -- "$(dirname "$0")" && pwd)}"
. "$LIB_DIR/remote-gate-firewall-backends.sh"
. "$LIB_DIR/remote-gate-wireguard-verify.sh"

case "${1:-}" in
    detect) detect_backend || { printf '%s\n' unsupported; exit 1; } ;;
    ipv6-capable) rg_b="$(detect_backend 2>/dev/null || true)"; case "$rg_b" in fw4-nftables) printf '%s\n' yes ;; fw3-iptables) fw3_ipv6_capable && printf '%s\n' yes || { printf '%s\n' no; exit 1; } ;; *) printf '%s\n' no; exit 1 ;; esac ;;
    install) install_rules ;;
    sync) shift; sync_policy "$@" ;;
    activate) case "$#" in 5) activate "$2" ipv4 wg_ping "$3" "$4" "$5" legacy ;; 7) activate "$2" "$3" "$4" "$5" "$6" "$7" web_verified ;; 8) activate "$2" "$3" "$4" "$5" "$6" "$7" "$8" ;; *) fail "usage: $0 activate <source> [family scope] <wan-device> <udp-ingress-port> <ttl-seconds> [source-kind]" ;; esac ;;
    verify) [ "$#" -eq 7 ] || fail "usage: $0 verify <source|any> <family> <wan-device> <udp-port> <seconds> <candidate|discovery>"; verify_open "$2" "$3" "$4" "$5" "$6" "$7" ;;
    verify-wireguard) [ "$#" -eq 5 ] || fail "usage: $0 verify-wireguard <source> <family> <wan-device> <udp-port>"; verify_wireguard_source "$2" "$3" "$4" "$5" ;;
    verify-clear) [ "$#" -eq 2 ] || fail "usage: $0 verify-clear <ipv4|ipv6>"; verify_clear "$2" ;;
    clear) clear_auth "${2:-all}" ;;
    restore) restore_rules ;;
    status-json) status_json ;;
    uninstall) uninstall_rules; rm -f "$MAPPED_INGRESS_V4_FILE" "$MAPPED_CONTROL_V4_FILE" ;;
    *) fail "usage: $0 detect|ipv6-capable|install|sync|activate|verify|verify-wireguard|verify-clear|clear|restore|status-json|uninstall" ;;
esac