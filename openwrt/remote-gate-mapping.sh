#!/bin/sh
set -eu

CONFIG_FILE="${REMOTE_GATE_CONFIG_FILE:-/etc/remote-gate.conf}"
LIB_DIR="${REMOTE_GATE_LIB_DIR:-/usr/lib/remote-gate}"
STATE_DIR="${REMOTE_GATE_MAPPING_STATE_DIR:-/tmp/remote-gate/mapping}"
MAPPER_BIN="${REMOTE_GATE_MAPPER_BIN:-$LIB_DIR/remote-gate-mapper}"
SERVICES="${REMOTE_GATE_SERVICE_REGISTRY:-$LIB_DIR/remote-gate-service-registry.sh}"
TAG="remote-gate-mapping"

if [ -r "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    . "$CONFIG_FILE"
fi

MAPPED_ACCESS="${MAPPED_ACCESS:-auto}"
MAPPER_STUN_HOST="${MAPPER_STUN_HOST:-stun.cloudflare.com}"
MAPPER_STUN_PORT="${MAPPER_STUN_PORT:-3478}"
MAPPER_KEEPALIVE="${MAPPER_KEEPALIVE:-20}"
MAPPER_IDLE_TIMEOUT="${MAPPER_IDLE_TIMEOUT:-180}"
MAPPER_MAX_SESSIONS="${MAPPER_MAX_SESSIONS:-64}"

case "$MAPPED_ACCESS" in auto|disabled) ;; *) MAPPED_ACCESS=auto ;; esac

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR" 2>/dev/null || true

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

mapper_available() {
    [ "$MAPPED_ACCESS" != "disabled" ] && [ -x "$MAPPER_BIN" ] && [ -x "$SERVICES" ] && command -v jsonfilter >/dev/null 2>&1
}

entry_key() {
    device="$1"; service_id="$2"
    printf '%s.%s' "$device" "$service_id" | sed 's/[^A-Za-z0-9_.-]/_/g'
}

meta_path() { printf '%s/%s.meta\n' "$STATE_DIR" "$1"; }
pid_path() { printf '%s/%s.pid\n' "$STATE_DIR" "$1"; }
status_path() { printf '%s/%s.status.json\n' "$STATE_DIR" "$1"; }
go_path() { printf '%s/%s.go\n' "$STATE_DIR" "$1"; }

owned_pid() {
    pid="$1"; status="$2"
    valid_uint "$pid" || return 1
    [ -r "/proc/$pid/cmdline" ] || return 1
    cmd="$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
    [ -n "$cmd" ] || return 1
    base="$(basename "$MAPPER_BIN")"
    printf '%s\n' "$cmd" | grep -Fq "$base" || return 1
    printf '%s\n' "$cmd" | grep -Fq "$status" || return 1
}

stop_key() {
    key="$1"
    pfile="$(pid_path "$key")"; sfile="$(status_path "$key")"
    pid="$(sed -n '1p' "$pfile" 2>/dev/null || true)"
    if owned_pid "$pid" "$sfile"; then
        kill "$pid" 2>/dev/null || true
        n=0
        while owned_pid "$pid" "$sfile" && [ "$n" -lt 5 ]; do
            sleep 1
            n=$((n + 1))
        done
        owned_pid "$pid" "$sfile" && kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$(meta_path "$key")" "$pfile" "$sfile" "$(go_path "$key")"
}

