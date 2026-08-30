#!/bin/bash
set -euo pipefail

[ "${EUID:-$(id -u)}" -eq 0 ] || { echo "Run as root." >&2; exit 1; }

systemctl disable --now remote-gate.service 2>/dev/null || true
rm -f /etc/systemd/system/remote-gate.service
systemctl daemon-reload
rm -rf /usr/local/lib/remote-gate

printf 'Application files removed.\n'
printf 'Preserved secrets/state:\n'
printf '  /etc/remote-gate\n'
printf '  /var/lib/remote-gate\n'
printf 'Remove those manually only if you no longer need them.\n'
