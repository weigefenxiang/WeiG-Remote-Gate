# Firewall compatibility

WeiG-Remote-Gate supports OpenWrt-family firmware through capability detection rather than release-number or branding allowlists. OpenWrt, LEDE, ImmortalWrt and compatible derivatives use the same backend contract when the required runtime stack is present.

| Detected stack | Backend |
| --- | --- |
| `fw3` + `iptables` + `ipset` + xt_set | `fw3-iptables` |
| `fw4` + `nft` + automatic nft includes | `fw4-nftables` |

The installer auto-detects the stack. It never asks the user to migrate firewall generations and does not reject a router merely because its release name is old or unfamiliar.

Package management is independent from the firewall generation. OpenWrt 25.12+ may use `apk`; older OpenWrt/LEDE/ImmortalWrt commonly uses `opkg`. Remote Gate runtime firewall behavior does not depend on which package manager is installed.

## Capability layers

Remote Gate separates required and optional capabilities:

```text
Core runtime
  /bin/sh + procd/rc.common + curl + ubus + jsonfilter + uci + ip

Access Gate
  fw3 + iptables + ipset
  or
  fw4 + nft

Optional IPv6 Gate
  IPv6 firewall support for the detected backend

Optional Mapped Access
  exact package ABI + compatible remote-gate-mapper binary

Optional Internet Exit
  required policy-routing/NAT capabilities for the selected family
```

Missing an optional capability disables only that feature. A router with no compatible mapper binary can still use Direct Access, IPv6 Gate when available, the control plane and existing WireGuard Gate behavior.

## Traffic boundary

### Access Gate

The Gate firewall abstraction filters only router-local INPUT traffic owned by Remote Gate:

- ICMP/ICMPv6 Echo Request on protected WAN devices when Ping scope applies;
- Direct registered UDP service ports, currently WireGuard listeners;
- exact Mapped Access `WAN device + ingress_port` pairs;
- exact STUN control tuples required by a prepared mapper;
- optional short diagnostic verification windows.

It never installs generic filtering in FORWARD. qBittorrent/BT, UPnP, NAT-PMP, DNAT and ordinary port forwarding remain under the original firewall policy.

### Exact Mapped STUN control exception

A prepared mapper must receive STUN replies on the same UDP socket that is otherwise protected by the Mapped ingress DROP rule. Remote Gate therefore installs only the exact control tuple before the Mapped DROP:

```text
WAN device
+ mapper ingress_port
+ resolved STUN IPv4
+ STUN source port
```

fw3 implements this as an exact INPUT ACCEPT before the exact `device + ingress_port` DROP. fw4 uses an `ifname . inet_service . ipv4_addr . inet_service` concatenated set before the mapped-ingress tuple set.

The native mapper independently treats the resolved STUN socket as control traffic only. Packets from that STUN peer are not relayed into the registered WireGuard service.

### Optional Internet Exit

`remote-gate-wireguard-egress.sh` is a separate runtime helper. When Internet Exit is explicitly selected, it may temporarily install only the FORWARD/NAT/PBR state needed to carry the selected WireGuard client subnet through the selected WAN.

The ownership is narrow:

- IPv4 mode: selected WG IPv4 subnet -> selected WAN, with runtime policy routing and NAT44;
- IPv6 mode: selected WG IPv6 ULA subnet -> selected WAN, with runtime policy routing and NAT66;
- Dual mode: both families are installed transactionally or rolled back together.

These rules are not persistent UCI egress policy. Disable, Close, TTL expiry, activation failure or reboot removes the runtime egress state. Existing qBittorrent/BT, UPnP, NAT-PMP, DNAT, LAN forwarding and unrelated traffic stay outside Remote Gate egress ownership.

On fw3/iptables systems, egress operations wait for the xtables lock instead of treating a short-lived concurrent firewall update as an immediate failure.

## Multi-source authorization

IPv4 and IPv6 use independent timeout sets. A family may contain multiple external source addresses at once, with a separate TTL for every source. Therefore multiple WireGuard peers can share one registered ingress without opening additional WAN service ports.

The family profile is deliberately constrained to one WAN device, one registered ingress port and one scope while any sources are active. This prevents source/interface/port sets from forming unintended cross-products on fw3 or fw4. To switch WAN, ingress or scope, close the existing temporary access first.

## Multi-WAN router-local return routing

Remote Gate keeps router-local replies to every authorized client on the WAN selected by the Gate command. This applies to both Direct WireGuard and Mapped Access: mapper replies are also locally generated router traffic destined for the authorized external source.

The return path is fully data-driven:

- every authorized IPv4 source gets an exact `/32` destination when a policy route is needed;
- every authorized IPv6 source gets an exact `/128` destination;
- the WAN device comes from the validated endpoint;
- the registered ingress port is dynamic and is not a hard-coded WireGuard port;
- route state and expiry are tracked per source.

Remote Gate first reuses an existing per-WAN policy-routing table discovered from the router's own `ip rule` state. If no suitable table exists and the ordinary route points at a different WAN, it creates a temporary routing table containing only that authorized client's host route.

The additional Gate return rule matches `iif lo`, so it applies only to packets generated locally by the router. It does not change forwarded LAN/BT/DNAT traffic. Expiring one authorization removes only that source's rule; `Close access now` clears all temporary authorization and return-route state.

Internet Exit PBR is separate: it matches packets arriving from the selected WireGuard interface/subnet and sends them to the explicitly selected WAN egress table.

## Priority

The Gate guard must run before the normal established/related shortcut so an expired authorization is blocked immediately.

- fw3 inserts `WEIG_REMOTE_GATE` at INPUT position 1.
- fw4 uses `/usr/share/nftables.d/chain-pre/input/`.

## Reload recovery

A firewall include calls `remote-gate-firewall.sh restore` after firewall rebuilds. Protected WAN, Direct ingress, Mapped ingress and exact STUN control state are restored from local state. Every active source is restored only for its remaining TTL. The return-route watcher independently reconciles router-local same-WAN reply rules while those source authorizations remain valid.

Internet Exit remains runtime-only and is reconciled from temporary state rather than committed as persistent firewall/network UCI configuration.

## Historical-version policy

Remote Gate does not maintain a list that says “17.01 works, 18.06 works, 19.07 works...” because derivatives routinely backport components. Instead:

- old LEDE/OpenWrt with the required capabilities may run;
- fw3 remains a first-class backend;
- new OpenWrt with `apk` remains supported;
- unsupported/missing optional capabilities degrade individually;
- native mapper delivery is selected by exact package ABI, never by a broad MIPS/ARM guess.
