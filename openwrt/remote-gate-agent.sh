#!/bin/sh
set -u

CONFIG_FILE="/etc/remote-gate.conf"
FIREWALL="/usr/lib/remote-gate/remote-gate-firewall.sh"
TAG="remote-gate"
TMP_BASE="/tmp/remote-gate-agent.$$"

[ -r "$CONFIG_FILE" ] || exit 1
# shellcheck disable=SC1090
. "$CONFIG_FILE"

: "${HOSTNAME:?HOSTNAME is required}"
: "${WRITE_TOKEN:?WRITE_TOKEN is required}"

BODY="${TMP_BASE}.body"
trap 'rm -f "$BODY"' EXIT INT TERM

curl_base() {
    if [ -n "${AGENT_INTERFACE:-}" ]; then
        curl -4 --interface "$AGENT_INTERFACE" "$@"
    else
        curl -4 "$@"
    fi
}

is_gate_public_ipv4() {
    printf '%s\n' "$1" | awk -F. '
        NF != 4 { exit 1 }
        { for (i=1;i<=4;i++) if ($i !~ /^[0-9]+$/ || $i<0 || $i>255) exit 1 }
        $1 == 10 { exit 1 }
        $1 == 172 && $2 >= 16 && $2 <= 31 { exit 1 }
        $1 == 192 && $2 == 168 { exit 1 }
        $1 == 100 && $2 >= 64 && $2 <= 127 { exit 1 }
        $1 == 0 || $1 == 127 { exit 1 }
        $1 == 169 && $2 == 254 { exit 1 }
        $1 >= 224 { exit 1 }
        { exit 0 }
    '
}

public_wan_devices() {
    for obj in $(ubus list 'network.interface.*' 2>/dev/null); do
        name="${obj#network.interface.}"
        [ "$name" = "$obj" ] && continue
        [ "$name" = "loopback" ] && continue
        status="$(ubus call "$obj" status 2>/dev/null)" || continue
        up="$(printf '%s' "$status" | jsonfilter -e '@.up' 2>/dev/null | sed -n '1p')"
        [ "$up" = "true" ] || continue
        ip="$(printf '%s' "$status" | jsonfilter -e '@["ipv4-address"][0].address' 2>/dev/null | sed -n '1p')"
        dev="$(printf '%s' "$status" | jsonfilter -e '@.l3_device' 2>/dev/null | sed -n '1p')"
        [ -n "$ip" ] && [ -n "$dev" ] || continue
        targets="$(printf '%s' "$status" | jsonfilter -e '@.route[*].target' 2>/dev/null)"
        printf '%s\n' "$targets" | grep -qx '0.0.0.0' || continue
        is_gate_public_ipv4 "$ip" || continue
        case "$dev" in ''|*[!A-Za-z0-9_.:@+-]*) continue ;; esac
        printf '%s\n' "$dev"
    done | sort -u
}

wireguard_ports() {
    {
        # Protect configured listen ports even before a WireGuard interface is up.
        for section in $(uci -q show network 2>/dev/null | sed -n "s/^network\.\([^.=]*\)\.proto='wireguard'$/\1/p"); do
            port="$(uci -q get "network.${section}.listen_port" 2>/dev/null || true)"
            case "$port" in ''|*[!0-9]*) continue ;; esac
            [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || continue
            printf '%s\n' "$port"
        done
        if command -v wg >/dev/null 2>&1; then
            for name in $(wg show interfaces 2>/dev/null); do
                port="$(wg show "$name" listen-port 2>/dev/null | sed -n '1p')"
                case "$port" in ''|*[!0-9]*) continue ;; esac
                [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || continue
                printf '%s\n' "$port"
            done
        fi
    } | sort -nu
}

sync_firewall_policy() {
    devices="$(public_wan_devices | tr '\n' ' ')"
    ports="$(wireguard_ports | tr '\n' ' ')"
    "$FIREWALL" sync "$devices" "$ports" >/dev/null 2>&1 || {
        logger -t "$TAG" "firewall policy sync failed" 2>/dev/null || true
        return 1
    }
}

