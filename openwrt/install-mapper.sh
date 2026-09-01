#!/bin/sh
set -eu
umask 077

CHANNEL="${1:-release}"
case "$CHANNEL" in release|dev) ;; *) echo "usage: $0 [release|dev]" >&2; exit 2 ;; esac
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root" >&2; exit 1; }
LIB_DIR="${REMOTE_GATE_LIB_DIR:-/usr/lib/remote-gate}"
[ -r "$LIB_DIR/VERSION" ] || { echo "ERROR: install/update WeiG Remote Gate before installing the mapper" >&2; exit 1; }
[ -r "$LIB_DIR/remote-gate-platform.sh" ] || { echo "ERROR: Remote Gate platform helper is missing" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "ERROR: curl is required" >&2; exit 1; }

if [ "$CHANNEL" = dev ]; then
    RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/refs/heads/dev}"
    ACTION=install-dev
else
    RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main}"
    ACTION=install
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/remote-gate-mapper-bootstrap.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT INT TERM
curl -fsSL "$RAW_BASE/openwrt/remote-gate-mapper-install.sh" -o "$tmp/remote-gate-mapper-install.sh"
curl -fsSL "$RAW_BASE/VERSION" -o "$tmp/VERSION"
sh -n "$tmp/remote-gate-mapper-install.sh"
remote_version="$(sed -n '1p' "$tmp/VERSION" | tr -d '\r\n')"
local_version="$(sed -n '1p' "$LIB_DIR/VERSION" | tr -d '\r\n')"
[ "$remote_version" = "$local_version" ] || {
    echo "ERROR: Remote Gate version mismatch: installed=$local_version mapper-channel=$remote_version" >&2
    echo "Update Remote Gate first, then rerun this mapper command." >&2
    exit 1
}
cp "$tmp/remote-gate-mapper-install.sh" "$LIB_DIR/remote-gate-mapper-install.sh.new.$$"
chmod 0755 "$LIB_DIR/remote-gate-mapper-install.sh.new.$$"
mv -f "$LIB_DIR/remote-gate-mapper-install.sh.new.$$" "$LIB_DIR/remote-gate-mapper-install.sh"

sh "$LIB_DIR/remote-gate-mapper-install.sh" "$ACTION"
sh "$LIB_DIR/remote-gate-mapper-install.sh" status
