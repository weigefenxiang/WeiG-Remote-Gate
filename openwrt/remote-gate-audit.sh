#!/bin/sh
set -u

section() {
    printf '\n===== %s =====\n' "$1"
}

has() {
    command -v "$1" >/dev/null 2>&1
}

print_cmd() {
    name="$1"
    if has "$name"; then
        path="$(command -v "$name" 2>/dev/null || true)"
        printf '%-14s %s\n' "$name" "$path"
    else
        printf '%-14s NOT FOUND\n' "$name"
    fi
}

safe_ubus_status() {
    obj="$1"
    status="$(ubus call "$obj" status 2>/dev/null)" || return 0
    name="${obj#network.interface.}"
    up="$(printf '%s' "$status" | jsonfilter -e '@.up' 2>/dev/null | sed -n '1p')"
    dev="$(printf '%s' "$status" | jsonfilter -e '@.l3_device' 2>/dev/null | sed -n '1p')"
    proto="$(printf '%s' "$status" | jsonfilter -e '@.proto' 2>/dev/null | sed -n '1p')"
    v4="$(printf '%s' "$status" | jsonfilter -e '@["ipv4-address"][*].address' 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
    v6="$(printf '%s' "$status" | jsonfilter -e '@["ipv6-address"][*].address' 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
    p6="$(printf '%s' "$status" | jsonfilter -e '@["ipv6-prefix"][*].address' 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
    def4="$(printf '%s' "$status" | jsonfilter -e '@.route[*].target' 2>/dev/null | grep -cx '0.0.0.0' 2>/dev/null || true)"
    def6="$(printf '%s' "$status" | jsonfilter -e '@.route[*].target' 2>/dev/null | grep -cx '::' 2>/dev/null || true)"
    [ -n "$v4" ] || v4='-'
    [ -n "$v6" ] || v6='-'
    [ -n "$p6" ] || p6='-'
    printf '%s | up=%s | proto=%s | device=%s | default4=%s | default6=%s\n' \
        "$name" "${up:--}" "${proto:--}" "${dev:--}" "${def4:-0}" "${def6:-0}"
    printf '  IPv4: %s\n' "$v4"
    printf '  IPv6: %s\n' "$v6"
    printf '  IPv6 prefix: %s\n' "$p6"
}

section 'SYSTEM'
if [ -r /etc/openwrt_release ]; then
    grep -E '^(DISTRIB_ID|DISTRIB_RELEASE|DISTRIB_REVISION|DISTRIB_TARGET|DISTRIB_ARCH)=' /etc/openwrt_release 2>/dev/null || true
fi
uname -a 2>/dev/null || true

section 'FIREWALL CAPABILITIES'
for cmd in fw3 fw4 iptables ip6tables ipset nft; do
    print_cmd "$cmd"
done
if has iptables; then
    iptables --version 2>/dev/null || true
fi
if has ip6tables; then
    ip6tables --version 2>/dev/null || true
fi
if has ipset; then
    ipset --version 2>/dev/null | sed -n '1p' || true
    printf 'ipset help mentions inet6 family: '
    if ipset help hash:ip 2>&1 | grep -qi 'inet6'; then
        printf 'YES\n'
    else
        printf 'NO/UNKNOWN\n'
    fi
fi

section 'RELEVANT PACKAGES'
if has opkg; then
    opkg list-installed 2>/dev/null | grep -E '^(firewall|firewall4|iptables|ip6tables|ipset|kmod-ipt-ipset|kmod-ip6tables|kmod-nft|nftables|wireguard|kmod-wireguard|natmap)( |-|$)' || true
else
    printf 'opkg not found\n'
fi

section 'NETWORK INTERFACES (SAFE SUMMARY)'
if has ubus && has jsonfilter; then
    for obj in $(ubus list 'network.interface.*' 2>/dev/null | sort); do
        [ "$obj" = 'network.interface.loopback' ] && continue
        safe_ubus_status "$obj"
    done
else
    printf 'ubus/jsonfilter unavailable\n'
fi

section 'KERNEL IPv6 ADDRESSES'
if has ip; then
    ip -6 -o addr show scope global 2>/dev/null | awk '{print $2, $3, $4}' || true
else
    printf 'ip command not found\n'
fi

section 'DEFAULT ROUTES'
if has ip; then
    printf '%s\n' '-- IPv4 --'
    ip -4 route show default 2>/dev/null || true
    printf '%s\n' '-- IPv6 --'
    ip -6 route show default 2>/dev/null || true
fi

section 'WIREGUARD (NO PRIVATE KEYS)'
if has wg; then
    interfaces="$(wg show interfaces 2>/dev/null || true)"
    if [ -z "$interfaces" ]; then
        printf 'No live WireGuard interface\n'
    else
        for name in $interfaces; do
            printf '%s | listen_port=%s\n' "$name" "$(wg show "$name" listen-port 2>/dev/null | sed -n '1p')"
            wg show "$name" latest-handshakes 2>/dev/null | awk '{if ($2 > latest) latest=$2} END {printf "  latest_handshake_epoch=%d\n", latest+0}'
        done
    fi
else
    printf 'wg not found\n'
fi

section 'NATMAP DISCOVERY'
print_cmd natmap
if has natmap; then
    printf 'natmap executable detected.\n'
else
    printf 'natmap executable not detected.\n'
fi
if has pidof && pidof natmap >/dev/null 2>&1; then
    printf 'natmap process: running\n'
else
    printf 'natmap process: not detected\n'
fi
if [ -e /etc/config/natmap ]; then
    printf 'UCI config file: /etc/config/natmap exists (content intentionally not printed)\n'
else
    printf 'UCI config file: not detected\n'
fi

section 'REMOTE GATE CURRENT STATE'
printf 'Agent service: '
if [ -x /etc/init.d/remote-gate-agent ]; then
    /etc/init.d/remote-gate-agent status 2>/dev/null || true
else
    printf 'not installed\n'
fi
if [ -x /usr/lib/remote-gate/remote-gate-firewall.sh ]; then
    /usr/lib/remote-gate/remote-gate-firewall.sh status-json 2>/dev/null || true
else
    printf 'Remote Gate firewall helper not installed\n'
fi

section 'NOTES'
printf '%s\n' \
    'This audit performs read-only capability/status queries only.' \
    'It does not read /etc/remote-gate.conf, WireGuard private keys, NATMap configuration contents, or any secret/token value.'
