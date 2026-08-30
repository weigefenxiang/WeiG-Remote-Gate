# Security model

## Default state

WeiG-Remote-Gate does not create a home-WAN HTTP or HTTPS service.

The temporary access sets are empty by default. WAN behavior therefore falls through to the router's existing firewall policy.

## Gate activation

The browser submits:
- selected reported public WAN name
- selected agent-reported WireGuard interface
- one of the fixed TTL values

The browser does **not** submit the IP address to allow.

The server takes the source from the trusted Cloudflare header path and queues:
- source IPv4
- WAN logical name and last reported `l3_device`
- WireGuard interface and reported UDP listen port
- TTL
- command ID and expiry

The OpenWrt agent verifies basic input syntax, confirms the WAN device currently exists, then updates nftables timeout sets.

## Replay protection

Only one command is pending at a time.
Each command has:
- random ID
- creation time
- expiry time
- state

After acknowledgement it is moved out of the pending slot. Re-acknowledging the same ID returns a conflict.

## Remaining production checks

Before production use:
1. Confirm the target router uses firewall4, not firewall3.
2. Confirm firewall4 automatic includes are enabled.
3. Run `fw4 check`.
4. Confirm the installed rules appear in `fw4 print`.
5. Confirm the named sets exist after firewall reload.
6. Test from a non-authorized external IPv4 that ICMP and the WireGuard UDP port remain unreachable.
7. Test that expiry removes set membership.
8. Test behavior across a firewall reload while Gate is active.

The installer performs checks 2-5. External-path testing remains deployment-specific.
