#!/bin/sh
set -u

AGENT="/usr/lib/remote-gate/remote-gate-agent.sh"
EGRESS_PROBE="/usr/lib/remote-gate/remote-gate-egress-probe.sh"
[ -x "$AGENT" ] || exit 1

# Private/CGNAT WANs get a best-effort per-device IPv4 egress observation.
# The helper is internally throttled and failures never block normal reporting.
[ -x "$EGRESS_PROBE" ] && "$EGRESS_PROBE" >/dev/null 2>&1 || true

# v0.3 consolidates transport/inventory logic in the agent so cron and hotplug
# never diverge from the service's dual-stack Multi-WAN behavior.
exec "$AGENT" report
