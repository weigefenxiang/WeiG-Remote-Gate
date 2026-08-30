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
STATUS="${TMP_BASE}.status"
trap 'rm -f "$BODY" "$STATUS"' EXIT INT TERM

curl_base() {
    if [ -n "${AGENT_INTERFACE:-}" ]; then
        curl -4 --interface "$AGENT_INTERFACE" "$@"
    else
        curl -4 "$@"
    fi
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
        rx="${transfer%% *}"
        tx="${transfer##* }"
        [ "$first" -eq 1 ] || printf ','
        first=0
        printf '{"name":"%s","listen_port":%s,"latest_handshake":%s,"rx":%s,"tx":%s}' \
            "$name" "$port" "${latest:-0}" "${rx:-0}" "${tx:-0}"
    done
    printf ']'
}

post_status() {
    fw="$("$FIREWALL" status-json 2>/dev/null || printf '{"active":false,"source_ip":"","device":"","wg_port":0,"expires_in":0}')"
    wg_json="$(wireguard_json)"
    payload="{\"wireguard\":${wg_json},\"firewall\":${fw}}"
    curl_base -sS --connect-timeout 8 --max-time 20 \
        -o /dev/null \
        -X POST "https://${HOSTNAME}/api/v1/agent/status" \
        -H "Authorization: Bearer ${WRITE_TOKEN}" \
        -H 'Content-Type: application/json' \
        --data-binary "$payload" >/dev/null 2>&1 || true
}

ack() {
    id="$1"; ok="$2"; detail="$3"
    payload="{\"id\":\"${id}\",\"ok\":${ok},\"detail\":\"${detail}\"}"
    curl_base -sS --connect-timeout 8 --max-time 20 \
        -o /dev/null \
        -X POST "https://${HOSTNAME}/api/v1/agent/ack" \
        -H "Authorization: Bearer ${WRITE_TOKEN}" \
        -H 'Content-Type: application/json' \
        --data-binary "$payload" >/dev/null 2>&1 || true
}

pull_once() {
    code="$(
        curl_base -sS --connect-timeout 8 --max-time 20 \
            -o "$BODY" -w '%{http_code}' \
            "https://${HOSTNAME}/api/v1/agent/pull" \
            -H "Authorization: Bearer ${WRITE_TOKEN}" 2>/dev/null
    )"
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
            if "$FIREWALL" activate "$source_ip" "$device" "$port" "$ttl"; then
                ack "$id" true "authorization-active"
            else
                ack "$id" false "firewall-activation-failed"
            fi
            ;;
        close)
            if "$FIREWALL" clear; then
                ack "$id" true "authorization-cleared"
            else
                ack "$id" false "firewall-clear-failed"
            fi
            ;;
        *)
            ack "$id" false "unsupported-action"
            ;;
    esac
}

case "${1:-once}" in
    once)
        post_status
        pull_once
        post_status
        ;;
    loop)
        interval="${AGENT_INTERVAL:-10}"
        case "$interval" in ''|*[!0-9]*) interval=10 ;; esac
        [ "$interval" -ge 5 ] || interval=5
        while :; do
            post_status
            pull_once
            post_status
            sleep "$interval"
        done
        ;;
    *)
        echo "usage: $0 [once|loop]" >&2
        exit 2
        ;;
esac