stop_all() {
    for pfile in "$STATE_DIR"/*.pid; do
        [ -f "$pfile" ] || continue
        key="$(basename "$pfile" .pid)"
        stop_key "$key"
    done
    rm -f "$STATE_DIR"/*.meta "$STATE_DIR"/*.status.json "$STATE_DIR"/*.go 2>/dev/null || true
}

parse_entry() {
    raw="$1"
    oldifs="$IFS"; IFS=','; set -- $raw; IFS="$oldifs"
    [ "$#" -eq 4 ] || return 1
    ENTRY_WAN="$1"; ENTRY_DEVICE="$2"; ENTRY_SERVICE_ID="$3"; ENTRY_SERVICE_PORT="$4"
    valid_name "$ENTRY_WAN" || return 1
    valid_device "$ENTRY_DEVICE" || return 1
    valid_name "$ENTRY_SERVICE_ID" || return 1
    valid_port "$ENTRY_SERVICE_PORT" || return 1
    "$SERVICES" validate "$ENTRY_SERVICE_ID" udp "$ENTRY_SERVICE_PORT" >/dev/null 2>&1 || return 1
}

start_entry() {
    wan="$1"; device="$2"; service_id="$3"; service_port="$4"
    key="$(entry_key "$device" "$service_id")"
    meta="$(meta_path "$key")"; pfile="$(pid_path "$key")"; status="$(status_path "$key")"; go="$(go_path "$key")"

    old_meta="$(cat "$meta" 2>/dev/null || true)"
    expected="${wan}|${device}|${service_id}|${service_port}"
    pid="$(sed -n '1p' "$pfile" 2>/dev/null || true)"
    if [ "$old_meta" = "$expected" ] && owned_pid "$pid" "$status"; then
        return 0
    fi

    stop_key "$key"
    printf '%s\n' "$expected" > "$meta"
    chmod 600 "$meta"
    rm -f "$go" "$status"

    "$MAPPER_BIN" \
        --device "$device" \
        --service-id "$service_id" \
        --service-port "$service_port" \
        --status-file "$status" \
        --go-file "$go" \
        --stun-host "$MAPPER_STUN_HOST" \
        --stun-port "$MAPPER_STUN_PORT" \
        --keepalive "$MAPPER_KEEPALIVE" \
        --idle-timeout "$MAPPER_IDLE_TIMEOUT" \
        --max-sessions "$MAPPER_MAX_SESSIONS" \
        >/dev/null 2>&1 &
    pid=$!
    printf '%s\n' "$pid" > "$pfile"
    chmod 600 "$pfile"
}

sync_prepare() {
    if ! mapper_available; then
        stop_all
        return 0
    fi

    desired="$STATE_DIR/.desired.$$"
    : > "$desired"
    trap 'rm -f "$desired"' EXIT INT TERM

    for raw in "$@"; do
        if ! parse_entry "$raw"; then
            logger -t "$TAG" "ignored invalid mapped-access desired entry" 2>/dev/null || true
            continue
        fi
        key="$(entry_key "$ENTRY_DEVICE" "$ENTRY_SERVICE_ID")"
        printf '%s\n' "$key" >> "$desired"
        start_entry "$ENTRY_WAN" "$ENTRY_DEVICE" "$ENTRY_SERVICE_ID" "$ENTRY_SERVICE_PORT"
    done
    sort -u "$desired" -o "$desired"

    for pfile in "$STATE_DIR"/*.pid; do
        [ -f "$pfile" ] || continue
        key="$(basename "$pfile" .pid)"
        grep -Fqx "$key" "$desired" 2>/dev/null || stop_key "$key"
    done
    rm -f "$desired"
    trap - EXIT INT TERM
}

status_value() {
    file="$1"; expr="$2"
    jsonfilter -i "$file" -e "$expr" 2>/dev/null | sed -n '1p'
}

ingress_ports() {
    mapper_available || return 0
    for status in "$STATE_DIR"/*.status.json; do
        [ -f "$status" ] || continue
        state="$(status_value "$status" '@.state')"
        case "$state" in prepared|active) ;; *) continue ;; esac
        port="$(status_value "$status" '@.ingress_port')"
        valid_port "$port" || continue
        printf '%s\n' "$port"
    done | sort -nu
}

activate_prepared() {
    mapper_available || return 0
    for status in "$STATE_DIR"/*.status.json; do
        [ -f "$status" ] || continue
        state="$(status_value "$status" '@.state')"
        [ "$state" = "prepared" ] || continue
        port="$(status_value "$status" '@.ingress_port')"
        valid_port "$port" || continue
        key="$(basename "$status" .status.json)"
        pfile="$(pid_path "$key")"
        pid="$(sed -n '1p' "$pfile" 2>/dev/null || true)"
        owned_pid "$pid" "$status" || continue
        : > "$(go_path "$key")"
        chmod 600 "$(go_path "$key")" 2>/dev/null || true
    done
}

mapping_record() {
    status="$1"
    key="$(basename "$status" .status.json)"
    meta="$(meta_path "$key")"
    [ -r "$meta" ] || return 1
    line="$(sed -n '1p' "$meta")"
    oldifs="$IFS"; IFS='|'; set -- $line; IFS="$oldifs"
    [ "$#" -eq 4 ] || return 1
    wan="$1"; device="$2"; service_id="$3"; service_port="$4"
    valid_name "$wan" && valid_device "$device" && valid_name "$service_id" && valid_port "$service_port" || return 1
    "$SERVICES" validate "$service_id" udp "$service_port" >/dev/null 2>&1 || return 1

    state="$(status_value "$status" '@.state')"
    [ "$state" = "active" ] || return 1
    external="$(status_value "$status" '@.external_address')"
    external_port="$(status_value "$status" '@.external_port')"
    ingress_port="$(status_value "$status" '@.ingress_port')"
    observed_at="$(status_value "$status" '@.observed_at')"
    is_public_ipv4 "$external" || return 1
    valid_port "$external_port" && valid_port "$ingress_port" || return 1
    valid_uint "$observed_at" || observed_at=0

    printf '%s|%s|%s|%s|%s|%s|%s\n' \
        "$wan" "$device" "$service_id" "$external" "$external_port" "$ingress_port" "$observed_at"
}

inventory_json() {
    first=1
    printf '['
    for status in "$STATE_DIR"/*.status.json; do
        [ -f "$status" ] || continue
        record="$(mapping_record "$status" 2>/dev/null || true)"
        [ -n "$record" ] || continue
        oldifs="$IFS"; IFS='|'; set -- $record; IFS="$oldifs"
        [ "$first" -eq 1 ] || printf ','
        first=0
        printf '{"wan":"%s","device":"%s","family":"ipv4","transport":"udp","external_address":"%s","external_port":%s,"ingress_port":%s,"service_id":"%s","observed_at":%s}' \
            "$1" "$2" "$4" "$5" "$6" "$3" "$7"
    done
    printf ']'
}

validate_ingress() {
    [ "$#" -eq 5 ] || return 1
    expected_device="$1"; expected_service="$2"; expected_ingress="$3"; expected_external="$4"; expected_external_port="$5"
    valid_device "$expected_device" && valid_name "$expected_service" && valid_port "$expected_ingress" && is_public_ipv4 "$expected_external" && valid_port "$expected_external_port" || return 1
    for status in "$STATE_DIR"/*.status.json; do
        [ -f "$status" ] || continue
        record="$(mapping_record "$status" 2>/dev/null || true)"
        [ -n "$record" ] || continue
        oldifs="$IFS"; IFS='|'; set -- $record; IFS="$oldifs"
        [ "$2" = "$expected_device" ] || continue
        [ "$3" = "$expected_service" ] || continue
        [ "$6" = "$expected_ingress" ] || continue
        [ "$4" = "$expected_external" ] || continue
        [ "$5" = "$expected_external_port" ] || continue
        return 0
    done
    return 1
}

status_json() {
    if [ "$MAPPED_ACCESS" = "disabled" ]; then
        printf '{"available":false,"state":"unavailable","active_mappings":0,"detail":"disabled"}'
        return 0
    fi
    if ! mapper_available; then
        printf '{"available":false,"state":"unavailable","active_mappings":0,"detail":"mapper-binary-unavailable"}'
        return 0
    fi
    active=0; prepared=0; failed=0
    for status in "$STATE_DIR"/*.status.json; do
        [ -f "$status" ] || continue
        state="$(status_value "$status" '@.state')"
        case "$state" in
            active) active=$((active + 1)) ;;
            prepared) prepared=$((prepared + 1)) ;;
            failed) failed=$((failed + 1)) ;;
        esac
    done
    if [ "$active" -gt 0 ]; then state=active; detail="";
    elif [ "$prepared" -gt 0 ]; then state=preparing; detail="waiting-for-firewall";
    elif [ "$failed" -gt 0 ]; then state=failed; detail="mapping-not-established";
    else state=idle; detail=""; fi
    printf '{"available":true,"state":"%s","active_mappings":%s,"detail":"%s"}' "$state" "$active" "$detail"
}

case "${1:-status-json}" in
    available) mapper_available ;;
    sync-prepare) shift; sync_prepare "$@" ;;
    ingress-ports) ingress_ports ;;
    activate-prepared) activate_prepared ;;
    inventory-json) inventory_json ;;
    validate-ingress)
        shift
        [ "$#" -eq 5 ] || { echo "usage: $0 validate-ingress <device> <service-id> <ingress-port> <external-address> <external-port>" >&2; exit 2; }
        validate_ingress "$@"
        ;;
    status-json) status_json ;;
    stop-all|cleanup) stop_all ;;
    *) echo "usage: $0 available|sync-prepare [wan,device,service,port ...]|ingress-ports|activate-prepared|inventory-json|validate-ingress ...|status-json|stop-all" >&2; exit 2 ;;
esac