wireguard_json() {
    command -v wg >/dev/null 2>&1 || { printf '[]'; return; }
    first=1
    printf '['
    for name in $(wg show interfaces 2>/dev/null); do
        case "$name" in ''|*[!A-Za-z0-9_.:@-]*) continue ;; esac
        port="$(wg show "$name" listen-port 2>/dev/null | sed -n '1p')"
        case "$port" in ''|*[!0-9]*) continue ;; esac
        latest="$(wg show "$name" latest-handshakes 2>/dev/null | awk 'BEGIN{m=0} {if ($2>m) m=$2} END{print m+0}')"
        transfer="$(wg show "$name" transfer 2>/dev/null | awk 'BEGIN{rx=0;tx=0} {rx+=$2;tx+=$3} END{printf "%d %d",rx,tx}')"
        rx="${transfer%% *}"; tx="${transfer##* }"
        [ "$first" -eq 1 ] || printf ','
        first=0
        printf '{"name":"%s","listen_port":%s,"latest_handshake":%s,"rx":%s,"tx":%s}' \
            "$name" "$port" "${latest:-0}" "${rx:-0}" "${tx:-0}"
    done
    printf ']'
}

post_status() {
    fw="$("$FIREWALL" status-json 2>/dev/null || printf '{"backend":"unsupported","ready":false,"active":false,"source_ip":"","device":"","wg_port":0,"expires_in":0,"protected_devices":0,"protected_ports":0}')"
    wg_json="$(wireguard_json)"
    payload="{\"wireguard\":${wg_json},\"firewall\":${fw}}"
    curl_base -sS --connect-timeout 8 --max-time 20 \
        -o /dev/null -X POST "https://${HOSTNAME}/api/v1/agent/status" \
        -H "Authorization: Bearer ${WRITE_TOKEN}" \
        -H 'Content-Type: application/json' --data-binary "$payload" >/dev/null 2>&1 || true
}

ack() {
    id="$1"; ok="$2"; detail="$3"
    payload="{\"id\":\"${id}\",\"ok\":${ok},\"detail\":\"${detail}\"}"
    curl_base -sS --connect-timeout 8 --max-time 20 \
        -o /dev/null -X POST "https://${HOSTNAME}/api/v1/agent/ack" \
        -H "Authorization: Bearer ${WRITE_TOKEN}" \
        -H 'Content-Type: application/json' --data-binary "$payload" >/dev/null 2>&1 || true
}

pull_once() {
    code="$(curl_base -sS --connect-timeout 8 --max-time 20 -o "$BODY" -w '%{http_code}' \
        "https://${HOSTNAME}/api/v1/agent/pull" -H "Authorization: Bearer ${WRITE_TOKEN}" 2>/dev/null)"
    rc=$?
    [ "$rc" -eq 0 ] || return 1
    [ "$code" = "204" ] && return 0
    [ "$code" = "200" ] || { logger -t "$TAG" "agent pull failed HTTP $code"; return 1; }

    id="$(jsonfilter -i "$BODY" -e '@.id' 2>/dev/null | sed -n '1p')"
    action="$(jsonfilter -i "$BODY" -e '@.action' 2>/dev/null | sed -n '1p')"
    expires_at="$(jsonfilter -i "$BODY" -e '@.expires_at' 2>/dev/null | sed -n '1p')"
    now="$(date +%s)"
    case "$expires_at" in ''|*[!0-9]*) ack "$id" false "invalid-expiry"; return 1 ;; esac
    [ "$expires_at" -gt "$now" ] || { ack "$id" false "command-expired"; return 0; }

    case "$action" in
        activate)
            source_ip="$(jsonfilter -i "$BODY" -e '@.source_ip' 2>/dev/null | sed -n '1p')"
            device="$(jsonfilter -i "$BODY" -e '@.device' 2>/dev/null | sed -n '1p')"
            port="$(jsonfilter -i "$BODY" -e '@.wg_port' 2>/dev/null | sed -n '1p')"
            ttl="$(jsonfilter -i "$BODY" -e '@.ttl' 2>/dev/null | sed -n '1p')"
            sync_firewall_policy || true
            if "$FIREWALL" activate "$source_ip" "$device" "$port" "$ttl"; then
                ack "$id" true "authorization-active"
            else
                ack "$id" false "firewall-activation-failed"
            fi
            ;;
        close)
            if "$FIREWALL" clear; then ack "$id" true "authorization-cleared"; else ack "$id" false "firewall-clear-failed"; fi
            ;;
        *) ack "$id" false "unsupported-action" ;;
    esac
}

run_once() {
    sync_firewall_policy || true
    post_status
    pull_once
    post_status
}

case "${1:-once}" in
    sync-firewall) sync_firewall_policy ;;
    once) run_once ;;
    loop)
        interval="${AGENT_INTERVAL:-10}"
        case "$interval" in ''|*[!0-9]*) interval=10 ;; esac
        [ "$interval" -ge 5 ] || interval=5
        while :; do run_once; sleep "$interval"; done
        ;;
    *) echo "usage: $0 [sync-firewall|once|loop]" >&2; exit 2 ;;
esac
