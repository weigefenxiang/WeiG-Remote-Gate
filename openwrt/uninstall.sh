#!/bin/sh
set -eu
umask 077

LIB_DIR="/usr/lib/remote-gate"
CONFIG_FILE="/etc/remote-gate.conf"
STATE_DIR="/etc/remote-gate-state"
INIT_FILE="/etc/init.d/remote-gate-agent"
HOTPLUG_FILE="/etc/hotplug.d/iface/95-remote-gate"
CRON_LINE="*/5 * * * * /usr/lib/remote-gate/remote-gate-report.sh"
BACKUP_ROOT="/var/backups/weig-remote-gate"
FW3_CHAIN_V4="WEIG_REMOTE_GATE"
FW3_CHAIN_V6="WEIG_REMOTE_GATE_V6"
IPSET_V4="weig_remote_gate_auth_v4"
IPSET_V6="weig_remote_gate_auth_v6"
FW4_TABLE_INCLUDE="/usr/share/nftables.d/table-pre/90-weig-remote-gate-sets.nft"
FW4_INPUT_INCLUDE="/usr/share/nftables.d/chain-pre/input/90-weig-remote-gate.nft"

DRY_RUN=0
ASSUME_YES=0
REMOVE_WIREGUARD=0

usage() {
    cat <<'EOF'
Usage: uninstall.sh [--dry-run] [--yes] [--remove-wireguard]

Default behavior:
  - backs up firewall/network/application state locally
  - removes only WeiG Remote Gate-owned firewall/application objects
  - preserves WireGuard configuration and Cloud/network settings
  - keeps the backup under /var/backups/weig-remote-gate/
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --yes|-y) ASSUME_YES=1 ;;
        --remove-wireguard) REMOVE_WIREGUARD=1 ;;
        --help|-h) usage; exit 0 ;;
        *) printf 'ERROR: Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

[ "$(id -u)" -eq 0 ] || { printf 'ERROR: Run as root.\n' >&2; exit 1; }

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$BACKUP_ROOT/$timestamp"

printf 'WeiG Remote Gate safe uninstall\n'
printf 'Will remove:\n'
printf '  Remote Gate agent/service, cron and hotplug hooks\n'
printf '  Remote Gate INPUT chains/ipsets or nft include objects\n'
printf '  Remote Gate application/config/state files\n'
printf 'Will preserve:\n'
printf '  WireGuard interface/keys/peers and WG firewall zone\n'
printf '  Existing FORWARD, DNAT, UPnP, NAT-PMP and qBittorrent rules\n'
printf '  A local recovery backup\n'
if [ "$REMOVE_WIREGUARD" -eq 1 ]; then
    printf 'Requested: remove WireGuard only if install manifest proves Remote Gate ownership.\n'
fi

if [ "$DRY_RUN" -eq 1 ]; then
    printf 'DRY RUN: no changes made.\n'
    printf 'Backup would be created under: %s/<timestamp>\n' "$BACKUP_ROOT"
    exit 0
fi

if [ "$ASSUME_YES" -ne 1 ]; then
    printf 'Continue? [y/N] '
    IFS= read -r answer
    case "$answer" in y|Y|yes|YES) ;; *) printf 'Cancelled.\n'; exit 0 ;; esac
fi

mkdir -p "$backup"
chmod 700 "$backup"

save_cmd() {
    name="$1"; shift
    if command -v "$1" >/dev/null 2>&1; then
        "$@" > "$backup/$name" 2>/dev/null || true
        chmod 600 "$backup/$name" 2>/dev/null || true
    fi
}

save_cmd iptables-save.txt iptables-save
save_cmd ip6tables-save.txt ip6tables-save
if command -v ipset >/dev/null 2>&1; then
    ipset save > "$backup/ipset-save.txt" 2>/dev/null || true
    chmod 600 "$backup/ipset-save.txt" 2>/dev/null || true
fi
if command -v uci >/dev/null 2>&1; then
    uci export firewall > "$backup/firewall.uci" 2>/dev/null || true
    uci export network > "$backup/network.uci" 2>/dev/null || true
    chmod 600 "$backup/firewall.uci" "$backup/network.uci" 2>/dev/null || true
fi
[ -f /etc/firewall.user ] && cp -a /etc/firewall.user "$backup/firewall.user" || true
[ -f /etc/crontabs/root ] && cp -a /etc/crontabs/root "$backup/root.crontab" || true
[ -f "$CONFIG_FILE" ] && cp -a "$CONFIG_FILE" "$backup/remote-gate.conf" || true
[ -d "$STATE_DIR" ] && cp -a "$STATE_DIR" "$backup/remote-gate-state" || true
[ -d "$LIB_DIR" ] && cp -a "$LIB_DIR" "$backup/remote-gate-lib" || true
[ -f "$INIT_FILE" ] && cp -a "$INIT_FILE" "$backup/remote-gate-agent.init" || true
[ -f "$HOTPLUG_FILE" ] && cp -a "$HOTPLUG_FILE" "$backup/remote-gate-hotplug.sh" || true
printf 'Backup created: %s\n' "$backup"

if [ -x "$INIT_FILE" ]; then
    "$INIT_FILE" disable >/dev/null 2>&1 || true
    "$INIT_FILE" stop >/dev/null 2>&1 || true
