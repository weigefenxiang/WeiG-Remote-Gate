#!/bin/bash
set -euo pipefail
umask 077

PROJECT="WeiG-Remote-Gate"
RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main}"
ETC_DIR="/etc/remote-gate"
STATE_DIR="/var/lib/remote-gate"
LIB_DIR="/usr/local/lib/remote-gate"
SERVICE_FILE="/etc/systemd/system/remote-gate.service"
SERVICE_NAME="remote-gate.service"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

[ "${EUID:-$(id -u)}" -eq 0 ] || fail "Run this installer as root."
command -v systemctl >/dev/null 2>&1 || fail "systemd is required."

for cmd in python3 openssl curl; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"
done

printf '\nWeiG Remote Gate server installer\n\n'

while :; do
    read -r -p "Public hostname (example: remote.example.com): " PUBLIC_HOSTNAME
    PUBLIC_HOSTNAME="${PUBLIC_HOSTNAME#http://}"
    PUBLIC_HOSTNAME="${PUBLIC_HOSTNAME#https://}"
    PUBLIC_HOSTNAME="${PUBLIC_HOSTNAME%%/*}"
    if [[ "$PUBLIC_HOSTNAME" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] && [[ "$PUBLIC_HOSTNAME" == *.* ]]; then
        PUBLIC_HOSTNAME="${PUBLIC_HOSTNAME,,}"
        break
    fi
    echo "Invalid hostname."
done

while :; do
    read -r -p "Login username: " LOGIN_USERNAME
    [ -n "$LOGIN_USERNAME" ] && [ "${#LOGIN_USERNAME}" -le 128 ] && break
    echo "Username must be 1-128 characters."
done

while :; do
    printf 'Login password (minimum 12 characters): '
    stty -echo
    IFS= read -r LOGIN_PASSWORD
    stty echo
    printf '\n'
    [ "${#LOGIN_PASSWORD}" -ge 12 ] || { echo "Password is too short."; continue; }
    printf 'Confirm password: '
    stty -echo
    IFS= read -r LOGIN_PASSWORD_2
    stty echo
    printf '\n'
    [ "$LOGIN_PASSWORD" = "$LOGIN_PASSWORD_2" ] || { echo "Passwords do not match."; continue; }
    unset LOGIN_PASSWORD_2
    break
done

if ! id remotegate >/dev/null 2>&1; then
    useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin remotegate
fi

install -d -o root -g remotegate -m 0750 "$ETC_DIR"
install -d -o remotegate -g remotegate -m 0700 "$STATE_DIR"
install -d -o root -g root -m 0755 "$LIB_DIR/app/templates" "$LIB_DIR/app/static/css" "$LIB_DIR/app/static/js"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"; unset LOGIN_PASSWORD || true' EXIT
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"

fetch_file() {
    local rel="$1" out="$2"
    if [ -f "$SCRIPT_DIR/../$rel" ]; then
        cp "$SCRIPT_DIR/../$rel" "$out"
    else
        curl -fsSL "$RAW_BASE/$rel" -o "$out"
    fi
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

for rel in "${FILES[@]}"; do
    mkdir -p "$TMP_DIR/$(dirname "$rel")"
    fetch_file "$rel" "$TMP_DIR/$rel"
done

python3 -m py_compile "$TMP_DIR"/server/app/*.py "$TMP_DIR/server/remote-gate.py"
bash -n "$TMP_DIR/server/uninstall.sh"

install -o root -g root -m 0755 "$TMP_DIR/server/remote-gate.py" "$LIB_DIR/remote-gate.py"
install -o root -g root -m 0755 "$TMP_DIR/server/uninstall.sh" "$LIB_DIR/uninstall.sh"
install -o root -g root -m 0644 "$TMP_DIR/server/remote-gate.service" "$SERVICE_FILE"
cp -a "$TMP_DIR/server/app/." "$LIB_DIR/app/"
find "$LIB_DIR/app" -type d -exec chmod 0755 {} +
find "$LIB_DIR/app" -type f -exec chmod 0644 {} +
install -o root -g root -m 0644 "$TMP_DIR/VERSION" "$LIB_DIR/VERSION"

SALT_HEX="$(openssl rand -hex 16)"
WRITE_TOKEN="$(openssl rand -hex 32)"
SESSION_SECRET_HEX="$(openssl rand -hex 32)"

PASSWORD_FILE="$TMP_DIR/.password"
printf '%s' "$LOGIN_PASSWORD" > "$PASSWORD_FILE"
chmod 0600 "$PASSWORD_FILE"
PASSWORD_HASH_HEX="$(python3 - "$SALT_HEX" "$PASSWORD_FILE" <<'PY'
import hashlib, pathlib, sys
salt = bytes.fromhex(sys.argv[1])
password = pathlib.Path(sys.argv[2]).read_bytes()
print(hashlib.scrypt(password, salt=salt, n=16384, r=8, p=1, dklen=32).hex())
PY
)"
rm -f "$PASSWORD_FILE"
unset LOGIN_PASSWORD

cat > "$ETC_DIR/config.json" <<EOF
{
  "public_hostname": "$PUBLIC_HOSTNAME",
  "bind_host": "127.0.0.1",
  "bind_port": 29444
}
EOF

python3 - "$ETC_DIR/auth.json" "$LOGIN_USERNAME" "$SALT_HEX" "$PASSWORD_HASH_HEX" <<'PY'
import json, sys
path, username, salt, pw_hash = sys.argv[1:]
with open(path, "w", encoding="utf-8") as handle:
    json.dump({
        "username": username,
        "salt_hex": salt,
        "password_hash_hex": pw_hash,
        "scrypt": {"n": 16384, "r": 8, "p": 1, "dklen": 32}
    }, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY

cat > "$ETC_DIR/secrets.json" <<EOF
{
  "write_token": "$WRITE_TOKEN",
  "session_secret_hex": "$SESSION_SECRET_HEX"
}
EOF

chown root:remotegate "$ETC_DIR"/*.json
chmod 0640 "$ETC_DIR"/*.json

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
sleep 1
systemctl is-active --quiet "$SERVICE_NAME" || {
    systemctl status "$SERVICE_NAME" --no-pager || true
    fail "Service failed to start."
}

HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' -H "Host: $PUBLIC_HOSTNAME" http://127.0.0.1:29444/healthz)"
[ "$HTTP_CODE" = "200" ] || fail "Local self-test failed (HTTP $HTTP_CODE)."

printf '\n============================================================\n'
printf ' WeiG Remote Gate installed successfully\n'
printf '============================================================\n\n'
printf 'Version:       %s\n' "$(cat "$LIB_DIR/VERSION")"
printf 'Hostname:      %s\n' "$PUBLIC_HOSTNAME"
printf 'Backend:       127.0.0.1:29444 (localhost only)\n'
printf 'WRITE_TOKEN:   %s\n' "$WRITE_TOKEN"
printf '\nStore WRITE_TOKEN only on the OpenWrt device and the VPS secret file.\n'
printf 'Recommended public path: Cloudflare Tunnel -> http://127.0.0.1:29444\n'
printf 'Safe uninstall: %s/uninstall.sh --dry-run\n' "$LIB_DIR"
