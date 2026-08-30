#!/bin/bash
set -euo pipefail
umask 077

RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main}"
ETC_DIR="/etc/remote-gate"
LIB_DIR="/usr/local/lib/remote-gate"
SERVICE_FILE="/etc/systemd/system/remote-gate.service"
SERVICE_NAME="remote-gate.service"
BACKUP_ROOT="/var/backups/weig-remote-gate"
CACHE_BUST="${REMOTE_GATE_CACHE_BUST:-$(date +%s)}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

[ "${EUID:-$(id -u)}" -eq 0 ] || fail "Run this updater as root."
for cmd in systemctl python3 curl install; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"
done
[ -r "$ETC_DIR/config.json" ] || fail "WeiG Remote Gate is not installed."
[ -r "$ETC_DIR/secrets.json" ] || fail "Missing $ETC_DIR/secrets.json"

TMP_DIR="$(mktemp -d)"
BACKUP=""
SUCCESS=0

rollback() {
    rc=$?
    if [ "$SUCCESS" -ne 1 ] && [ -n "$BACKUP" ] && [ -d "$BACKUP" ]; then
        printf '\nUpdate failed; restoring previous Remote Gate files...\n' >&2
        systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
        rm -rf "$LIB_DIR"
        [ -d "$BACKUP/lib" ] && cp -a "$BACKUP/lib" "$LIB_DIR"
        if [ -f "$BACKUP/remote-gate.service" ]; then
            cp -a "$BACKUP/remote-gate.service" "$SERVICE_FILE"
        else
            rm -f "$SERVICE_FILE"
        fi
        systemctl daemon-reload || true
        systemctl start "$SERVICE_NAME" || true
        printf 'Backup retained at: %s\n' "$BACKUP" >&2
    fi
    rm -rf "$TMP_DIR"
    exit "$rc"
}
trap rollback EXIT INT TERM

fetch_raw() {
    local rel="$1" out="$2" sep='?'
    [[ "$RAW_BASE" == *\?* ]] && sep='&'
    curl -fsSL -H 'Cache-Control: no-cache' "${RAW_BASE}/${rel}${sep}_=${CACHE_BUST}" -o "$out"
}

FILES=(
  "server/remote-gate.py"
  "server/remote-gate.service"
  "server/uninstall.sh"
  "server/app/__init__.py"
  "server/app/config.py"
  "server/app/store.py"
  "server/app/security.py"
  "server/app/client_sources.py"
  "server/app/endpoints.py"
  "server/app/gate.py"
  "server/app/main.py"
  "server/app/templates/login.html"
  "server/app/templates/dashboard.html"
  "server/app/static/css/tokens.css"
  "server/app/static/css/base.css"
  "server/app/static/css/components.css"
  "server/app/static/css/layout.css"
  "server/app/static/css/dashboard.css"
  "server/app/static/css/themes.css"
  "server/app/static/css/spatial.css"
  "server/app/static/js/theme-bootstrap.js"
  "server/app/static/js/i18n.js"
  "server/app/static/js/theme.js"
  "server/app/static/js/utility-panel.js"
  "server/app/static/js/fit-text.js"
  "server/app/static/js/workspace.js"
  "server/app/static/js/activity.js"
  "server/app/static/js/gate-controls.js"
  "server/app/static/js/app.js"
  "VERSION"
)

info "Downloading WeiG Remote Gate update."
for rel in "${FILES[@]}"; do
    mkdir -p "$TMP_DIR/$(dirname "$rel")"
    fetch_raw "$rel" "$TMP_DIR/$rel"
done
python3 -m py_compile "$TMP_DIR"/server/app/*.py "$TMP_DIR/server/remote-gate.py"
bash -n "$TMP_DIR/server/uninstall.sh"

REMOTE_VERSION="$(sed -n '1p' "$TMP_DIR/VERSION")"
LOCAL_VERSION="$(cat "$LIB_DIR/VERSION" 2>/dev/null || echo unknown)"
if [ "$LOCAL_VERSION" = "$REMOTE_VERSION" ] && [ "${FORCE:-0}" != "1" ]; then
    printf 'WeiG Remote Gate is already up to date (%s).\n' "$LOCAL_VERSION"
    SUCCESS=1
    trap - EXIT INT TERM
    rm -rf "$TMP_DIR"
    exit 0
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_ROOT/$stamp"
install -d -o root -g root -m 0700 "$BACKUP_ROOT" "$BACKUP"
[ -d "$LIB_DIR" ] && cp -a "$LIB_DIR" "$BACKUP/lib"
[ -f "$SERVICE_FILE" ] && cp -a "$SERVICE_FILE" "$BACKUP/remote-gate.service"
chmod -R go-rwx "$BACKUP"

systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
rm -rf "$LIB_DIR"
install -d -o root -g root -m 0755 "$LIB_DIR/app"
install -o root -g root -m 0755 "$TMP_DIR/server/remote-gate.py" "$LIB_DIR/remote-gate.py"
install -o root -g root -m 0755 "$TMP_DIR/server/uninstall.sh" "$LIB_DIR/uninstall.sh"
install -o root -g root -m 0644 "$TMP_DIR/server/remote-gate.service" "$SERVICE_FILE"
cp -a "$TMP_DIR/server/app/." "$LIB_DIR/app/"
find "$LIB_DIR/app" -type d -exec chmod 0755 {} +
find "$LIB_DIR/app" -type f -exec chmod 0644 {} +
install -o root -g root -m 0644 "$TMP_DIR/VERSION" "$LIB_DIR/VERSION"

systemctl daemon-reload
systemctl restart "$SERVICE_NAME"

HOSTNAME="$(python3 - "$ETC_DIR/config.json" <<'PY'
import json, sys
print(str(json.load(open(sys.argv[1], encoding='utf-8'))['public_hostname']).strip().lower().rstrip('.'))
PY
)"
WRITE_TOKEN="$(python3 - "$ETC_DIR/secrets.json" <<'PY'
import json, sys
print(str(json.load(open(sys.argv[1], encoding='utf-8'))['write_token']))
PY
)"

HEALTHY=0
HTTP_CODE=000
for _ in $(seq 1 15); do
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        HTTP_CODE="$(curl -sS --connect-timeout 1 -o /dev/null -w '%{http_code}' -H "Host: $HOSTNAME" http://127.0.0.1:29444/healthz 2>/dev/null || true)"
        if [ "$HTTP_CODE" = "200" ]; then
            HEALTHY=1
            break
        fi
    fi
    sleep 1
done
[ "$HEALTHY" -eq 1 ] || fail "Updated service failed health check (HTTP $HTTP_CODE)."

PULL_CODE="$(curl -sS -o /dev/null -w '%{http_code}' -H "Host: $HOSTNAME" -H "Authorization: Bearer $WRITE_TOKEN" http://127.0.0.1:29444/api/v1/agent/pull)"
[ "$PULL_CODE" = "204" ] || [ "$PULL_CODE" = "200" ] || fail "Agent API self-test failed (HTTP $PULL_CODE)."

SUCCESS=1
trap - EXIT INT TERM
rm -rf "$TMP_DIR"
unset WRITE_TOKEN
printf 'WeiG Remote Gate updated: %s -> %s\n' "$LOCAL_VERSION" "$REMOTE_VERSION"
printf 'Backup: %s\n' "$BACKUP"
printf 'Safe uninstall: %s/uninstall.sh --dry-run\n' "$LIB_DIR"
