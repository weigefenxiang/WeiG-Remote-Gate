#!/bin/sh
set -eu

valid_name() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }

wireguard_services() {
    command -v wg >/dev/null 2>&1 || return 0
    for name in $(wg show interfaces 2>/dev/null); do
        valid_name "$name" || continue
        port="$(wg show "$name" listen-port 2>/dev/null | sed -n '1p')"
        valid_uint "$port" || continue
        [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || continue
        printf 'wg.%s|wireguard|udp|%s|%s\n' "$name" "$name" "$port"
    done | sort -u
}

list_services() {
    wireguard_services
}

inventory_json() {
    first=1
    printf '['
    list_services | while IFS='|' read -r service_id service_type transport name service_port; do
        [ -n "$service_id" ] || continue
        [ "$first" -eq 1 ] || printf ','
        first=0
        printf '{"id":"%s","type":"%s","transport":"%s","name":"%s","service_port":%s}' \
            "$service_id" "$service_type" "$transport" "$name" "$service_port"
    done
    printf ']'
}

ports() {
    list_services | awk -F'|' '$3 == "udp" && $5 ~ /^[0-9]+$/ {print $5}' | sort -nu
}

validate_service() {
    expected_id="${1:-}"
    expected_transport="${2:-}"
    expected_port="${3:-}"
    valid_name "$expected_id" || return 1
    case "$expected_transport" in udp) ;; *) return 1 ;; esac
    valid_uint "$expected_port" || return 1
    [ "$expected_port" -ge 1 ] && [ "$expected_port" -le 65535 ] || return 1
    list_services | awk -F'|' \
        -v id="$expected_id" -v transport="$expected_transport" -v port="$expected_port" \
        '$1 == id && $3 == transport && $5 == port {found=1} END {exit found ? 0 : 1}'
}

case "${1:-inventory-json}" in
    list) list_services ;;
    inventory-json) inventory_json ;;
    ports) ports ;;
    validate)
        [ "$#" -eq 4 ] || { echo "usage: $0 validate <service-id> <transport> <service-port>" >&2; exit 2; }
        validate_service "$2" "$3" "$4"
        ;;
    *) echo "usage: $0 [list|inventory-json|ports|validate]" >&2; exit 2 ;;
esac
