#!/bin/sh
set -u

CONFIG_FILE="/etc/remote-gate.conf"
STATE_DIR="/etc/remote-gate-state"
PROBE_DIR="$STATE_DIR/wan-egress-probe"
INTERVAL="${WAN_EGRESS_PROBE_INTERVAL:-180}"

[ -r "$CONFIG_FILE" ] || exit 0
# shellcheck disable=SC1090
. "$CONFIG_FILE"
: "${HOSTNAME:?HOSTNAME is required}"
: "${WRITE_TOKEN:?WRITE_TOKEN is required}"

case "$INTERVAL" in ''|*[!0-9]*) INTERVAL=180 ;; esac
[ "$INTERVAL" -ge 60 ] || INTERVAL=60
mkdir -p "$PROBE_DIR"
chmod 700 "$PROBE_DIR" 2>/dev/null || true

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

safe_key() { printf '%s' "$1" | sed 's/[^A-Za-z0-9_.-]/_/g'; }

probe_device() {
    dev="$1"
    key="$(safe_key "$dev")"
    stamp_file="$PROBE_DIR/$key.last"
    now="$(date +%s)"
    last="$(cat "$stamp_file" 2>/dev/null || echo 0)"
    case "$last" in ''|*[!0-9]*) last=0 ;; esac
    [ "$((now - last))" -ge "$INTERVAL" ] || return 0

    # Throttle attempts even when the carrier path is temporarily unavailable.
    printf '%s\n' "$now" > "$stamp_file"
    chmod 600 "$stamp_file"

    code="$(curl -4 --interface "$dev" -sS \
        --connect-timeout 6 --max-time 15 \
        -o /dev/null -w '%{http_code}' \
        -X POST "https://${HOSTNAME}/api/v1/agent/egress-probe?device=${dev}" \
        -H "Authorization: Bearer ${WRITE_TOKEN}" 2>/dev/null)" || return 0
    [ "$code" = "204" ] || return 0
}

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
    printf '%s\n' "$targets" | grep -qx '0.0.0.0' || continue

    addresses="$(printf '%s' "$status" | jsonfilter -e '@["ipv4-address"][*].address' 2>/dev/null)"
    [ -n "$addresses" ] || continue
    public=0
    while IFS= read -r address; do
        [ -n "$address" ] || continue
        if is_public_ipv4 "$address"; then public=1; break; fi
    done <<EOF
$addresses
EOF
    [ "$public" -eq 0 ] || continue

    probe_device "$dev"
done
