#!/bin/bash
set -euo pipefail

RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main}"
OLD_ETC="/etc/wan2-vault"
OLD_STATE="/var/lib/wan2-vault"
OLD_SERVICE="wan2-vault.service"
NEW_ETC="/etc/remote-gate"
NEW_STATE="/var/lib/remote-gate"
NEW_LIB="/usr/local/lib/remote-gate"
NEW_SERVICE_FILE="/etc/systemd/system/remote-gate.service"
NEW_SERVICE="remote-gate.service"
BACKUP_ROOT="/var/backups/weig-remote-gate-migration"
CACHE_BUST="${REMOTE_GATE_CACHE_BUST:-$(date +%s)}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

[ "${EUID:-$(id -u)}" -eq 0 ] || fail "Run this migrator as root."
for cmd in systemctl python3 curl useradd install openssl; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"
done

[ -d "$OLD_ETC" ] || fail "Legacy /etc/wan2-vault was not found."
for f in config.json auth.json secrets.json; do
    [ -r "$OLD_ETC/$f" ] || fail "Missing legacy file: $OLD_ETC/$f"
done

case "$BACKUP_ROOT/" in
    "$OLD_STATE/"*) fail "Migration backup root must be outside $OLD_STATE" ;;
esac

OLD_ACTIVE=0
OLD_ENABLED=0
systemctl is-active --quiet "$OLD_SERVICE" && OLD_ACTIVE=1 || true
systemctl is-enabled --quiet "$OLD_SERVICE" && OLD_ENABLED=1 || true

TMP_DIR="$(mktemp -d)"
BACKUP=""
SUCCESS=0

