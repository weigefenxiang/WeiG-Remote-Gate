#!/bin/sh
set -eu

RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main}"
LIB_DIR="/usr/lib/remote-gate"
CONFIG_FILE="/etc/remote-gate.conf"
INIT_FILE="/etc/init.d/remote-gate-agent"
HOTPLUG_FILE="/etc/hotplug.d/iface/95-remote-gate"
CRON_LINE="*/5 * * * * /usr/lib/remote-gate/remote-gate-report.sh"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "Run this installer as root."

for cmd in curl ubus jsonfilter awk sed grep sort uci ip; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"
done

printf '\nWeiG Remote Gate OpenWrt installer\n\n'
printf 'Public hostname (example: remote.example.com): '
IFS= read -r HOSTNAME
HOSTNAME="${HOSTNAME#http://}"
HOSTNAME="${HOSTNAME#https://}"
HOSTNAME="${HOSTNAME%%/*}"
[ -n "$HOSTNAME" ] || fail "Hostname is required."

if command -v stty >/dev/null 2>&1; then
    printf 'WRITE_TOKEN from the VPS installer: '
    stty -echo
    trap 'stty echo 2>/dev/null || true' EXIT INT TERM
    IFS= read -r WRITE_TOKEN
    stty echo
    trap - EXIT INT TERM
    printf '\n'
else
    printf 'WRITE_TOKEN from the VPS installer (input will be visible on this minimal system): '
    IFS= read -r WRITE_TOKEN
fi
[ "${#WRITE_TOKEN}" -ge 32 ] || fail "WRITE_TOKEN is too short."

mkdir -p "$LIB_DIR" "$(dirname "$HOTPLUG_FILE")"
chmod 0755 "$LIB_DIR"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P)"
fetch_file() {
    rel="$1"; out="$2"
    if [ -f "$SCRIPT_DIR/$rel" ]; then
        cp "$SCRIPT_DIR/$rel" "$out"
    else
        curl -fsSL "$RAW_BASE/openwrt/$rel" -o "$out"
    fi
}

fetch_file "remote-gate-report.sh" "$LIB_DIR/remote-gate-report.sh"
fetch_file "remote-gate-agent.sh" "$LIB_DIR/remote-gate-agent.sh"
fetch_file "remote-gate-firewall.sh" "$LIB_DIR/remote-gate-firewall.sh"
fetch_file "remote-gate-firewall-include.sh" "$LIB_DIR/remote-gate-firewall-include.sh"
fetch_file "remote-gate-agent.init" "$INIT_FILE"
fetch_file "remote-gate-hotplug.sh" "$HOTPLUG_FILE"
chmod 0755 "$LIB_DIR"/*.sh "$INIT_FILE" "$HOTPLUG_FILE"

BACKEND="$("$LIB_DIR/remote-gate-firewall.sh" detect 2>/dev/null)" || \
    fail "Unsupported firewall. Need fw4+nftables or fw3+iptables+ipset."
case "$BACKEND" in
    fw4-nftables) printf 'Detected firewall backend: firewall4 / nftables\n' ;;
    fw3-iptables) printf 'Detected firewall backend: firewall3 / iptables + ipset\n' ;;
    *) fail "Unsupported firewall backend: $BACKEND" ;;
esac
printf 'Remote Gate protects only ICMP echo and local WireGuard UDP ports on public WANs.\n'
printf 'FORWARD, DNAT, UPnP, NAT-PMP, qBittorrent and unrelated ports are not filtered by Remote Gate.\n\n'

cat > "$CONFIG_FILE" <<CFGEOF
HOSTNAME='$HOSTNAME'
WRITE_TOKEN='$WRITE_TOKEN'
MODE='auto'
INTERFACES='WAN2'
AGENT_INTERFACE=''
AGENT_INTERVAL='10'
CFGEOF
chmod 0600 "$CONFIG_FILE"

"$LIB_DIR/remote-gate-firewall.sh" install >/dev/null
"$LIB_DIR/remote-gate-agent.sh" sync-firewall || \
    fail "Initial public-WAN/WireGuard firewall policy sync failed."

if [ "$BACKEND" = "fw3-iptables" ]; then
    iptables -S INPUT | sed -n '1,4p'
else
    fw4 -q check
fi

grep -Fqx "$CRON_LINE" /etc/crontabs/root 2>/dev/null || \
    printf '%s\n' "$CRON_LINE" >> /etc/crontabs/root
[ -x /etc/init.d/cron ] && /etc/init.d/cron restart || true
"$INIT_FILE" enable
"$INIT_FILE" restart
FORCE=1 FORCE_INVENTORY=1 "$LIB_DIR/remote-gate-report.sh" || true
"$LIB_DIR/remote-gate-agent.sh" once || true

printf '\nWeiG Remote Gate OpenWrt components installed.\n'
printf 'Firewall backend: %s\n' "$BACKEND"
printf 'The WAN has no HTTP/HTTPS listener from this project.\n'
printf 'qBittorrent/BT port forwarding remains under the original firewall and is unaffected.\n'
printf 'Run: %s status-json\n' "$LIB_DIR/remote-gate-firewall.sh"
