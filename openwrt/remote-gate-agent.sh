#!/bin/sh
set -u

CONFIG_FILE="/etc/remote-gate.conf"
FIREWALL="/usr/lib/remote-gate/remote-gate-firewall.sh"
STATE_DIR="/etc/remote-gate-state"
TAG="remote-gate"
TMP_BASE="/tmp/remote-gate-agent.$$"
INV_DIR="${TMP_BASE}.inventory"
BODY="${TMP_BASE}.body"
CONTROL_STATE_FILE="$STATE_DIR/control-path"
INVENTORY_STATE_FILE="$STATE_DIR/inventory-v2.fingerprint"
INVENTORY_POSTED_FILE="$STATE_DIR/inventory-v2.posted"

[ -r "$CONFIG_FILE" ] || exit 1
# shellcheck disable=SC1090
. "$CONFIG_FILE"

: "${HOSTNAME:?HOSTNAME is required}"
: "${WRITE_TOKEN:?WRITE_TOKEN is required}"

GATE_IPV6="${GATE_IPV6:-auto}"
CONTROL_TRANSPORT="${CONTROL_TRANSPORT:-auto}"
NATMAP_DISCOVERY="${NATMAP_DISCOVERY:-auto}"
case "$GATE_IPV6" in auto|enabled|disabled) ;; *) GATE_IPV6=auto ;; esac
case "$CONTROL_TRANSPORT" in auto|manual) ;; *) CONTROL_TRANSPORT=auto ;; esac
case "$NATMAP_DISCOVERY" in auto|disabled) ;; *) NATMAP_DISCOVERY=auto ;; esac

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR" 2>/dev/null || true
trap 'rm -rf "$INV_DIR"; rm -f "$BODY" "${TMP_BASE}".*' EXIT INT TERM

valid_device() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }

is_public_ipv4() {
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

is_global_ipv6() {
    value="$(printf '%s' "$1" | tr 'A-F' 'a-f')"
    case "$value" in
        2*|3*) return 0 ;;
        *) return 1 ;;
    esac
}

group_key() {
    printf '%s' "$1" | sed 's/[^A-Za-z0-9_.-]/_/g'
}

