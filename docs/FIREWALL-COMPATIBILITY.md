# Firewall compatibility

WeiG-Remote-Gate supports two firewall generations through one backend contract.

| Detected stack | Backend |
| --- | --- |
| `fw3` + `iptables` + `ipset` | `fw3-iptables` |
| `fw4` + `nft` | `fw4-nftables` |

The installer auto-detects the stack. It never asks the user to migrate firewall generations.

## Traffic boundary

Remote Gate filters only router-local INPUT traffic for:

- ICMP echo-request on active public WAN devices;
- UDP ports currently reported by local WireGuard interfaces.

It never installs filtering in FORWARD. qBittorrent/BT, UPnP, NAT-PMP, DNAT and ordinary port forwarding remain under the original firewall policy.

## Multi-WAN WireGuard return routing

When a temporary authorization is active, Remote Gate also keeps router-local replies to that authorized client on the same WAN selected by the Gate command. This prevents a WireGuard handshake that arrived on WAN2/WAN3 from being answered through another default WAN.

The return path is fully data-driven:

- the authorized source address comes from the active Gate authorization;
- the WAN device is the selected endpoint device, with no WAN1/WAN2/WAN3 name hard-coding;
- the WireGuard UDP port is the discovered listen port carried by the authorization, not a fixed `51820` value;
- IPv4 uses an exact `/32` destination and IPv6 uses an exact `/128` destination.

Remote Gate first reuses an existing per-WAN policy-routing table discovered from the router's own `ip rule` state. If no suitable table exists and the ordinary route points at a different WAN, it creates a temporary empty routing table containing only the authorized client's host route.

The additional rule matches `iif lo`, so it applies only to packets generated locally by the router. It does not change forwarded LAN/BT/DNAT traffic. The rule is removed when the authorization closes, expires, is replaced, the service stops, or the WAN topology is reconciled after an interface update.

## Priority

The guard must run before the normal established/related shortcut so an expired WireGuard authorization is blocked immediately.

- fw3 inserts `WEIG_REMOTE_GATE` at INPUT position 1.
- fw4 uses `/usr/share/nftables.d/chain-pre/input/`.

## Reload recovery

A firewall include calls `remote-gate-firewall.sh restore` after firewall rebuilds. Protected public-WAN/WireGuard policy is restored from local state. Active authorization is restored only for its remaining TTL. The return-route watcher independently reconciles the router-local same-WAN reply rule while that authorization remains valid.
