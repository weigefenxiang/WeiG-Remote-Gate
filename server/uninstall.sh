#!/bin/bash
set -euo pipefail
umask 077

BACKUP_ROOT="/var/backups/weig-remote-gate"
SERVICE="remote-gate.service"
UNIT="/etc/systemd/system/remote-gate.service"
ETC_DIR="/etc/remote-gate"
STATE_DIR="/var/lib/remote-gate"
LIB_DIR="/usr/local/lib/remote-gate"
PORT=29444
DRY_RUN=0
ASSUME_YES=0

usage() {
    cat <<'EOF'
Usage: uninstall.sh [--dry-run] [--yes]

Creates a local recovery backup, removes the WeiG Remote Gate VPS service and
application/state/config files, then verifies that the service and loopback
listener are gone. Cloudflare Tunnel configuration is intentionally preserved.
EOF
}

while (($#)); do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --yes|-y) ASSUME_YES=1 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "ERROR: Run as root." >&2; exit 1; }

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$BACKUP_ROOT/$timestamp"

cat <<EOF
WeiG Remote Gate safe VPS uninstall

Will remove:
  $SERVICE
  $UNIT
  $ETC_DIR
  $STATE_DIR
  $LIB_DIR

Will preserve:
  Cloudflare Tunnel / DNS configuration
  a local recovery backup

EOF

if ((DRY_RUN)); then
    echo "DRY RUN: no changes made."
    echo "Backup would be created under: $BACKUP_ROOT/<timestamp>"
    exit 0
fi

if ((!ASSUME_YES)); then
    read -r -p "Continue? [y/N] " answer
    case "$answer" in y|Y|yes|YES) ;; *) echo "Cancelled."; exit 0 ;; esac
fi

mkdir -p "$backup"
chmod 700 "$backup"
[[ -d "$ETC_DIR" ]] && cp -a "$ETC_DIR" "$backup/etc-remote-gate"
[[ -d "$STATE_DIR" ]] && cp -a "$STATE_DIR" "$backup/var-lib-remote-gate"
[[ -d "$LIB_DIR" ]] && cp -a "$LIB_DIR" "$backup/usr-local-lib-remote-gate"
[[ -f "$UNIT" ]] && cp -a "$UNIT" "$backup/remote-gate.service"
if command -v systemctl >/dev/null 2>&1; then
    systemctl status "$SERVICE" --no-pager > "$backup/service-status.txt" 2>&1 || true
fi
chmod -R go-rwx "$backup"
echo "Backup created: $backup"

systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true
rm -f "$UNIT"
systemctl daemon-reload
systemctl reset-failed "$SERVICE" >/dev/null 2>&1 || true

rm -rf "$LIB_DIR" "$ETC_DIR" "$STATE_DIR"

residue=0
systemctl is-active --quiet "$SERVICE" 2>/dev/null && residue=1 || true
[[ -e "$UNIT" || -e "$LIB_DIR" || -e "$ETC_DIR" || -e "$STATE_DIR" ]] && residue=1
if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | grep -Eq "127\.0\.0\.1:${PORT}([[:space:]]|$)|\[::1\]:${PORT}([[:space:]]|$)" && residue=1 || true
fi

if ((residue)); then
    echo "WARNING: residual Remote Gate objects were detected." >&2
    echo "Backup: $backup" >&2
    exit 1
fi

cat <<EOF

Remote Gate VPS components removed successfully.
Backup retained at:
  $backup

Cloudflare Tunnel/DNS was NOT removed. Remove or repoint the route separately
only if notify.weigshare.com is no longer needed.
EOF