collect_wans() {
    rm -rf "$INV_DIR"
    mkdir -p "$INV_DIR"
    for obj in $(ubus list 'network.interface.*' 2>/dev/null); do
        name="${obj#network.interface.}"
        [ "$name" = "$obj" ] && continue
        [ "$name" = "loopback" ] && continue
        [ "$name" = "WG_HOME" ] && continue

        status="$(ubus call "$obj" status 2>/dev/null)" || continue
        up="$(printf '%s' "$status" | jsonfilter -e '@.up' 2>/dev/null | sed -n '1p')"
        [ "$up" = "true" ] || continue
        proto="$(printf '%s' "$status" | jsonfilter -e '@.proto' 2>/dev/null | sed -n '1p')"
        [ "$proto" = "wireguard" ] && continue
        dev="$(printf '%s' "$status" | jsonfilter -e '@.l3_device' 2>/dev/null | sed -n '1p')"
        valid_device "$dev" || continue

        targets="$(printf '%s' "$status" | jsonfilter -e '@.route[*].target' 2>/dev/null)"
        def4=0; def6=0
        printf '%s\n' "$targets" | grep -qx '0.0.0.0' && def4=1
        printf '%s\n' "$targets" | grep -qx '::' && def6=1
        [ "$def4" -eq 1 ] || [ "$def6" -eq 1 ] || continue

        key="$(group_key "$dev")"
        base="$INV_DIR/$key"
        printf '%s\n' "$dev" > "$base.device"
        printf '%s\n' "$name" >> "$base.names"

        if [ "$def4" -eq 1 ]; then
            : > "$base.def4"
            printf '%s\n' "$name" > "$base.name"
        elif [ ! -s "$base.name" ]; then
            case "$name" in
                *_6) printf '%s\n' "${name%_6}" > "$base.name" ;;
                *) printf '%s\n' "$name" > "$base.name" ;;
            esac
        fi
        [ "$def6" -eq 1 ] && : > "$base.def6"

        printf '%s' "$status" | jsonfilter -e '@["ipv4-address"][*].address' 2>/dev/null >> "$base.v4" || true
        printf '%s' "$status" | jsonfilter -e '@["ipv6-address"][*].address' 2>/dev/null >> "$base.v6" || true
    done

    for file in "$INV_DIR"/*.names; do
        [ -f "$file" ] || continue
        sort -u "$file" -o "$file"
    done
    for file in "$INV_DIR"/*.v4 "$INV_DIR"/*.v6; do
        [ -f "$file" ] || continue
        sed '/^$/d' "$file" | sort -u > "${file}.tmp"
        mv "${file}.tmp" "$file"
    done
}

wireguard_ports() {
    {
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

ipv6_firewall_capable() {
    [ -x "$FIREWALL" ] || return 1
    "$FIREWALL" ipv6-capable >/dev/null 2>&1
}

v4_protected_devices() {
    collect_wans
    for file in "$INV_DIR"/*.device; do
        [ -f "$file" ] || continue
        base="${file%.device}"
        dev="$(sed -n '1p' "$file")"
        [ -f "$base.v4" ] || continue
        while IFS= read -r address; do
            if is_public_ipv4 "$address"; then
                printf '%s\n' "$dev"
                break
            fi
        done < "$base.v4"
    done | sort -u
}

v6_protected_devices() {
    [ "$GATE_IPV6" != "disabled" ] || return 0
    ipv6_firewall_capable || return 0
    collect_wans
    for file in "$INV_DIR"/*.device; do
        [ -f "$file" ] || continue
        base="${file%.device}"
        dev="$(sed -n '1p' "$file")"
        [ -f "$base.v6" ] || continue
        while IFS= read -r address; do
            if is_global_ipv6 "$address"; then
                printf '%s\n' "$dev"
                break
            fi
        done < "$base.v6"
    done | sort -u
}

sync_firewall_policy() {
    v4="$(v4_protected_devices | tr '\n' ' ')"
    v6="$(v6_protected_devices | tr '\n' ' ')"
    ports="$(wireguard_ports | tr '\n' ' ')"
    "$FIREWALL" sync "$v4" "$v6" "$ports" >/dev/null 2>&1 || {
        logger -t "$TAG" "firewall policy sync failed" 2>/dev/null || true
        return 1
    }
}

json_string_array_file() {
    file="$1"
    first=1
    printf '['
    if [ -f "$file" ]; then
        while IFS= read -r value; do
            [ -n "$value" ] || continue
            [ "$first" -eq 1 ] || printf ','
            first=0
            printf '"%s"' "$value"
        done < "$file"
    fi
    printf ']'
}

natmap_json() {
    printf '[]'
}

build_inventory_json() {
    collect_wans
    gate6=false
    [ "$GATE_IPV6" != "disabled" ] && ipv6_firewall_capable && gate6=true

    control4=false
    control6=false
    first=1
    printf '{"schema":2,"generated_at":%s,"capabilities":{"gate_ipv4":true,"gate_ipv6":%s,' "$(date +%s)" "$gate6"
    for file in "$INV_DIR"/*.device; do
        [ -f "$file" ] || continue
        base="${file%.device}"
        [ -f "$base.v4" ] && [ -f "$base.def4" ] && control4=true
        if [ -f "$base.v6" ] && [ -f "$base.def6" ]; then
            while IFS= read -r a; do is_global_ipv6 "$a" && control6=true; done < "$base.v6"
        fi
    done
    printf '"control_ipv4":%s,"control_ipv6":%s,"natmap":false},"wans":[' "$control4" "$control6"

    for file in "$INV_DIR"/*.device; do
        [ -f "$file" ] || continue
        base="${file%.device}"
        name="$(sed -n '1p' "$base.name" 2>/dev/null)"
        dev="$(sed -n '1p' "$base.device" 2>/dev/null)"
        [ -n "$name" ] && [ -n "$dev" ] || continue
        [ "$first" -eq 1 ] || printf ','
        first=0
        def4=false; def6=false
        [ -f "$base.def4" ] && def4=true
        [ -f "$base.def6" ] && def6=true
        printf '{"name":"%s","device":"%s","logical_interfaces":' "$name" "$dev"
        json_string_array_file "$base.names"
        printf ',"up":true,"default_route_v4":%s,"default_route_v6":%s,"ipv4":' "$def4" "$def6"
        json_string_array_file "$base.v4"
        printf ',"ipv6":'
        json_string_array_file "$base.v6"
        printf '}'
    done
    printf '],"natmap":'
    natmap_json
    printf '}'
}

control_candidates() {
    collect_wans
    tmp="${TMP_BASE}.candidates"
    : > "$tmp"
    for file in "$INV_DIR"/*.device; do
        [ -f "$file" ] || continue
        base="${file%.device}"
        dev="$(sed -n '1p' "$file")"
        if [ -f "$base.v4" ] && [ -f "$base.def4" ]; then
            rank=30
            while IFS= read -r a; do is_public_ipv4 "$a" && rank=10; done < "$base.v4"
            printf '%s|ipv4|%s\n' "$rank" "$dev" >> "$tmp"
        fi
        if [ -f "$base.v6" ] && [ -f "$base.def6" ]; then
            has6=0
            while IFS= read -r a; do is_global_ipv6 "$a" && has6=1; done < "$base.v6"
            [ "$has6" -eq 1 ] && printf '20|ipv6|%s\n' "$dev" >> "$tmp"
        fi
    done

    sorted="${TMP_BASE}.candidates.sorted"
    sort -t'|' -k1,1n -k3,3 "$tmp" > "$sorted"

    last_family=""; last_dev=""
    if [ -r "$CONTROL_STATE_FILE" ]; then
        last_family="$(sed -n '1p' "$CONTROL_STATE_FILE")"
        last_dev="$(sed -n '2p' "$CONTROL_STATE_FILE")"
    fi
    if [ -n "$last_family" ] && [ -n "$last_dev" ] && grep -Fq "|$last_family|$last_dev" "$sorted"; then
        printf '%s|%s\n' "$last_family" "$last_dev"
    fi

    if [ -n "${AGENT_INTERFACE:-}" ]; then
        for fam in ipv4 ipv6; do
            if grep -Fq "|$fam|$AGENT_INTERFACE" "$sorted"; then
                [ "$fam|$AGENT_INTERFACE" = "$last_family|$last_dev" ] || printf '%s|%s\n' "$fam" "$AGENT_INTERFACE"
            fi
        done
        [ "$CONTROL_TRANSPORT" = "manual" ] && return 0
    fi

    while IFS='|' read -r rank family dev; do
        [ -n "$family" ] && [ -n "$dev" ] || continue
        [ "$family|$dev" = "$last_family|$last_dev" ] && continue
        [ -n "${AGENT_INTERFACE:-}" ] && [ "$dev" = "$AGENT_INTERFACE" ] && continue
        printf '%s|%s\n' "$family" "$dev"
    done < "$sorted"
}

remember_control_path() {
    family="$1"; dev="$2"
    {
        printf '%s\n' "$family"
        printf '%s\n' "$dev"
        date +%s
    } > "$CONTROL_STATE_FILE"
    chmod 600 "$CONTROL_STATE_FILE"
}

control_request() {
    method="$1"; path="$2"; output="$3"; payload="${4:-}"
    rm -f "$output"
    for candidate in $(control_candidates | tr '|' ':'); do
        family="${candidate%%:*}"
        dev="${candidate#*:}"
        flag="-4"
        [ "$family" = "ipv6" ] && flag="-6"

        if [ "$method" = "POST" ]; then
            code="$(
                curl "$flag" --interface "$dev" -sS \
                    --connect-timeout 6 --max-time 15 \
                    -o "$output" -w '%{http_code}' \
                    -X POST "https://${HOSTNAME}${path}" \
                    -H "Authorization: Bearer ${WRITE_TOKEN}" \
                    -H 'Content-Type: application/json' \
                    --data-binary "$payload" 2>/dev/null
            )"
        else
            code="$(
                curl "$flag" --interface "$dev" -sS \
                    --connect-timeout 6 --max-time 15 \
                    -o "$output" -w '%{http_code}' \
                    "https://${HOSTNAME}${path}" \
                    -H "Authorization: Bearer ${WRITE_TOKEN}" 2>/dev/null
            )"
        fi
        rc=$?
        if [ "$rc" -eq 0 ] && [ -n "$code" ] && [ "$code" != "000" ]; then
            CONTROL_CODE="$code"
            CONTROL_FAMILY="$family"
            CONTROL_DEVICE="$dev"
            remember_control_path "$family" "$dev"
            return 0
        fi
    done
    CONTROL_CODE="000"
    CONTROL_FAMILY=""
    CONTROL_DEVICE=""
    return 1
}

transport_json() {
    family=""; dev=""; last_ok=0
    if [ -r "$CONTROL_STATE_FILE" ]; then
        family="$(sed -n '1p' "$CONTROL_STATE_FILE")"
        dev="$(sed -n '2p' "$CONTROL_STATE_FILE")"
        last_ok="$(sed -n '3p' "$CONTROL_STATE_FILE")"
    fi
    case "$last_ok" in ''|*[!0-9]*) last_ok=0 ;; esac
    healthy=false
    [ "$last_ok" -gt 0 ] && [ "$(( $(date +%s) - last_ok ))" -le 120 ] && healthy=true
    printf '{"active_family":"%s","active_device":"%s","healthy":%s,"last_ok_at":%s}' "$family" "$dev" "$healthy" "$last_ok"
}

inventory_fingerprint() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}'
    else
        cksum | awk '{print $1 ":" $2}'
    fi
}

maybe_post_inventory() {
    payload="$(build_inventory_json)"
    fingerprint="$(printf '%s' "$payload" | sed 's/"generated_at":[0-9]*/"generated_at":0/' | inventory_fingerprint)"
    old="$(cat "$INVENTORY_STATE_FILE" 2>/dev/null || true)"
    last="$(cat "$INVENTORY_POSTED_FILE" 2>/dev/null || echo 0)"
    case "$last" in ''|*[!0-9]*) last=0 ;; esac
    now="$(date +%s)"
    if [ "$fingerprint" = "$old" ] && [ "$((now - last))" -lt 300 ]; then
        return 0
    fi
    if control_request POST "/api/v1/inventory" "$BODY" "$payload" && [ "$CONTROL_CODE" = "204" ]; then
        printf '%s\n' "$fingerprint" > "$INVENTORY_STATE_FILE"
        printf '%s\n' "$now" > "$INVENTORY_POSTED_FILE"
        chmod 600 "$INVENTORY_STATE_FILE" "$INVENTORY_POSTED_FILE"
        return 0
    fi
    logger -t "$TAG" "schema-2 inventory update failed (HTTP ${CONTROL_CODE:-000})" 2>/dev/null || true
    return 1
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
    fw="$("$FIREWALL" status-json 2>/dev/null || printf '{"backend":"unsupported","ready":false,"active":false,"source_ip":"","device":"","wg_port":0,"expires_in":0,"protected_devices_v4":0,"protected_devices_v6":0,"protected_ports":0}')"
    wg_json="$(wireguard_json)"
    transport="$(transport_json)"
    payload="{\"schema\":2,\"wireguard\":${wg_json},\"firewall\":${fw},\"transport\":${transport}}"
    control_request POST "/api/v1/agent/status" "$BODY" "$payload" >/dev/null 2>&1 || true
}