rollback() {
    rc=$?
    if [ "$SUCCESS" -ne 1 ]; then
        printf '\nMigration failed; restoring legacy service state...\n' >&2
        systemctl stop "$NEW_SERVICE" >/dev/null 2>&1 || true
        if [ "$OLD_ENABLED" -eq 1 ]; then
            systemctl enable "$OLD_SERVICE" >/dev/null 2>&1 || true
        fi
        if [ "$OLD_ACTIVE" -eq 1 ]; then
            systemctl start "$OLD_SERVICE" >/dev/null 2>&1 || true
        fi
        [ -n "$BACKUP" ] && printf 'Backup retained at: %s\n' "$BACKUP" >&2
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

info "Downloading WeiG-Remote-Gate server files."
FILES=(
  "server/remote-gate.py"
  "server/remote-gate.service"
  "server/app/__init__.py"
  "server/app/config.py"
  "server/app/store.py"
  "server/app/security.py"
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
  "server/app/static/js/theme-bootstrap.js"
  "server/app/static/js/i18n.js"
  "server/app/static/js/theme.js"
  "server/app/static/js/fit-text.js"
  "server/app/static/js/workspace.js"
  "server/app/static/js/activity.js"
  "server/app/static/js/gate-controls.js"
  "server/app/static/js/app.js"
  "VERSION"
)
for rel in "${FILES[@]}"; do
    mkdir -p "$TMP_DIR/$(dirname "$rel")"
    fetch_raw "$rel" "$TMP_DIR/$rel"
done
python3 -m py_compile "$TMP_DIR"/server/app/*.py "$TMP_DIR/server/remote-gate.py"

HOSTNAME="$(python3 - "$OLD_ETC/config.json" <<'PY'
import json, sys
obj = json.load(open(sys.argv[1], encoding='utf-8'))
print(str(obj['public_hostname']).strip().lower().rstrip('.'))
PY
)"
WRITE_TOKEN="$(python3 - "$OLD_ETC/secrets.json" <<'PY'
import json, sys
obj = json.load(open(sys.argv[1], encoding='utf-8'))
print(str(obj['write_token']))
PY
)"
[ "${#WRITE_TOKEN}" -ge 32 ] || fail "Legacy WRITE_TOKEN is invalid."

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_ROOT/$stamp"
install -d -o root -g root -m 0700 "$BACKUP_ROOT"
install -d -o root -g root -m 0700 "$BACKUP"
cp -a "$OLD_ETC" "$BACKUP/etc-wan2-vault"
[ -d "$OLD_STATE" ] && cp -a "$OLD_STATE" "$BACKUP/state-wan2-vault"
[ -f /etc/systemd/system/wan2-vault.service ] && cp -a /etc/systemd/system/wan2-vault.service "$BACKUP/wan2-vault.service"
[ -d /usr/local/lib/wan2-vault ] && cp -a /usr/local/lib/wan2-vault "$BACKUP/lib-wan2-vault"

if ! id remotegate >/dev/null 2>&1; then
    useradd --system --home-dir "$NEW_STATE" --shell /usr/sbin/nologin remotegate
fi
install -d -o root -g remotegate -m 0750 "$NEW_ETC"
install -d -o remotegate -g remotegate -m 0700 "$NEW_STATE"
install -d -o root -g root -m 0755 "$NEW_LIB/app/templates" "$NEW_LIB/app/static/css" "$NEW_LIB/app/static/js"

install -o root -g remotegate -m 0640 "$OLD_ETC/config.json" "$NEW_ETC/config.json"
install -o root -g remotegate -m 0640 "$OLD_ETC/auth.json" "$NEW_ETC/auth.json"
install -o root -g remotegate -m 0640 "$OLD_ETC/secrets.json" "$NEW_ETC/secrets.json"

install -o root -g root -m 0755 "$TMP_DIR/server/remote-gate.py" "$NEW_LIB/remote-gate.py"
install -o root -g root -m 0644 "$TMP_DIR/server/remote-gate.service" "$NEW_SERVICE_FILE"
cp -a "$TMP_DIR/server/app/." "$NEW_LIB/app/"
find "$NEW_LIB/app" -type d -exec chmod 0755 {} +
find "$NEW_LIB/app" -type f -exec chmod 0644 {} +
install -o root -g root -m 0644 "$TMP_DIR/VERSION" "$NEW_LIB/VERSION"

if [ -r "$OLD_STATE/current.json" ]; then
    python3 - "$OLD_STATE/current.json" "$NEW_STATE/current.json" <<'PY'
import ipaddress, json, os, sys, tempfile
src, dst = sys.argv[1:]
try:
    old = json.load(open(src, encoding='utf-8'))
except Exception:
    old = {}

def private(value):
    try:
        a = ipaddress.ip_address(str(value))
    except ValueError:
        return True
    return a.version != 4 or a.is_private or a in ipaddress.ip_network('100.64.0.0/10') or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved

new = {'schema': 1, 'interfaces': {}}
items = old.get('interfaces', {}) if isinstance(old, dict) else {}
if isinstance(items, dict):
    for name, rec in items.items():
        if not isinstance(rec, dict):
            continue
        ip = str(rec.get('ip') or '')
        new['interfaces'][str(name)] = {
            'ip': ip,
            'device': str(rec.get('device') or ''),
            'address_type': 'private' if private(ip) else 'public',
            'active': bool(rec.get('active', True)),
            'changed_at': int(rec.get('changed_at', 0) or 0),
            'last_report_at': int(rec.get('last_report_at', 0) or 0),
            'last_report_status': str(rec.get('last_report_status') or ''),
        }
fd, tmp = tempfile.mkstemp(prefix='.current.', dir=os.path.dirname(dst), text=True)
with os.fdopen(fd, 'w', encoding='utf-8') as f:
    json.dump(new, f, ensure_ascii=False, separators=(',', ':'))
    f.write('\n')
os.chmod(tmp, 0o600)
os.replace(tmp, dst)
PY
    chown remotegate:remotegate "$NEW_STATE/current.json"
    chmod 0600 "$NEW_STATE/current.json"
fi

info "Switching localhost service from WAN2-Vault to Remote-Gate."
systemctl stop "$OLD_SERVICE" || true
systemctl disable "$OLD_SERVICE" >/dev/null 2>&1 || true
systemctl daemon-reload
systemctl enable "$NEW_SERVICE" >/dev/null
systemctl start "$NEW_SERVICE"

HEALTHY=0
HTTP_CODE=000
for _ in $(seq 1 15); do
    if systemctl is-active --quiet "$NEW_SERVICE"; then
        HTTP_CODE="$(curl -sS --connect-timeout 1 -o /dev/null -w '%{http_code}' -H "Host: $HOSTNAME" http://127.0.0.1:29444/healthz 2>/dev/null || true)"
        [ "$HTTP_CODE" = "200" ] && { HEALTHY=1; break; }
    fi
    sleep 1
done
[ "$HEALTHY" -eq 1 ] || {
    systemctl status "$NEW_SERVICE" --no-pager -l >&2 || true
    journalctl -u "$NEW_SERVICE" -n 80 --no-pager >&2 || true
    fail "Remote Gate health check failed (HTTP $HTTP_CODE)."
}

PULL_CODE="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Host: $HOSTNAME" \
    -H "Authorization: Bearer $WRITE_TOKEN" \
    http://127.0.0.1:29444/api/v1/agent/pull)"
[ "$PULL_CODE" = "204" ] || fail "Agent pull self-test failed (HTTP $PULL_CODE, expected 204)."

SUCCESS=1
trap - EXIT INT TERM
rm -rf "$TMP_DIR"
unset WRITE_TOKEN

printf '\n============================================================\n'
printf ' WeiG WAN2-Vault -> Remote-Gate migration successful\n'
printf '============================================================\n'
printf 'Version:       %s\n' "$(cat "$NEW_LIB/VERSION")"
printf 'Hostname:      %s\n' "$HOSTNAME"
printf 'Backend:       127.0.0.1:29444\n'
printf 'Agent API:     HTTP 204 verified locally\n'
printf 'Legacy service: stopped and disabled, files retained\n'
printf 'Backup:        %s\n' "$BACKUP"
printf '\nCloudflare Tunnel does not need to change if it already targets http://127.0.0.1:29444.\n'
printf 'The legacy WRITE_TOKEN and login credentials were preserved.\n'
