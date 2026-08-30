#!/bin/sh
set -eu

RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main}"
LIB_DIR="/usr/lib/remote-gate"
CONFIG_FILE="/etc/remote-gate.conf"
INIT_FILE="/etc/init.d/remote-gate-agent"
CRON_LINE="*/5 * * * * /usr/lib/remote-gate/remote-gate-report.sh"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Run this installer as root."

for cmd in curl ubus jsonfilter nft fw4 awk sed grep; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"
done

printf '\nWeiG Remote Gate OpenWrt installer\n\n'
printf 'Public hostname (example: remote.example.com): '
IFS= read -r HOSTNAME
HOSTNAME="${HOSTNAME#http://}"
HOSTNAME="${HOSTNAME#https://}"
HOSTNAME="${HOSTNAME%%/*}"
[ -n "$HOSTNAME" ] || fail "Hostname is required."

printf 'WRITE_TOKEN from the VPS installer: '
stty -echo
IFS= read -r WRITE_TOKEN
stty echo
printf '\n'
[ "${#WRITE_TOKEN}" -ge 32 ] || fail "WRITE_TOKEN is too short."

mkdir -p "$LIB_DIR"
chmod 0755 "$LIB_DIR"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P)"
fetch_file() {
    rel="$1"
    out="$2"
    if [ -f "$SCRIPT_DIR/$rel" ]; then
        cp "$SCRIPT_DIR/$rel" "$out"
    else
        curl -fsSL "$RAW_BASE/openwrt/$rel" -o "$out"
    fi
}

fetch_file "remote-gate-report.sh" "$LIB_DIR/remote-gate-report.sh"
fetch_file "remote-gate-agent.sh" "$LIB_DIR/remote-gate-agent.sh"
fetch_file "remote-gate-firewall.sh" "$LIB_DIR/remote-gate-firewall.sh"
fetch_file "remote-gate-agent.init" "$INIT_FILE"
chmod 0755 "$LIB_DIR"/*.sh "$INIT_FILE"

cat > "$CONFIG_FILE" <<EOF
HOSTNAME='$HOSTNAME'
WRITE_TOKEN='$WRITE_TOKEN'
MODE='auto'
INTERFACES='WAN2'
AGENT_INTERFACE=''
AGENT_INTERVAL='10'
EOF
chmod 0600 "$CONFIG_FILE"

"$LIB_DIR/remote-gate-firewall.sh" install

grep -Fqx "$CRON_LINE" /etc/crontabs/root 2>/dev/null || {
    printf '%s\n' "$CRON_LINE" >> /etc/crontabs/root
}
if [ -x /etc/init.d/cron ]; then
    /etc/init.d/cron restart
fi

"$INIT_FILE" enable
"$INIT_FILE" restart

FORCE=1 FORCE_INVENTORY=1 "$LIB_DIR/remote-gate-report.sh" || true
"$LIB_DIR/remote-gate-agent.sh" once || true

printf '\nWeiG Remote Gate OpenWrt components installed.\n'
printf 'The WAN has no HTTP/HTTPS listener from this project.\n'
printf 'WireGuard will appear in the dashboard when `wg show interfaces` reports it.\n'
