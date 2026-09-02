#!/bin/sh
set -u

CONFIG_FILE="/etc/remote-gate.conf"
FIREWALL="/usr/lib/remote-gate/remote-gate-firewall.sh"
EGRESS="/usr/lib/remote-gate/remote-gate-wireguard-egress.sh"
SERVICES="/usr/lib/remote-gate/remote-gate-service-registry.sh"
MAPPING="/usr/lib/remote-gate/remote-gate-mapping.sh"
STATE_DIR="/etc/remote-gate-state"
RUNTIME_DIR="${REMOTE_GATE_RUNTIME_DIR:-/tmp/remote-gate}"
COMMAND_RESULT_FILE="$RUNTIME_DIR/agent-command-result"
TAG="remote-gate"
TMP_BASE="/tmp/remote-gate-agent.$$"
INV_DIR="${TMP_BASE}.inventory"
BODY="${TMP_BASE}.body"
CONTROL_STATE_FILE="$STATE_DIR/control-path"
INVENTORY_STATE_FILE="$STATE_DIR/inventory-v3.fingerprint"
INVENTORY_POSTED_FILE="$STATE_DIR/inventory-v3.posted"

[ -r "$CONFIG_FILE" ] || exit 1
# shellcheck disable=SC1090
. "$CONFIG_FILE"

: "${HOSTNAME:?HOSTNAME is required}"
: "${WRITE_TOKEN:?WRITE_TOKEN is required}"

GATE_IPV6="${GATE_IPV6:-auto}"
CONTROL_TRANSPORT="${CONTROL_TRANSPORT:-auto}"
MAPPED_ACCESS="${MAPPED_ACCESS:-auto}"
REMOTE_GATE_VERIFY_CANDIDATE_SECONDS="${REMOTE_GATE_VERIFY_CANDIDATE_SECONDS:-10}"
REMOTE_GATE_VERIFY_DISCOVERY_SECONDS="${REMOTE_GATE_VERIFY_DISCOVERY_SECONDS:-30}"
export REMOTE_GATE_VERIFY_CANDIDATE_SECONDS REMOTE_GATE_VERIFY_DISCOVERY_SECONDS
case "$GATE_IPV6" in auto|enabled|disabled) ;; *) GATE_IPV6=auto ;; esac
case "$CONTROL_TRANSPORT" in auto|manual) ;; *) CONTROL_TRANSPORT=auto ;; esac
case "$MAPPED_ACCESS" in auto|disabled) ;; *) MAPPED_ACCESS=auto ;; esac

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR" 2>/dev/null || true
trap 'rm -rf "$INV_DIR"; rm -f "$BODY" "${TMP_BASE}".*' EXIT INT TERM

