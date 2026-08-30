#!/bin/sh
# Keep the protected public-WAN/WireGuard policy current on interface changes.
case "${ACTION:-}" in
    ifup|ifupdate|update)
        [ -x /usr/lib/remote-gate/remote-gate-agent.sh ] || exit 0
        (/usr/lib/remote-gate/remote-gate-agent.sh sync-firewall >/dev/null 2>&1) &
        ;;
esac
exit 0
