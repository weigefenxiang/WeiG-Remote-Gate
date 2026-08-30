#!/bin/sh
set -eu

LIB_DIR="/usr/lib/remote-gate"
CRON_LINE="*/5 * * * * /usr/lib/remote-gate/remote-gate-report.sh"

if [ -x /etc/init.d/remote-gate-agent ]; then
    /etc/init.d/remote-gate-agent disable || true
    /etc/init.d/remote-gate-agent stop || true
fi
if [ -x "$LIB_DIR/remote-gate-firewall.sh" ]; then
    "$LIB_DIR/remote-gate-firewall.sh" uninstall || true
fi
rm -f /etc/init.d/remote-gate-agent /etc/hotplug.d/iface/95-remote-gate
if [ -f /etc/crontabs/root ]; then
    grep -Fvx "$CRON_LINE" /etc/crontabs/root > /tmp/remote-gate-cron.$$ || true
    mv /tmp/remote-gate-cron.$$ /etc/crontabs/root
    /etc/init.d/cron restart 2>/dev/null || true
fi
rm -rf "$LIB_DIR"
printf 'Application files removed.\n'
printf 'Original firewall behavior (including existing Allow-Ping/UPnP/DNAT rules) is restored.\n'
printf 'Preserved configuration/state: /etc/remote-gate.conf /etc/remote-gate-state\n'
