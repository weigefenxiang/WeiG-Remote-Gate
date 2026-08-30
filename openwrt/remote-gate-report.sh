#!/bin/sh
set -u

AGENT="/usr/lib/remote-gate/remote-gate-agent.sh"
[ -x "$AGENT" ] || exit 1

# v0.3 consolidates transport/inventory logic in the agent so cron and hotplug
# never diverge from the service's dual-stack Multi-WAN behavior.
exec "$AGENT" report
