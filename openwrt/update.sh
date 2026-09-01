#!/bin/sh
set -eu
umask 077

RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main}"
RAW_PREFIX="https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/"
case "$RAW_BASE" in
    "${RAW_PREFIX}"dev/*)
        RAW_BASE="${RAW_PREFIX}refs/heads/${RAW_BASE#${RAW_PREFIX}}"
        ;;
esac
RAW_REF=""
case "$RAW_BASE" in
    "${RAW_PREFIX}"refs/heads/*)
        RAW_REF="${RAW_BASE#${RAW_PREFIX}refs/heads/}"
        ;;
    "${RAW_PREFIX}"*)
        RAW_REF="${RAW_BASE#${RAW_PREFIX}}"
        ;;
esac
GITHUB_API_BASE="https://api.github.com/repos/weigefenxiang/WeiG-Remote-Gate/contents"
LIB_DIR="/usr/lib/remote-gate"
CONFIG_FILE="/etc/remote-gate.conf"
STATE_DIR="/etc/remote-gate-state"
INIT_FILE="/etc/init.d/remote-gate-agent"
HOTPLUG_FILE="/etc/hotplug.d/iface/95-remote-gate"
PLATFORM="$LIB_DIR/remote-gate-platform.sh"
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
for cmd in curl sh cp mv rm mkdir chmod date grep sed; do command -v "$cmd" >/dev/null 2>&1 || fail "Missing core dependency: $cmd"; done
[ -r /etc/rc.common ] || fail "Missing OpenWrt rc.common service framework."

mkdir -p "$TMP_DIR"
trap 'rc=$?; if [ "$SUCCESS" -ne 1 ] && [ -n "$BACKUP" ] && [ -d "$BACKUP" ]; then
    printf "\nUpdate failed; restoring previous OpenWrt-family Remote Gate files...\n" >&2
    [ -x "$INIT_FILE" ] && "$INIT_FILE" stop >/dev/null 2>&1 || true
    [ -x "$LIB_DIR/remote-gate-mapping.sh" ] && "$LIB_DIR/remote-gate-mapping.sh" stop-all >/dev/null 2>&1 || true
    if [ "$NEW_FILES_INSTALLED" -eq 1 ] && [ -x "$LIB_DIR/remote-gate-firewall.sh" ]; then "$LIB_DIR/remote-gate-firewall.sh" uninstall >/dev/null 2>&1 || true; fi
    rm -rf "$LIB_DIR"; [ -d "$BACKUP/remote-gate-lib" ] && cp -a "$BACKUP/remote-gate-lib" "$LIB_DIR"
    [ -f "$BACKUP/remote-gate.conf" ] && cp -a "$BACKUP/remote-gate.conf" "$CONFIG_FILE"
    rm -rf "$STATE_DIR"; [ -d "$BACKUP/remote-gate-state" ] && cp -a "$BACKUP/remote-gate-state" "$STATE_DIR"
    [ -f "$BACKUP/remote-gate-agent.init" ] && cp -a "$BACKUP/remote-gate-agent.init" "$INIT_FILE"
    [ -f "$BACKUP/remote-gate-hotplug.sh" ] && { mkdir -p "$(dirname "$HOTPLUG_FILE")"; cp -a "$BACKUP/remote-gate-hotplug.sh" "$HOTPLUG_FILE"; }
    chmod 0755 "$LIB_DIR"/*.sh "$INIT_FILE" "$HOTPLUG_FILE" 2>/dev/null || true
    [ -f "$LIB_DIR/remote-gate-mapper" ] && chmod 0755 "$LIB_DIR/remote-gate-mapper" 2>/dev/null || true
    [ -x "$LIB_DIR/remote-gate-firewall.sh" ] && "$LIB_DIR/remote-gate-firewall.sh" install >/dev/null 2>&1 || true
    [ -x "$LIB_DIR/remote-gate-agent.sh" ] && "$LIB_DIR/remote-gate-agent.sh" sync-firewall >/dev/null 2>&1 || true
    [ -x "$INIT_FILE" ] && { "$INIT_FILE" enable >/dev/null 2>&1 || true; "$INIT_FILE" start >/dev/null 2>&1 || true; }
    printf "Backup retained at: %s\n" "$BACKUP" >&2
fi
rm -rf "$TMP_DIR"; exit "$rc"' EXIT INT TERM

fetch_api_raw() {
    repo_rel="$1"; out="$2"
    [ -n "$RAW_REF" ] || return 1
    api_url="${GITHUB_API_BASE}/${repo_rel}?ref=${RAW_REF}"
    curl -fsSL \
        -H 'Accept: application/vnd.github.raw+json' \
        -H 'X-GitHub-Api-Version: 2022-11-28' \
        -H 'User-Agent: WeiG-Remote-Gate-Updater' \
        "$api_url" -o "$out"
}

fetch_repo_path() {
    repo_rel="$1"; out="$2"; raw_url="${RAW_BASE}/${repo_rel}"
    if curl -fsSL -H 'Cache-Control: no-cache' "$raw_url" -o "$out" 2>/dev/null; then
        return 0
    fi
    rm -f "$out"
    printf 'WARN: Raw download failed; trying GitHub API: %s\n' "$repo_rel" >&2
    if fetch_api_raw "$repo_rel" "$out"; then
        return 0
    fi
    rm -f "$out"
    fail "Download failed from Raw and GitHub API: $repo_rel"
}

fetch() {
    rel="$1"; out="$2"
    fetch_repo_path "openwrt/${rel}" "$out"
}

FILES="remote-gate-platform.sh remote-gate-report.sh remote-gate-agent.sh remote-gate-egress-probe.sh remote-gate-wireguard-egress.sh remote-gate-service-registry.sh remote-gate-mapping.sh remote-gate-mapper-install.sh remote-gate-firewall.sh remote-gate-firewall-backends.sh remote-gate-wireguard-verify.sh remote-gate-firewall-include.sh remote-gate-audit.sh remote-gate-agent.init remote-gate-hotplug.sh uninstall.sh update.sh"
info "Downloading OpenWrt-family update."
for rel in $FILES; do fetch "$rel" "$TMP_DIR/$rel"; done
fetch_repo_path "VERSION" "$TMP_DIR/VERSION"
for rel in $FILES; do sh -n "$TMP_DIR/$rel" || fail "Shell syntax check failed: $rel"; done

sh "$TMP_DIR/remote-gate-platform.sh" core-capable || fail "Required OpenWrt-family core runtime capabilities are unavailable."
init_system="$(sh "$TMP_DIR/remote-gate-platform.sh" init 2>/dev/null || printf unknown)"
case "$init_system" in
    procd|rc.common) ;;
    *) fail "Unsupported OpenWrt-family service framework: $init_system" ;;
esac

remote_version="$(sed -n '1p' "$TMP_DIR/VERSION")"
local_version="$(cat "$LIB_DIR/VERSION" 2>/dev/null || echo unknown)"
if [ "$remote_version" = "$local_version" ] && [ "${FORCE:-0}" != "1" ]; then
    printf 'WeiG Remote Gate is already up to date (%s). Use FORCE=1 for a same-version development refresh.\n' "$local_version"; SUCCESS=1; trap - EXIT INT TERM; rm -rf "$TMP_DIR"; exit 0
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"; BACKUP="$BACKUP_ROOT/$stamp"
mkdir -p "$BACKUP_ROOT" "$BACKUP"; chmod 700 "$BACKUP_ROOT" "$BACKUP"
[ -d "$LIB_DIR" ] && cp -a "$LIB_DIR" "$BACKUP/remote-gate-lib"
[ -f "$CONFIG_FILE" ] && cp -a "$CONFIG_FILE" "$BACKUP/remote-gate.conf"
[ -d "$STATE_DIR" ] && cp -a "$STATE_DIR" "$BACKUP/remote-gate-state"
[ -f "$INIT_FILE" ] && cp -a "$BACKUP/remote-gate-agent.init" "$BACKUP/remote-gate-agent.init" 2>/dev/null || true
[ -f "$INIT_FILE" ] && cp -a "$INIT_FILE" "$BACKUP/remote-gate-agent.init"
[ -f "$HOTPLUG_FILE" ] && cp -a "$HOTPLUG_FILE" "$BACKUP/remote-gate-hotplug.sh"
command -v iptables-save >/dev/null 2>&1 && iptables-save > "$BACKUP/iptables-save.txt" 2>/dev/null || true
command -v ip6tables-save >/dev/null 2>&1 && ip6tables-save > "$BACKUP/ip6tables-save.txt" 2>/dev/null || true
command -v ipset >/dev/null 2>&1 && ipset save > "$BACKUP/ipset-save.txt" 2>/dev/null || true
if command -v uci >/dev/null 2>&1; then uci export firewall > "$BACKUP/firewall.uci" 2>/dev/null || true; uci export network > "$BACKUP/network.uci" 2>/dev/null || true; fi
chmod -R go-rwx "$BACKUP"; info "Backup created: $BACKUP"

[ -x "$INIT_FILE" ] && "$INIT_FILE" stop >/dev/null 2>&1 || true
[ -x "$LIB_DIR/remote-gate-mapping.sh" ] && "$LIB_DIR/remote-gate-mapping.sh" stop-all >/dev/null 2>&1 || true
mkdir -p "$LIB_DIR" "$(dirname "$HOTPLUG_FILE")" "$STATE_DIR"
for rel in remote-gate-platform.sh remote-gate-report.sh remote-gate-agent.sh remote-gate-egress-probe.sh remote-gate-wireguard-egress.sh remote-gate-service-registry.sh remote-gate-mapping.sh remote-gate-mapper-install.sh remote-gate-firewall.sh remote-gate-firewall-backends.sh remote-gate-wireguard-verify.sh remote-gate-firewall-include.sh remote-gate-audit.sh uninstall.sh update.sh; do cp "$TMP_DIR/$rel" "$LIB_DIR/$rel"; done
cp "$TMP_DIR/remote-gate-agent.init" "$INIT_FILE"
cp "$TMP_DIR/remote-gate-hotplug.sh" "$HOTPLUG_FILE"
cp "$TMP_DIR/VERSION" "$LIB_DIR/VERSION"
chmod 0755 "$LIB_DIR"/*.sh "$INIT_FILE" "$HOTPLUG_FILE"; chmod 0644 "$LIB_DIR/VERSION"; NEW_FILES_INSTALLED=1

MAPPER_SOURCE="${REMOTE_GATE_MAPPER_SOURCE:-}"
if [ -n "$MAPPER_SOURCE" ]; then
    sh "$LIB_DIR/remote-gate-mapper-install.sh" install-local "$MAPPER_SOURCE" || fail "Explicit mapper binary failed validation."
else
    mapper_channel=release
    [ "$RAW_REF" = dev ] && mapper_channel=dev
    if sh "$LIB_DIR/remote-gate-mapper-install.sh" "install-$mapper_channel"; then
        info "Mapper installed from the $mapper_channel channel for the exact Package ABI."
    else
        mapper_rc=$?
        if [ "$mapper_rc" -eq 3 ]; then
            printf 'WARN: No %s mapper is available for this exact Package ABI; existing mapper, if any, was preserved.\n' "$mapper_channel" >&2
        else
            printf 'WARN: %s mapper validation failed; existing mapper, if any, was preserved.\n' "$mapper_channel" >&2
        fi
    fi
fi

append_default() { key="$1" value="$2"; grep -Eq "^${key}=" "$CONFIG_FILE" 2>/dev/null || printf "%s='%s'\n" "$key" "$value" >> "$CONFIG_FILE"; }
append_default GATE_IPV6 disabled
append_default CONTROL_TRANSPORT auto
append_default MAPPED_ACCESS auto
grep -Ev '^NATMAP_DISCOVERY=' "$CONFIG_FILE" > "$TMP_DIR/remote-gate.conf.migrated" || true
mv "$TMP_DIR/remote-gate.conf.migrated" "$CONFIG_FILE"
chmod 0600 "$CONFIG_FILE"

mkdir -p "$STATE_DIR"
if [ ! -f "$STATE_DIR/install-manifest" ]; then
    { printf 'schema=2\n'; printf 'wireguard_owned=0\n'; printf 'firewall_include_owned=1\n'; printf 'agent_owned=1\n'; printf 'mapper_owned=1\n'; } > "$STATE_DIR/install-manifest"; chmod 0600 "$STATE_DIR/install-manifest"
else
    grep -Eq '^mapper_owned=' "$STATE_DIR/install-manifest" 2>/dev/null || printf 'mapper_owned=1\n' >> "$STATE_DIR/install-manifest"
fi

"$LIB_DIR/remote-gate-wireguard-egress.sh" cleanup-legacy >/dev/null || fail "Legacy WireGuard egress cleanup failed."
"$LIB_DIR/remote-gate-agent.sh" sync-firewall || fail "Pre-install firewall policy sync failed."
"$LIB_DIR/remote-gate-firewall.sh" install >/dev/null || fail "Firewall integration failed."
"$LIB_DIR/remote-gate-agent.sh" sync-firewall || fail "Post-install firewall policy sync failed."
status="$("$LIB_DIR/remote-gate-firewall.sh" status-json 2>/dev/null || true)"
printf '%s\n' "$status" | grep -q '"ready":true' || fail "Firewall self-check did not report ready=true."

"$INIT_FILE" enable >/dev/null 2>&1 || true
"$INIT_FILE" start || fail "Remote Gate agent failed to start."
"$LIB_DIR/remote-gate-egress-probe.sh" >/dev/null 2>&1 || true

DIST="$("$PLATFORM" distribution 2>/dev/null || printf unknown)"
RELEASE="$("$PLATFORM" release 2>/dev/null || printf unknown)"
INIT_SYSTEM="$("$PLATFORM" init 2>/dev/null || printf unknown)"
PKG_MANAGER="$("$PLATFORM" package-manager 2>/dev/null || printf none)"
PKG_ARCH="$("$PLATFORM" package-arch 2>/dev/null || true)"

SUCCESS=1; trap - EXIT INT TERM; rm -rf "$TMP_DIR"
printf 'WeiG Remote Gate OpenWrt-family updated: %s -> %s\n' "$local_version" "$remote_version"
printf 'Platform: %s %s | service=%s | package=%s | ABI=%s\n' "$DIST" "$RELEASE" "$INIT_SYSTEM" "$PKG_MANAGER" "${PKG_ARCH:-unknown}"
printf 'Backup: %s\n' "$BACKUP"
printf 'IPv6 Gate mode: %s\n' "$(sed -n "s/^GATE_IPV6='\([^']*\)'/\1/p" "$CONFIG_FILE" | sed -n '1p')"
if sh "$LIB_DIR/remote-gate-mapper-install.sh" current >/dev/null 2>&1; then
    printf 'Mapped Access: mapper binary matches current VERSION and exact Package ABI\n'
elif [ -x "$LIB_DIR/remote-gate-mapper" ]; then
    printf 'Mapped Access: mapper binary is present but delivery metadata is not current; validate before relying on mapping\n'
else
    printf 'Mapped Access: mapper binary unavailable; Direct/IPv6/Gate features remain enabled\n'
fi
printf 'Private/CGNAT WAN IPv4 egress probe: enabled\n'
printf 'Optional WG home Internet egress: runtime only, reboot returns it to OFF\n'
printf 'Read-only audit: %s/remote-gate-audit.sh\n' "$LIB_DIR"
printf 'Platform audit: %s summary\n' "$PLATFORM"
printf 'Mapper delivery audit: %s/remote-gate-mapper-install.sh status-json\n' "$LIB_DIR"
printf 'WireGuard configuration was preserved.\n'