ack() {
    id="$1"; ok="$2"; detail="$3"
    payload="{\"id\":\"${id}\",\"ok\":${ok},\"detail\":\"${detail}\"}"
    control_request POST "/api/v1/agent/ack" "$BODY" "$payload" >/dev/null 2>&1 || true
}

pull_once() {
    control_request GET "/api/v1/agent/pull" "$BODY" || return 1
    code="$CONTROL_CODE"
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
            family="$(jsonfilter -i "$BODY" -e '@.family' 2>/dev/null | sed -n '1p')"
            scope="$(jsonfilter -i "$BODY" -e '@.scope' 2>/dev/null | sed -n '1p')"
            device="$(jsonfilter -i "$BODY" -e '@.device' 2>/dev/null | sed -n '1p')"
            port="$(jsonfilter -i "$BODY" -e '@.wg_port' 2>/dev/null | sed -n '1p')"
            ttl="$(jsonfilter -i "$BODY" -e '@.ttl' 2>/dev/null | sed -n '1p')"
            [ -n "$family" ] || family=ipv4
            [ -n "$scope" ] || scope=wg_ping
            sync_firewall_policy || true
            if "$FIREWALL" activate "$source_ip" "$family" "$scope" "$device" "$port" "$ttl"; then
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

report_only() {
    sync_firewall_policy || true
    maybe_post_inventory || true
    post_status
}

run_once() {
    sync_firewall_policy || true
    maybe_post_inventory || true
    post_status
    pull_rc=0
    pull_once || pull_rc=$?
    post_status
    return "$pull_rc"
}

case "${1:-once}" in
    sync-firewall) sync_firewall_policy ;;
    inventory) build_inventory_json ;;
    report) report_only ;;
    once) run_once ;;
    loop)
        interval="${AGENT_INTERVAL:-10}"
        case "$interval" in ''|*[!0-9]*) interval=10 ;; esac
        [ "$interval" -ge 5 ] || interval=5
        while :; do run_once; sleep "$interval"; done
        ;;
    *) echo "usage: $0 [sync-firewall|inventory|report|once|loop]" >&2; exit 2 ;;
esac
