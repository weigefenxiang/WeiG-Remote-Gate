# Security policy

## Hard invariants

WeiG-Remote-Gate must preserve these invariants:

1. The VPS application binds only to loopback.
2. The project creates no HTTP/HTTPS listener on the home WAN.
3. The browser cannot choose the IPv4 address that is authorized.
4. Only active public WANs can be used for Gate activation.
5. Gate authorization is temporary and bounded to a selected WireGuard UDP port.
6. Remote Gate guards only ICMP echo and router-local WireGuard UDP traffic.
7. Remote Gate must not blanket-filter WAN traffic or add filtering to the `FORWARD` path.
8. DNAT, UPnP, NAT-PMP, port forwarding, qBittorrent/BT and unrelated services remain owned by the original firewall.
9. The Gate guard is evaluated before ordinary established/related acceptance.
10. Uninstall restores the user's original firewall behavior and does not delete unrelated UCI rules.

## Firewall backends

Supported backends are:

- firewall3: iptables + ipset with per-entry timeout;
- firewall4: nftables sets with timeout.

The installer auto-detects the backend and refuses unsupported combinations.

## Reporting issues

Do not include WRITE_TOKEN, passwords, session cookies, WireGuard private keys, real home public IPs or other secrets in public issues.
