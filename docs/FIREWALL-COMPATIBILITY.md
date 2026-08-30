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

## Priority

The guard must run before the normal established/related shortcut so an expired WireGuard authorization is blocked immediately.

- fw3 inserts `WEIG_REMOTE_GATE` at INPUT position 1.
- fw4 uses `/usr/share/nftables.d/chain-pre/input/`.

## Reload recovery

A firewall include calls `remote-gate-firewall.sh restore` after firewall rebuilds. Protected public-WAN/WireGuard policy is restored from local state. Active authorization is restored only for its remaining TTL.