fi

firewall_ok=1
if [ -x "$LIB_DIR/remote-gate-firewall.sh" ]; then
    "$LIB_DIR/remote-gate-firewall.sh" clear >/dev/null 2>&1 || true
    "$LIB_DIR/remote-gate-firewall.sh" uninstall >/dev/null 2>&1 || firewall_ok=0
else
    if command -v uci >/dev/null 2>&1; then
        uci -q delete firewall.remote_gate >/dev/null 2>&1 || true
        uci commit firewall >/dev/null 2>&1 || true
    fi
    if command -v iptables >/dev/null 2>&1; then
        while iptables -C INPUT -j "$FW3_CHAIN_V4" >/dev/null 2>&1; do
            iptables -D INPUT -j "$FW3_CHAIN_V4" >/dev/null 2>&1 || break
        done
        iptables -F "$FW3_CHAIN_V4" >/dev/null 2>&1 || true
        iptables -X "$FW3_CHAIN_V4" >/dev/null 2>&1 || true
    fi
    if command -v ip6tables >/dev/null 2>&1; then
        while ip6tables -C INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1; do
            ip6tables -D INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1 || break
        done
        ip6tables -F "$FW3_CHAIN_V6" >/dev/null 2>&1 || true
        ip6tables -X "$FW3_CHAIN_V6" >/dev/null 2>&1 || true
    fi
    if command -v ipset >/dev/null 2>&1; then
        ipset destroy "$IPSET_V4" >/dev/null 2>&1 || true
        ipset destroy "$IPSET_V6" >/dev/null 2>&1 || true
    fi
    had_fw4=0
    [ -e "$FW4_TABLE_INCLUDE" ] && had_fw4=1
    [ -e "$FW4_INPUT_INCLUDE" ] && had_fw4=1
    rm -f "$FW4_TABLE_INCLUDE" "$FW4_INPUT_INCLUDE"
    if [ "$had_fw4" -eq 1 ] && [ -x /etc/init.d/firewall ]; then
        /etc/init.d/firewall reload >/dev/null 2>&1 || firewall_ok=0
    fi
fi

if [ "$firewall_ok" -ne 1 ]; then
    printf 'ERROR: Remote Gate firewall cleanup failed; application files were preserved.\n' >&2
    printf 'Recovery backup: %s\n' "$backup" >&2
    exit 1
fi

if [ -f /etc/crontabs/root ]; then
    grep -Fvx "$CRON_LINE" /etc/crontabs/root > "/tmp/remote-gate-cron.$$" || true
    mv "/tmp/remote-gate-cron.$$" /etc/crontabs/root
    /etc/init.d/cron restart >/dev/null 2>&1 || true
fi

rm -f "$INIT_FILE" "$HOTPLUG_FILE"

if [ "$REMOVE_WIREGUARD" -eq 1 ]; then
    manifest="$STATE_DIR/install-manifest"
    wg_owned="$(sed -n 's/^wireguard_owned=//p' "$manifest" 2>/dev/null | sed -n '1p')"
    if [ "$wg_owned" = "1" ]; then
        printf 'WireGuard ownership is recorded, but automatic WG deletion is intentionally disabled in v0.3.0 development builds.\n'
        printf 'WireGuard was preserved for safety.\n'
    else
        printf 'WireGuard is not recorded as Remote Gate-owned; preserving it.\n'
    fi
fi

rm -rf "$LIB_DIR"
rm -f "$CONFIG_FILE"
rm -rf "$STATE_DIR"

residue=0
if command -v iptables >/dev/null 2>&1; then
    iptables -S INPUT 2>/dev/null | grep -Fq "$FW3_CHAIN_V4" && residue=1 || true
    iptables -S "$FW3_CHAIN_V4" >/dev/null 2>&1 && residue=1 || true
fi
if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -S INPUT 2>/dev/null | grep -Fq "$FW3_CHAIN_V6" && residue=1 || true
    ip6tables -S "$FW3_CHAIN_V6" >/dev/null 2>&1 && residue=1 || true
fi
if command -v ipset >/dev/null 2>&1; then
    ipset list -n 2>/dev/null | grep -Eq "^(${IPSET_V4}|${IPSET_V6})$" && residue=1 || true
fi
[ -e "$FW4_TABLE_INCLUDE" ] && residue=1
[ -e "$FW4_INPUT_INCLUDE" ] && residue=1
if command -v uci >/dev/null 2>&1; then
    uci -q get firewall.remote_gate >/dev/null 2>&1 && residue=1 || true
fi
ps 2>/dev/null | grep '[r]emote-gate-agent.sh' >/dev/null 2>&1 && residue=1 || true

if [ "$residue" -ne 0 ]; then
    printf 'WARNING: residual Remote Gate objects were detected. Do not delete the backup.\n' >&2
    printf 'Backup: %s\n' "$backup" >&2
    exit 1
fi

printf '\nRemote Gate removed successfully.\n'
printf 'Backup retained at: %s\n' "$backup"
printf 'WireGuard configuration was preserved.\n'
printf 'Original firewall ownership remains with OpenWrt; no full iptables snapshot was blindly restored.\n'
