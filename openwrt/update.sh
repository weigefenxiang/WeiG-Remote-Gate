#!/bin/sh
set -eu
umask 077

RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main}"
LIB_DIR="/usr/lib/remote-gate"
CONFIG_FILE="/etc/remote-gate.conf"
STATE_DIR="/etc/remote-gate-state"
INIT_FILE="/etc/init.d/remote-gate-agent"
HOTPLUG_FILE="/etc/hotplug.d/iface/95-remote-gate"
BACKUP_ROOT="/var/backups/weig-remote-gate"
TMP_DIR="/tmp/remote-gate-update.$$"
SUCCESS=0
BACKUP=""
NEW_FILES_INSTALLED=0

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || fail "Run this updater as root."
[ -d "$LIB_DIR" ] || fail "WeiG Remote Gate is not installed."
[ -r "$CONFIG_FILE" ] || fail "Missing $CONFIG_FILE"
for cmd in curl sh cp mv rm mkdir chmod date grep sed; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"
done

mkdir -p "$TMP_DIR"
trap 'rc=$?; if [ "$SUCCESS" -ne 1 ] && [ -n "$BACKUP" ] && [ -d "$BACKUP" ]; then
    printf "\nUpdate failed; restoring previous OpenWrt Remote Gate files...\n" >&2
    [ -x "$INIT_FILE" ] && "$INIT_FILE" stop >/dev/null 2>&1 || true
    if [ "$NEW_FILES_INSTALLED" -eq 1 ] && [ -x "$LIB_DIR/remote-gate-firewall.sh" ]; then
        "$LIB_DIR/remote-gate-firewall.sh" uninstall >/dev/null 2>&1 || true
    fi
    rm -rf "$LIB_DIR"
    [ -d "$BACKUP/remote-gate-lib" ] && cp -a "$BACKUP/remote-gate-lib" "$LIB_DIR"
    [ -f "$BACKUP/remote-gate.conf" ] && cp -a "$BACKUP/remote-gate.conf" "$CONFIG_FILE"
    rm -rf "$STATE_DIR"
    [ -d "$BACKUP/remote-gate-state" ] && cp -a "$BACKUP/remote-gate-state" "$STATE_DIR"
    [ -f "$BACKUP/remote-gate-agent.init" ] && cp -a "$BACKUP/remote-gate-agent.init" "$INIT_FILE"
    [ -f "$BACKUP/remote-gate-hotplug.sh" ] && { mkdir -p "$(dirname "$HOTPLUG_FILE")"; cp -a "$BACKUP/remote-gate-hotplug.sh" "$HOTPLUG_FILE"; }
    chmod 0755 "$LIB_DIR"/*.sh "$INIT_FILE" "$HOTPLUG_FILE" 2>/dev/null || true
    if [ -x "$LIB_DIR/remote-gate-firewall.sh" ]; then
        "$LIB_DIR/remote-gate-firewall.sh" install >/dev/null 2>&1 || true
    fi
    if [ -x "$LIB_DIR/remote-gate-agent.sh" ]; then
        "$LIB_DIR/remote-gate-agent.sh" sync-firewall >/dev/null 2>&1 || true
    fi
    [ -x "$INIT_FILE" ] && { "$INIT_FILE" enable >/dev/null 2>&1 || true; "$INIT_FILE" start >/dev/null 2>&1 || true; }
    printf "Backup retained at: %s\n" "$BACKUP" >&2
fi
rm -rf "$TMP_DIR"
exit "$rc"' EXIT INT TERM

fetch() {
    rel="$1" out="$2"
    curl -fsSL -H 'Cache-Control: no-cache' "${RAW_BASE}/openwrt/${rel}?_=$(date +%s)" -o "$out"
}

FILES="remote-gate-report.sh remote-gate-agent.sh remote-gate-firewall.sh remote-gate-firewall-include.sh remote-gate-agent.init remote-gate-hotplug.sh uninstall.sh"
info "Downloading OpenWrt update."
for rel in $FILES; do
    fetch "$rel" "$TMP_DIR/$rel"
done
curl -fsSL -H 'Cache-Control: no-cache' "${RAW_BASE}/VERSION?_=$(date +%s)" -o "$TMP_DIR/VERSION"

for rel in remote-gate-report.sh remote-gate-agent.sh remote-gate-firewall.sh remote-gate-firewall-include.sh remote-gate-agent.init remote-gate-hotplug.sh uninstall.sh; do
    sh -n "$TMP_DIR/$rel" || fail "Shell syntax check failed: $rel"
done

remote_version="$(sed -n '1p' "$TMP_DIR/VERSION")"
local_version="$(cat "$LIB_DIR/VERSION" 2>/dev/null || echo unknown)"
if [ "$remote_version" = "$local_version" ] && [ "${FORCE:-0}" != "1" ]; then
    printf 'WeiG Remote Gate is already up to date (%s).\n' "$local_version"
    SUCCESS=1
    trap - EXIT INT TERM
    rm -rf "$TMP_DIR"
    exit 0
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_ROOT/$stamp"
mkdir -p "$BACKUP_ROOT" "$BACKUP"
chmod 700 "$BACKUP_ROOT" "$BACKUP"
[ -d "$LIB_DIR" ] && cp -a "$LIB_DIR" "$BACKUP/remote-gate-lib"
[ -f "$CONFIG_FILE" ] && cp -a "$CONFIG_FILE" "$BACKUP/remote-gate.conf"
[ -d "$STATE_DIR" ] && cp -a "$STATE_DIR" "$BACKUP/remote-gate-state"
[ -f "$INIT_FILE" ] && cp -a "$INIT_FILE" "$BACKUP/remote-gate-agent.init"
[ -f "$HOTPLUG_FILE" ] && cp -a "$HOTPLUG_FILE" "$BACKUP/remote-gate-hotplug.sh"
command -v iptables-save >/dev/null 2>&1 && iptables-save > "$BACKUP/iptables-save.txt" 2>/dev/null || true
command -v ip6tables-save >/dev/null 2>&1 && ip6tables-save > "$BACKUP/ip6tables-save.txt" 2>/dev/null || true
command -v ipset >/dev/null 2>&1 && ipset save > "$BACKUP/ipset-save.txt" 2>/dev/null || true
if command -v uci >/dev/null 2>&1; then
    uci export firewall > "$BACKUP/firewall.uci" 2>/dev/null || true
    uci export network > "$BACKUP/network.uci" 2>/dev/null || true
fi
chmod -R go-rwx "$BACKUP"
info "Backup created: $BACKUP"

[ -x "$INIT_FILE" ] && "$INIT_FILE" stop >/dev/null 2>&1 || true
mkdir -p "$LIB_DIR" "$(dirname "$HOTPLUG_FILE")" "$STATE_DIR"
cp "$TMP_DIR/remote-gate-report.sh" "$LIB_DIR/remote-gate-report.sh"
cp "$TMP_DIR/remote-gate-agent.sh" "$LIB_DIR/remote-gate-agent.sh"
cp "$TMP_DIR/remote-gate-firewall.sh" "$LIB_DIR/remote-gate-firewall.sh"
cp "$TMP_DIR/remote-gate-firewall-include.sh" "$LIB_DIR/remote-gate-firewall-include.sh"
cp "$TMP_DIR/uninstall.sh" "$LIB_DIR/uninstall.sh"
cp "$TMP_DIR/remote-gate-agent.init" "$INIT_FILE"
cp "$TMP_DIR/remote-gate-hotplug.sh" "$HOTPLUG_FILE"
cp "$TMP_DIR/VERSION" "$LIB_DIR/VERSION"
chmod 0755 "$LIB_DIR"/*.sh "$INIT_FILE" "$HOTPLUG_FILE"
chmod 0644 "$LIB_DIR/VERSION"
NEW_FILES_INSTALLED=1

append_default() {
    key="$1" value="$2"
    grep -Eq "^${key}=" "$CONFIG_FILE" 2>/dev/null || printf "%s='%s'\n" "$key" "$value" >> "$CONFIG_FILE"
}
append_default GATE_IPV6 auto
append_default CONTROL_TRANSPORT auto
append_default NATMAP_DISCOVERY auto
chmod 0600 "$CONFIG_FILE"

mkdir -p "$STATE_DIR"
if [ ! -f "$STATE_DIR/install-manifest" ]; then
    {
        printf 'schema=1\n'
        printf 'wireguard_owned=0\n'
        printf 'firewall_include_owned=1\n'
        printf 'agent_owned=1\n'
    } > "$STATE_DIR/install-manifest"
    chmod 0600 "$STATE_DIR/install-manifest"
fi

"$LIB_DIR/remote-gate-firewall.sh" install >/dev/null || fail "Firewall integration failed."
"$LIB_DIR/remote-gate-agent.sh" sync-firewall || fail "Dual-stack firewall policy sync failed."
status="$("$LIB_DIR/remote-gate-firewall.sh" status-json 2>/dev/null || true)"
printf '%s\n' "$status" | grep -q '"ready":true' || fail "Firewall self-check did not report ready=true."

"$INIT_FILE" enable >/dev/null 2>&1 || true
"$INIT_FILE" start || fail "Remote Gate agent failed to start."
"$LIB_DIR/remote-gate-agent.sh" once || true

SUCCESS=1
trap - EXIT INT TERM
rm -rf "$TMP_DIR"
printf 'WeiG Remote Gate OpenWrt updated: %s -> %s\n' "$local_version" "$remote_version"
printf 'Backup: %s\n' "$BACKUP"
printf 'IPv6 Gate mode: %s\n' "$(sed -n "s/^GATE_IPV6='\([^']*\)'/\1/p" "$CONFIG_FILE" | sed -n '1p')"
printf 'WireGuard configuration was preserved.\n'