valid_name() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }
valid_device() { valid_name "$1"; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
valid_port() { valid_uint "$1" && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]; }

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
        printf '%s' "$status" | jsonfilter -e '@["ipv6-address"][*].address' 2>/dev/null | while IFS= read -r address; do
            is_global_ipv6 "$address" && printf '%s\n' "$address"
        done >> "$base.v6" || true
    done

    for file in "$INV_DIR"/*.names; do
        [ -f "$file" ] || continue
        sort -u "$file" > "${file}.tmp"
        mv "${file}.tmp" "$file"
    done
    for file in "$INV_DIR"/*.v4 "$INV_DIR"/*.v6; do
        [ -f "$file" ] || continue
        sed '/^$/d' "$file" | sort -u > "${file}.tmp"
        mv "${file}.tmp" "$file"
    done
}

wireguard_ports() {
    if [ -x "$SERVICES" ]; then
        "$SERVICES" ports 2>/dev/null || true
        return 0
    fi
    {
        for section in $(uci -q show network 2>/dev/null | sed -n "s/^network\.\([^.=]*\)\.proto='wireguard'$/\1/p"); do
            port="$(uci -q get "network.${section}.listen_port" 2>/dev/null || true)"
            valid_port "$port" || continue
            printf '%s\n' "$port"
        done
        if command -v wg >/dev/null 2>&1; then
            for name in $(wg show interfaces 2>/dev/null); do
                port="$(wg show "$name" listen-port 2>/dev/null | sed -n '1p')"
                valid_port "$port" || continue
                printf '%s\n' "$port"
            done
        fi
    } | sort -nu
}

mapping_desired_entries() {
    [ "$MAPPED_ACCESS" != "disabled" ] || return 0
    [ -x "$MAPPING" ] && [ -x "$SERVICES" ] || return 0
    collect_wans
    services="$($SERVICES list 2>/dev/null || true)"
    [ -n "$services" ] || return 0

    for file in "$INV_DIR"/*.device; do
        [ -f "$file" ] || continue
        base="${file%.device}"
        [ -f "$base.def4" ] && [ -s "$base.v4" ] || continue
        has_public=0
        while IFS= read -r address; do
            is_public_ipv4 "$address" && has_public=1
        done < "$base.v4"
        [ "$has_public" -eq 0 ] || continue
        wan="$(sed -n '1p' "$base.name" 2>/dev/null)"
        device="$(sed -n '1p' "$base.device" 2>/dev/null)"
        valid_name "$wan" && valid_device "$device" || continue
        printf '%s\n' "$services" | while IFS='|' read -r service_id service_type transport service_name service_port; do
            [ "$service_type" = "wireguard" ] && [ "$transport" = "udp" ] || continue
            valid_name "$service_id" && valid_name "$service_name" && valid_port "$service_port" || continue
            printf '%s,%s,%s,%s\n' "$wan" "$device" "$service_id" "$service_port"
        done
    done
}

sync_mapping_prepare() {
    [ -x "$MAPPING" ] || return 0
    if [ "$MAPPED_ACCESS" = "disabled" ]; then
        "$MAPPING" stop-all >/dev/null 2>&1 || true
        return 0
    fi
    desired="$(mapping_desired_entries)"
    if [ -n "$desired" ]; then
        # Desired values are generated only from locally validated WAN/service names
        # and therefore contain no shell metacharacters or spaces.
        # shellcheck disable=SC2086
        set -- $desired
        "$MAPPING" sync-prepare "$@" >/dev/null 2>&1 || true
    else
        "$MAPPING" sync-prepare >/dev/null 2>&1 || true
    fi
}

mapped_ingress_pairs() {
    [ -x "$MAPPING" ] || return 0
    "$MAPPING" ingress-pairs 2>/dev/null || true
}

mapped_control_pairs() {
    [ -x "$MAPPING" ] || return 0
    "$MAPPING" control-pairs 2>/dev/null || true
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
        [ -s "$base.v4" ] || continue
        printf '%s\n' "$dev"
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
    sync_mapping_prepare
    v4="$(v4_protected_devices | tr '\n' ' ')"
    v6="$(v6_protected_devices | tr '\n' ' ')"
    wg_ports="$(wireguard_ports | tr '\n' ' ')"
    mapped_pairs="$(mapped_ingress_pairs | tr '\n' ' ')"
    mapped_control="$(mapped_control_pairs | tr '\n' ' ')"
    "$FIREWALL" sync "$v4" "$v6" "$wg_ports" "$mapped_pairs" "$mapped_control" >/dev/null 2>&1 || {
        logger -t "$TAG" "firewall policy sync failed" 2>/dev/null || true
        return 1
    }
    if [ -x "$MAPPING" ]; then "$MAPPING" activate-prepared >/dev/null 2>&1 || true; fi
}

sync_egress() {
    [ -x "$EGRESS" ] || return 0
    "$EGRESS" sync >/dev/null 2>&1 || true
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

services_json() {
    if [ -x "$SERVICES" ]; then "$SERVICES" inventory-json 2>/dev/null || printf '[]'; else printf '[]'; fi
}

mappings_json() {
    if [ -x "$MAPPING" ]; then "$MAPPING" inventory-json 2>/dev/null || printf '[]'; else printf '[]'; fi
}

mapping_status_json() {
    if [ -x "$MAPPING" ]; then "$MAPPING" status-json 2>/dev/null || printf '{"available":false,"state":"unavailable","active_mappings":0,"detail":"mapping-helper-failed"}'; else printf '{"available":false,"state":"unavailable","active_mappings":0,"detail":"mapping-helper-unavailable"}'; fi
}

build_inventory_json() {
    collect_wans
    gate6=false
    [ "$GATE_IPV6" != "disabled" ] && ipv6_firewall_capable && gate6=true

    control4=false
    control6=false
    first=1
    mapping_status="$(mapping_status_json)"
    mapper_available="$(printf '%s' "$mapping_status" | jsonfilter -e '@.available' 2>/dev/null | sed -n '1p')"
    [ "$mapper_available" = "true" ] || mapper_available=false
    mapped_count="$(printf '%s' "$mapping_status" | jsonfilter -e '@.active_mappings' 2>/dev/null | sed -n '1p')"
    valid_uint "$mapped_count" || mapped_count=0
    mapped_access=false
    [ "$mapped_count" -gt 0 ] && mapped_access=true

    printf '{"schema":3,"generated_at":%s,"capabilities":{"gate_ipv4":true,"gate_ipv6":%s,' "$(date +%s)" "$gate6"
    for file in "$INV_DIR"/*.device; do
        [ -f "$file" ] || continue
        base="${file%.device}"
        [ -f "$base.v4" ] && [ -f "$base.def4" ] && control4=true
        if [ -f "$base.v6" ] && [ -f "$base.def6" ]; then
            while IFS= read -r a; do is_global_ipv6 "$a" && control6=true; done < "$base.v6"
        fi
    done
    printf '"control_ipv4":%s,"control_ipv6":%s,"mapped_access":%s,"mapper_available":%s},"wans":[' "$control4" "$control6" "$mapped_access" "$mapper_available"

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
    printf '],"services":'
    services_json
    printf ',"mappings":'
    mappings_json
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
    if [ "$fingerprint" = "$old" ] && [ "$((now - last))" -lt 300 ]; then return 0; fi
    if control_request POST "/api/v1/inventory" "$BODY" "$payload" && [ "$CONTROL_CODE" = "204" ]; then
        printf '%s\n' "$fingerprint" > "$INVENTORY_STATE_FILE"
        printf '%s\n' "$now" > "$INVENTORY_POSTED_FILE"
        chmod 600 "$INVENTORY_STATE_FILE" "$INVENTORY_POSTED_FILE"
        return 0
    fi
    logger -t "$TAG" "schema-3 inventory update failed (HTTP ${CONTROL_CODE:-000})" 2>/dev/null || true
    return 1
}

wireguard_json() {
    command -v wg >/dev/null 2>&1 || { printf '[]'; return; }
    first=1
    printf '['
    for name in $(wg show interfaces 2>/dev/null); do
        valid_name "$name" || continue
        port="$(wg show "$name" listen-port 2>/dev/null | sed -n '1p')"
        valid_port "$port" || continue
        latest="$(wg show "$name" latest-handshakes 2>/dev/null | awk 'BEGIN{m=0} {if ($2>m) m=$2} END{print m+0}')"
        transfer="$(wg show "$name" transfer 2>/dev/null | awk 'BEGIN{rx=0;tx=0} {rx+=$2;tx+=$3} END{printf "%d %d",rx,tx}')"
        rx="${transfer%% *}"; tx="${transfer##* }"
        [ "$first" -eq 1 ] || printf ','
        first=0
        printf '{"name":"%s","listen_port":%s,"latest_handshake":%s,"rx":%s,"tx":%s}' "$name" "$port" "${latest:-0}" "${rx:-0}" "${tx:-0}"
    done
    printf ']'
}

egress_json() {
    if [ -x "$EGRESS" ]; then
        "$EGRESS" status-json 2>/dev/null || printf '{"active":false,"state":"inactive","mode":"","wan":"","device":"","wan_v4":"","device_v4":"","wan_v6":"","device_v6":"","wg":"","ipv4_subnet":"","ipv6_subnet":"","detail":"","expires_in":0}'
    else
        printf '{"active":false,"state":"inactive","mode":"","wan":"","device":"","wan_v4":"","device_v4":"","wan_v6":"","device_v6":"","wg":"","ipv4_subnet":"","ipv6_subnet":"","detail":"","expires_in":0}'
    fi
}

post_status() {
    inventory_synced="${1:-true}"
    case "$inventory_synced" in true|false) ;; *) inventory_synced=false ;; esac
    fw="$("$FIREWALL" status-json 2>/dev/null || printf '{"backend":"unsupported","ready":false,"active":false,"source_ip":"","device":"","ingress_port":0,"wg_port":0,"expires_in":0,"protected_devices_v4":0,"protected_devices_v6":0,"protected_ports":0,"protected_mapped_ingress_v4":0}')"
    wg_json="$(wireguard_json)"
    egress="$(egress_json)"
    mapping="$(mapping_status_json)"
    transport="$(transport_json)"
    payload="{\"schema\":3,\"inventory_synced\":${inventory_synced},\"wireguard\":${wg_json},\"firewall\":${fw},\"egress\":${egress},\"mapping\":${mapping},\"transport\":${transport}}"
    if control_request POST "/api/v1/agent/status" "$BODY" "$payload" && [ "$CONTROL_CODE" = "204" ]; then
        return 0
    fi
    logger -t "$TAG" "agent status update failed (HTTP ${CONTROL_CODE:-000})" 2>/dev/null || true
    return 1
}

sanitize_detail() {
    printf '%s' "$1" | tr '\r\n' '  ' | sed 's/[^A-Za-z0-9 ._:/(),+-]/_/g' | cut -c1-200
}

send_ack() {
    id="$1"; ok="$2"; detail="$(sanitize_detail "$3")"
    payload="{\"id\":\"${id}\",\"ok\":${ok},\"detail\":\"${detail}\"}"
    control_request POST "/api/v1/agent/ack" "$BODY" "$payload" >/dev/null 2>&1 && [ "$CONTROL_CODE" = "204" ]
}

ack() { send_ack "$1" "$2" "$3" || true; }

clear_activation_result() {
    expected="${1:-}"
    [ -r "$COMMAND_RESULT_FILE" ] || return 0
    if [ -n "$expected" ]; then
        saved_id="$(sed -n '1p' "$COMMAND_RESULT_FILE" 2>/dev/null)"
        [ "$saved_id" = "$expected" ] || return 0
    fi
    rm -f "$COMMAND_RESULT_FILE"
}

write_activation_result() {
    result_id="$1"; result_state="$2"; result_detail="$(sanitize_detail "$3")"
    case "$result_state" in pending|true|false) ;; *) return 1 ;; esac
    mkdir -p "$RUNTIME_DIR" || return 1
    chmod 700 "$RUNTIME_DIR" 2>/dev/null || true
    result_tmp="${COMMAND_RESULT_FILE}.tmp.$$"
    {
        printf '%s\n' "$result_id"
        printf '%s\n' "$result_state"
        printf '%s\n' "$result_detail"
    } > "$result_tmp" || { rm -f "$result_tmp"; return 1; }
    chmod 600 "$result_tmp" 2>/dev/null || true
    mv -f "$result_tmp" "$COMMAND_RESULT_FILE"
}

prepare_activation_command() {
    write_activation_result "$1" pending "activation-in-progress"
}

finish_activation_command() {
    result_id="$1"; result_ok="$2"; result_detail="$(sanitize_detail "$3")"
    if ! write_activation_result "$result_id" "$result_ok" "$result_detail"; then
        logger -t "$TAG" "cannot persist activation result for ACK replay; rolling back runtime" 2>/dev/null || true
        rollback_active_access
        if write_activation_result "$result_id" false "activation-result-journal-failed"; then
            if send_ack "$result_id" false "activation-result-journal-failed"; then
                clear_activation_result "$result_id"
            fi
        fi
        return 1
    fi
    if send_ack "$result_id" "$result_ok" "$result_detail"; then
        clear_activation_result "$result_id"
    fi
    return 0
}

replay_activation_result() {
    expected="$1"
    [ -r "$COMMAND_RESULT_FILE" ] || return 1
    saved_id="$(sed -n '1p' "$COMMAND_RESULT_FILE" 2>/dev/null)"
    saved_state="$(sed -n '2p' "$COMMAND_RESULT_FILE" 2>/dev/null)"
    saved_detail="$(sed -n '3p' "$COMMAND_RESULT_FILE" 2>/dev/null)"
    if [ "$saved_id" != "$expected" ]; then
        case "$saved_state" in
            true|false) ;;
            *)
                logger -t "$TAG" "stale uncertain activation $saved_id superseded by $expected; rolling back before new command" 2>/dev/null || true
                rollback_active_access
                ;;
        esac
        rm -f "$COMMAND_RESULT_FILE"
        return 1
    fi
    case "$saved_state" in
        true|false)
            if send_ack "$saved_id" "$saved_state" "$saved_detail"; then
                clear_activation_result "$saved_id"
            fi
            ;;
        *)
            logger -t "$TAG" "activation command $saved_id had uncertain local result; rolling back before ACK" 2>/dev/null || true
            rollback_active_access
            if write_activation_result "$saved_id" false "activation-result-uncertain"; then
                if send_ack "$saved_id" false "activation-result-uncertain"; then
                    clear_activation_result "$saved_id"
                fi
            fi
            ;;
    esac
    return 0
}

rollback_active_access() {
    "$FIREWALL" clear >/dev/null 2>&1 || true
    [ ! -x "$EGRESS" ] || "$EGRESS" disable >/dev/null 2>&1 || true
}

rollback_batch_access() {
    count="$1"
    valid_uint "$count" || count=1
    [ "$count" -gt 1 ] || return 0
    rollback_active_access
}

pull_once() {
    mode="${1:-all}"
    case "$mode" in all|close-only) ;; *) mode=close-only ;; esac
    control_request GET "/api/v1/agent/pull" "$BODY" || return 1
    code="$CONTROL_CODE"
    [ "$code" = "204" ] && return 0
    [ "$code" = "200" ] || { logger -t "$TAG" "agent pull failed HTTP $code"; return 1; }

    id="$(jsonfilter -i "$BODY" -e '@.id' 2>/dev/null | sed -n '1p')"
    action="$(jsonfilter -i "$BODY" -e '@.action' 2>/dev/null | sed -n '1p')"
    if [ "$mode" = "close-only" ] && [ "$action" != "close" ]; then
        logger -t "$TAG" "status not published; pending ${action:-unknown} command left queued" 2>/dev/null || true
        return 0
    fi
    if [ "$action" = "activate" ]; then
        if replay_activation_result "$id"; then
            logger -t "$TAG" "activation command $id result replayed without re-execution" 2>/dev/null || true
            return 0
        fi
    else
        clear_activation_result
    fi
    expires_at="$(jsonfilter -i "$BODY" -e '@.expires_at' 2>/dev/null | sed -n '1p')"
    now="$(date +%s)"
    case "$expires_at" in ''|*[!0-9]*) ack "$id" false "invalid-expiry"; return 1 ;; esac
    [ "$expires_at" -gt "$now" ] || { ack "$id" false "command-expired"; return 0; }

    case "$action" in
        activate)
            source_ip="$(jsonfilter -i "$BODY" -e '@.source_ip' 2>/dev/null | sed -n '1p')"
            source_confidence="$(jsonfilter -i "$BODY" -e '@.source_confidence' 2>/dev/null | sed -n '1p')"
            family="$(jsonfilter -i "$BODY" -e '@.family' 2>/dev/null | sed -n '1p')"
            scope="$(jsonfilter -i "$BODY" -e '@.scope' 2>/dev/null | sed -n '1p')"
            access_method="$(jsonfilter -i "$BODY" -e '@.access_method' 2>/dev/null | sed -n '1p')"
            transport="$(jsonfilter -i "$BODY" -e '@.transport' 2>/dev/null | sed -n '1p')"
            wan="$(jsonfilter -i "$BODY" -e '@.wan' 2>/dev/null | sed -n '1p')"
            device="$(jsonfilter -i "$BODY" -e '@.device' 2>/dev/null | sed -n '1p')"
            service_id="$(jsonfilter -i "$BODY" -e '@.service_id' 2>/dev/null | sed -n '1p')"
            service_type="$(jsonfilter -i "$BODY" -e '@.service_type' 2>/dev/null | sed -n '1p')"
            wireguard="$(jsonfilter -i "$BODY" -e '@.wireguard' 2>/dev/null | sed -n '1p')"
            ingress_port="$(jsonfilter -i "$BODY" -e '@.ingress_port' 2>/dev/null | sed -n '1p')"
            service_port="$(jsonfilter -i "$BODY" -e '@.service_port' 2>/dev/null | sed -n '1p')"
            legacy_wg_port="$(jsonfilter -i "$BODY" -e '@.wg_port' 2>/dev/null | sed -n '1p')"
            external_address="$(jsonfilter -i "$BODY" -e '@.external_address' 2>/dev/null | sed -n '1p')"
            external_port="$(jsonfilter -i "$BODY" -e '@.external_port' 2>/dev/null | sed -n '1p')"
            egress_wan="$(jsonfilter -i "$BODY" -e '@.egress_wan' 2>/dev/null | sed -n '1p')"
            egress_wan_ipv4="$(jsonfilter -i "$BODY" -e '@.egress_wan_ipv4' 2>/dev/null | sed -n '1p')"
            egress_wan_ipv6="$(jsonfilter -i "$BODY" -e '@.egress_wan_ipv6' 2>/dev/null | sed -n '1p')"
            egress_mode="$(jsonfilter -i "$BODY" -e '@.egress_mode' 2>/dev/null | sed -n '1p')"
            batch_index="$(jsonfilter -i "$BODY" -e '@.batch_index' 2>/dev/null | sed -n '1p')"
            batch_count="$(jsonfilter -i "$BODY" -e '@.batch_count' 2>/dev/null | sed -n '1p')"
            ttl="$(jsonfilter -i "$BODY" -e '@.ttl' 2>/dev/null | sed -n '1p')"

            [ -n "$family" ] || family=ipv4
            [ -n "$scope" ] || scope=wg_ping
            [ -n "$access_method" ] || access_method=direct
            [ -n "$transport" ] || transport=udp
            [ -n "$service_type" ] || service_type=wireguard
            [ -n "$service_port" ] || service_port="$legacy_wg_port"
            [ -n "$ingress_port" ] || ingress_port="$service_port"
            [ -n "$service_id" ] && true || { valid_name "$wireguard" && service_id="wg.$wireguard"; }

            case "$access_method" in direct|mapped) ;; *) ack "$id" false "invalid-access-method"; return 1 ;; esac
            [ "$transport" = "udp" ] || { ack "$id" false "unsupported-transport"; return 1; }
            [ "$service_type" = "wireguard" ] || { ack "$id" false "unsupported-service"; return 1; }
            valid_name "$wan" && valid_device "$device" && valid_name "$wireguard" && valid_name "$service_id" && valid_port "$service_port" || { ack "$id" false "invalid-service-registration"; return 1; }
            [ "$service_id" = "wg.$wireguard" ] || { ack "$id" false "service-wireguard-mismatch"; return 1; }
            [ -x "$SERVICES" ] && "$SERVICES" validate "$service_id" udp "$service_port" >/dev/null 2>&1 || { ack "$id" false "service-not-registered"; return 1; }

            if [ "$access_method" = "direct" ]; then
                valid_port "$ingress_port" || { ack "$id" false "invalid-direct-ingress"; return 1; }
                [ "$ingress_port" = "$service_port" ] || { ack "$id" false "direct-ingress-service-mismatch"; return 1; }
            else
                [ "$family" = "ipv4" ] || { ack "$id" false "mapped-ipv4-required"; return 1; }
                [ -x "$MAPPING" ] || { ack "$id" false "mapped-endpoint-unavailable"; return 1; }
            fi

            valid_uint "$batch_index" || batch_index=0
            valid_uint "$batch_count" || batch_count=1
            [ "$batch_count" -ge 1 ] || batch_count=1
            if [ -z "$egress_mode" ]; then
                if [ "$batch_count" -gt 1 ]; then egress_mode=dual; else egress_mode="$family"; fi
            fi
            case "$egress_mode" in ipv4|ipv6|dual) ;; *) ack "$id" false "invalid-egress-mode"; return 1 ;; esac

            if [ -n "$egress_wan" ]; then valid_name "$egress_wan" || { ack "$id" false "invalid-egress-wan"; return 1; }; fi
            if [ -n "$egress_wan_ipv4" ]; then valid_name "$egress_wan_ipv4" || { ack "$id" false "invalid-ipv4-egress-wan"; return 1; }; fi
            if [ -n "$egress_wan_ipv6" ]; then valid_name "$egress_wan_ipv6" || { ack "$id" false "invalid-ipv6-egress-wan"; return 1; }; fi
            case "$egress_mode" in
                ipv4) [ -n "$egress_wan_ipv4" ] || egress_wan_ipv4="$egress_wan" ;;
                ipv6) [ -n "$egress_wan_ipv6" ] || egress_wan_ipv6="$egress_wan" ;;
                dual)
                    [ -n "$egress_wan_ipv4" ] || egress_wan_ipv4="$egress_wan"
                    [ -n "$egress_wan_ipv6" ] || egress_wan_ipv6="$egress_wan"
                    if { [ -n "$egress_wan_ipv4" ] && [ -z "$egress_wan_ipv6" ]; } || { [ -z "$egress_wan_ipv4" ] && [ -n "$egress_wan_ipv6" ]; }; then
                        rollback_batch_access "$batch_count"
                        ack "$id" false "incomplete-dual-egress-plan"
                        return 1
                    fi
                    ;;
            esac
            egress_requested=0
            if [ -n "$egress_wan_ipv4" ] || [ -n "$egress_wan_ipv6" ]; then egress_requested=1; fi

            case "$source_confidence" in
                verified) source_kind=web_verified ;;
                observed) source_kind=web_observed ;;
                candidate) source_kind=web_candidate ;;
                *) source_kind=web_verified ;;
            esac

            if [ "$batch_index" -eq 0 ] && [ -x "$EGRESS" ]; then "$EGRESS" disable >/dev/null 2>&1 || true; fi

            sync_firewall_policy || true
            mapped_detail=""
            if [ "$access_method" = "mapped" ]; then
                mapped_record="$("$MAPPING" resolve-current "$wan" "$device" "$service_id" 2>/dev/null || true)"
                if [ -z "$mapped_record" ]; then
                    logger -t "$TAG" "mapped activation has no current endpoint for ${wan}/${device}/${service_id}" 2>/dev/null || true
                    rollback_batch_access "$batch_count"
                    ack "$id" false "mapped-endpoint-unavailable"
                    return 1
                fi
                oldifs="$IFS"; IFS='|'; set -- $mapped_record; IFS="$oldifs"
                [ "$#" -eq 7 ] || { rollback_batch_access "$batch_count"; ack "$id" false "mapped-endpoint-invalid"; return 1; }
                [ "$1" = "$wan" ] && [ "$2" = "$device" ] && [ "$3" = "$service_id" ] || { rollback_batch_access "$batch_count"; ack "$id" false "mapped-endpoint-mismatch"; return 1; }
                external_address="$4"
                external_port="$5"
                ingress_port="$6"
                is_public_ipv4 "$external_address" && valid_port "$external_port" && valid_port "$ingress_port" || { rollback_batch_access "$batch_count"; ack "$id" false "mapped-endpoint-invalid"; return 1; }
                mapped_detail=" mapped-endpoint:${external_address}:${external_port}"
            fi

            if ! prepare_activation_command "$id"; then
                logger -t "$TAG" "activation result journal unavailable before side effects" 2>/dev/null || true
                rollback_batch_access "$batch_count"
                ack "$id" false "activation-result-journal-unavailable"
                return 1
            fi

            error_file="${TMP_BASE}.firewall-error"
            rm -f "$error_file"
            if "$FIREWALL" activate "$source_ip" "$family" "$scope" "$device" "$ingress_port" "$ttl" "$source_kind" 2>"$error_file"; then
                apply_egress=1
                if [ "$batch_count" -gt 1 ] && [ "$((batch_index + 1))" -lt "$batch_count" ]; then apply_egress=0; fi
                if [ "$egress_requested" -eq 1 ] && [ "$apply_egress" -eq 1 ]; then
                    egress_ok=false
                    if [ -x "$EGRESS" ]; then
                        case "$egress_mode" in
                            dual)
                                if [ "$egress_wan_ipv4" = "$egress_wan_ipv6" ]; then
                                    "$EGRESS" enable "$wireguard" "$egress_wan_ipv4" "$ttl" dual >/dev/null 2>"${TMP_BASE}.egress-error" && egress_ok=true
                                else
                                    "$EGRESS" enable-split "$wireguard" "$egress_wan_ipv4" "$egress_wan_ipv6" "$ttl" >/dev/null 2>"${TMP_BASE}.egress-error" && egress_ok=true
                                fi
                                ;;
                            ipv4) "$EGRESS" enable "$wireguard" "$egress_wan_ipv4" "$ttl" ipv4 >/dev/null 2>"${TMP_BASE}.egress-error" && egress_ok=true ;;
                            ipv6) "$EGRESS" enable "$wireguard" "$egress_wan_ipv6" "$ttl" ipv6 >/dev/null 2>"${TMP_BASE}.egress-error" && egress_ok=true ;;
                        esac
                    fi
                    if [ "$egress_ok" = true ]; then
                        finish_activation_command "$id" true "web-authorization-and-${egress_mode}-egress-active${mapped_detail}"
                    else
                        detail="$(sed -n 's/^ERROR: //p' "${TMP_BASE}.egress-error" 2>/dev/null | tail -n 1)"
                        [ -n "$detail" ] || detail="wireguard-egress-activation-failed"
                        logger -t "$TAG" "egress activation failed: $detail" 2>/dev/null || true
                        rollback_active_access
                        finish_activation_command "$id" false "$detail"
                    fi
                elif [ "$egress_requested" -eq 1 ]; then
                    finish_activation_command "$id" true "web-authorization-active-pending-egress${mapped_detail}"
                else
                    [ -x "$EGRESS" ] && "$EGRESS" disable >/dev/null 2>&1 || true
                    finish_activation_command "$id" true "web-authorization-active${mapped_detail}"
                fi
            else
                rollback_batch_access "$batch_count"
                [ -x "$EGRESS" ] && "$EGRESS" disable >/dev/null 2>&1 || true
                detail="$(sed -n 's/^ERROR: //p' "$error_file" 2>/dev/null | tail -n 1)"
                [ -n "$detail" ] || detail="$(tail -n 1 "$error_file" 2>/dev/null || true)"
                [ -n "$detail" ] || detail="firewall-activation-failed"
                logger -t "$TAG" "activation failed: $detail" 2>/dev/null || true
                finish_activation_command "$id" false "$detail"
            fi
            rm -f "$error_file" "${TMP_BASE}.egress-error"
            ;;
        close)
            close_ok=true
            "$FIREWALL" clear || close_ok=false
            [ ! -x "$EGRESS" ] || "$EGRESS" disable >/dev/null 2>&1 || close_ok=false
            if [ "$close_ok" = true ]; then ack "$id" true "all-authorizations-and-egress-cleared"; else ack "$id" false "gate-close-failed"; fi
            ;;
        *) ack "$id" false "unsupported-action" ;;
    esac
}

report_only() {
    sync_firewall_policy || true
    sync_egress
    if maybe_post_inventory; then
        post_status true || true
    else
        post_status false || true
    fi
}

run_once() {
    sync_firewall_policy || true
    sync_egress
    if ! maybe_post_inventory; then
        post_status false || true
        logger -t "$TAG" "inventory not synchronized; command pull skipped" 2>/dev/null || true
        return 0
    fi

    pull_mode=all
    if ! post_status true; then
        pull_mode=close-only
        logger -t "$TAG" "status not published; only close commands may be pulled" 2>/dev/null || true
    fi
    pull_rc=0
    pull_once "$pull_mode" || pull_rc=$?
    sync_egress
    post_status true || true
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
