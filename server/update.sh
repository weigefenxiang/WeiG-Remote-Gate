#!/bin/bash
set -euo pipefail
umask 077

REPO="weigefenxiang/WeiG-Remote-Gate"
RAW_PREFIX="https://raw.githubusercontent.com/${REPO}/"
GITHUB_API="https://api.github.com/repos/${REPO}"
GITHUB_CONTENTS="${GITHUB_API}/contents"
RAW_BASE="${REMOTE_GATE_RAW_BASE:-${RAW_PREFIX}main}"
case "$RAW_BASE" in
  "${RAW_PREFIX}"dev/*)
    RAW_BASE="${RAW_PREFIX}refs/heads/${RAW_BASE#${RAW_PREFIX}}"
    ;;
esac
ETC_DIR="/etc/remote-gate"
LIB_DIR="/usr/local/lib/remote-gate"
SERVICE_FILE="/etc/systemd/system/remote-gate.service"
SERVICE_NAME="remote-gate.service"
BACKUP_ROOT="/var/backups/weig-remote-gate"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
info() { printf '==> %s\n' "$*"; }

[ "${EUID:-$(id -u)}" -eq 0 ] || fail "Run this updater as root."
for cmd in systemctl python3 curl install; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"
done
[ -r "$ETC_DIR/config.json" ] || fail "WeiG Remote Gate is not installed."
[ -r "$ETC_DIR/secrets.json" ] || fail "Missing $ETC_DIR/secrets.json"

resolve_build_sha() {
    local suffix ref sha
    suffix="${RAW_BASE#${RAW_PREFIX}}"
    [ "$suffix" != "$RAW_BASE" ] || return 1
    if [[ "$suffix" =~ ^[0-9a-fA-F]{40}$ ]]; then
        printf '%s\n' "${suffix,,}"
        return 0
    fi
    case "$suffix" in
      refs/heads/*) ref="${suffix#refs/heads/}" ;;
      refs/tags/*) ref="${suffix#refs/tags/}" ;;
      *) ref="$suffix" ;;
    esac
    sha="$(
        curl -fsSL \
          -H 'Accept: application/vnd.github+json' \
          -H 'X-GitHub-Api-Version: 2022-11-28' \
          -H 'User-Agent: WeiG-Remote-Gate-Updater' \
          --get --data-urlencode "sha=$ref" --data-urlencode 'per_page=1' \
          "$GITHUB_API/commits" |
        python3 -c 'import json,re,sys; d=json.load(sys.stdin); s=(d[0].get("sha","") if isinstance(d,list) and d else ""); sys.stdout.write(s if re.fullmatch(r"[0-9a-fA-F]{40}",s) else "")'
    )" || return 1
    [[ "$sha" =~ ^[0-9a-fA-F]{40}$ ]] || return 1
    printf '%s\n' "${sha,,}"
}

BUILD_SHA="${REMOTE_GATE_BUILD_SHA:-}"
if [ -z "$BUILD_SHA" ]; then
    BUILD_SHA="$(resolve_build_sha)" || fail "Could not resolve GitHub build SHA from $RAW_BASE"
fi
[[ "$BUILD_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || fail "Invalid build SHA: $BUILD_SHA"
BUILD_SHA="${BUILD_SHA,,}"
BUILD_SHORT="${BUILD_SHA:0:12}"
# Freeze the whole deployment to one immutable commit before downloading files.
RAW_BASE="${RAW_PREFIX}${BUILD_SHA}"

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
    local rel="$1" out="$2" url="${RAW_BASE}/${rel}" api_url="${GITHUB_CONTENTS}/${rel}?ref=${BUILD_SHA}"
    if curl -fsSL -H 'Cache-Control: no-cache' "$url" -o "$out"; then
        return 0
    fi
    warn "Raw download failed; trying GitHub API: $rel"
    if ! curl -fsSL \
      -H 'Accept: application/vnd.github.raw+json' \
      -H 'X-GitHub-Api-Version: 2022-11-28' \
      -H 'User-Agent: WeiG-Remote-Gate-Updater' \
      "$api_url" -o "$out"; then
        fail "Download failed from Raw and GitHub API: $rel"
    fi
}

FILES=(
  "server/remote-gate.py"
  "server/remote-gate.service"
  "server/uninstall.sh"
  "server/update.sh"
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
  "server/app/static/Wei.G.ico"
  "server/app/static/css/tokens.css"
  "server/app/static/css/base.css"
  "server/app/static/css/components.css"
  "server/app/static/css/layout.css"
  "server/app/static/css/dashboard.css"
  "server/app/static/css/themes.css"
  "server/app/static/css/spatial.css"
  "server/app/static/css/interaction.css"
  "server/app/static/css/feedback.css"
  "server/app/static/js/theme-bootstrap.js"
  "server/app/static/js/i18n.js"
  "server/app/static/js/theme.js"
  "server/app/static/js/utility-panel.js"
  "server/app/static/js/fit-text.js"
  "server/app/static/js/workspace.js"
  "server/app/static/js/activity.js"
  "server/app/static/js/motion-feedback.js"
  "server/app/static/js/ui-feedback.js"
  "server/app/static/js/client-sources.js"
  "server/app/static/js/endpoint-picker.js"
  "server/app/static/js/duration-control.js"
  "server/app/static/js/gate-controls.js"
  "server/app/static/js/app.js"
  "VERSION"
)

info "Downloading WeiG Remote Gate update at build $BUILD_SHORT."
for rel in "${FILES[@]}"; do
    mkdir -p "$TMP_DIR/$(dirname "$rel")"
    fetch_raw "$rel" "$TMP_DIR/$rel"
done
python3 -m py_compile "$TMP_DIR"/server/app/*.py "$TMP_DIR/server/remote-gate.py"
bash -n "$TMP_DIR/server/uninstall.sh"
bash -n "$TMP_DIR/server/update.sh"

REMOTE_VERSION="$(sed -n '1p' "$TMP_DIR/VERSION")"
LOCAL_VERSION="$(cat "$LIB_DIR/VERSION" 2>/dev/null || echo unknown)"
LOCAL_BUILD="$(cat "$LIB_DIR/BUILD" 2>/dev/null || true)"

python3 - "$TMP_DIR/server/app/templates" "$REMOTE_VERSION" "$BUILD_SHA" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
version = sys.argv[2].strip()
build = sys.argv[3].strip().lower()
replacements = {
    "{{ASSET_VERSION}}": build,
    "{{VERSION}}": version,
    "{{BUILD_SHA}}": build,
    "{{BUILD_SHORT}}": build[:12],
}
for name in ("login.html", "dashboard.html"):
    path = root / name
    text = path.read_text(encoding="utf-8")
    for token, value in replacements.items():
        text = text.replace(token, value)
    leftovers = [token for token in replacements if token in text]
    if leftovers:
        raise SystemExit(f"unresolved build token(s) in {name}: {leftovers}")
    path.write_text(text, encoding="utf-8")
PY
printf '%s\n' "$BUILD_SHA" > "$TMP_DIR/BUILD"

if [ "$LOCAL_VERSION" = "$REMOTE_VERSION" ] && [ "$LOCAL_BUILD" = "$BUILD_SHA" ] && [ "${FORCE:-0}" != "1" ]; then
    printf 'WeiG Remote Gate is already up to date (%s, build %s).\n' "$LOCAL_VERSION" "$BUILD_SHORT"
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
install -o root -g root -m 0755 "$TMP_DIR/server/update.sh" "$LIB_DIR/update.sh"
install -o root -g root -m 0644 "$TMP_DIR/server/remote-gate.service" "$SERVICE_FILE"
cp -a "$TMP_DIR/server/app/." "$LIB_DIR/app/"
find "$LIB_DIR/app" -type d -exec chmod 0755 {} +
find "$LIB_DIR/app" -type f -exec chmod 0644 {} +
install -o root -g root -m 0644 "$TMP_DIR/VERSION" "$LIB_DIR/VERSION"
install -o root -g root -m 0644 "$TMP_DIR/BUILD" "$LIB_DIR/BUILD"

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
printf 'Build: %s\n' "$BUILD_SHA"
printf 'Backup: %s\n' "$BACKUP"
printf 'Safe update: %s/update.sh\n' "$LIB_DIR"
printf 'Safe uninstall: %s/uninstall.sh --dry-run\n' "$LIB_DIR"
