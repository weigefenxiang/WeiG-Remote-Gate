# Firewall compatibility

WeiG-Remote-Gate supports two firewall generations through one Gate backend contract.

| Detected stack | Backend |
| --- | --- |
| `fw3` + `iptables` + `ipset` | `fw3-iptables` |
| `fw4` + `nft` | `fw4-nftables` |

The installer auto-detects the stack. It never asks the user to migrate firewall generations.

## Traffic boundary

### Access Gate

The Gate firewall abstraction filters only router-local INPUT traffic for:

- ICMP echo-request on protected WAN devices;
- UDP ports currently reported by local WireGuard interfaces.

It never installs generic filtering in FORWARD. qBittorrent/BT, UPnP, NAT-PMP, DNAT and ordinary port forwarding remain under the original firewall policy.

### Optional Internet Exit

`remote-gate-wireguard-egress.sh` is a separate runtime helper. When Internet Exit is explicitly selected, it may temporarily install only the FORWARD/NAT/PBR state needed to carry the selected WireGuard client subnet through the selected WAN.

The ownership is narrow:

- IPv4 mode: selected WG IPv4 subnet -> selected WAN, with runtime policy routing and NAT44;
- IPv6 mode: selected WG IPv6 ULA subnet -> selected WAN, with runtime policy routing and NAT66;
- Dual mode: both families are installed transactionally or rolled back together.

These rules are not persistent UCI egress policy. Disable, Close, TTL expiry, activation failure or reboot removes the runtime egress state. Existing qBittorrent/BT, UPnP, NAT-PMP, DNAT, LAN forwarding and unrelated traffic stay outside Remote Gate egress ownership.

On fw3/iptables systems, egress operations wait for the xtables lock instead of treating a short-lived concurrent firewall update as an immediate failure.

## Multi-source authorization

IPv4 and IPv6 use independent timeout sets. A family may contain multiple external source addresses at once, with a separate TTL for every source. Therefore multiple WireGuard peers can share one router-local listener such as `WG_HOME` on one UDP port without opening additional ports.

The family profile is deliberately constrained to one WAN device, one WireGuard listen port and one scope while any sources are active. This prevents the source set, interface set and port set from forming unintended cross-products on fw3 or fw4. To switch WAN, port or scope, close the existing temporary access first.

## Multi-WAN WireGuard return routing

Remote Gate keeps router-local replies to every authorized client on the WAN selected by the Gate command. This prevents a WireGuard handshake that arrived on WAN2/WAN3 from being answered through another default WAN.

The return path is fully data-driven:

- every authorized IPv4 source gets an exact `/32` destination when a policy route is needed;
- every authorized IPv6 source gets an exact `/128` destination;
- the WAN device comes from the validated endpoint;
- the UDP port is the discovered WireGuard listen port, not a hard-coded value;
- route state and expiry are tracked per source.

Remote Gate first reuses an existing per-WAN policy-routing table discovered from the router's own `ip rule` state. If no suitable table exists and the ordinary route points at a different WAN, it creates a temporary routing table containing only that authorized client's host route.

The additional Gate return rule matches `iif lo`, so it applies only to packets generated locally by the router. It does not change forwarded LAN/BT/DNAT traffic. Expiring one authorization removes only that source's rule; `Close access now` clears all temporary authorization and return-route state.

Internet Exit PBR is separate: it matches packets arriving from the selected WireGuard interface/subnet and sends them to the explicitly selected WAN egress table.

## Priority

The Gate guard must run before the normal established/related shortcut so an expired WireGuard authorization is blocked immediately.

- fw3 inserts `WEIG_REMOTE_GATE` at INPUT position 1.
- fw4 uses `/usr/share/nftables.d/chain-pre/input/`.

## Reload recovery

A firewall include calls `remote-gate-firewall.sh restore` after firewall rebuilds. Protected WAN/WireGuard Gate policy is restored from local state. Every active source is restored only for its remaining TTL. The return-route watcher independently reconciles all router-local same-WAN reply rules while those source authorizations remain valid.

Internet Exit remains runtime-only and is reconciled from temporary state rather than committed as persistent firewall/network UCI configuration.
