#!/bin/sh
# Called by firewall3/firewall4 after rules are rebuilt. Keep this file tiny:
# firewall4 sources script includes and deliberately disables shell UCI helpers.
/usr/lib/remote-gate/remote-gate-firewall.sh restore >/dev/null 2>&1 || \
    logger -t remote-gate "failed to restore Remote Gate firewall guard"
