# Current Device Validation

0.3.17 development is currently prioritized around one real router before wider OpenWrt-family compatibility is treated as a release blocker.

## Current hardware target

```text
Distribution: ImmortalWrt 21.02-SNAPSHOT
Target:       mediatek/mt7981
Package ABI:  aarch64_cortex-a53
Kernel:       Linux 5.4.x / aarch64
Firewall:     fw3 + iptables legacy + ipset
Service:      WG_HOME / UDP 51820
```

Current WAN roles observed on the device are dynamic and should not be identified by address or by the literal names `WAN` / `WAN2` in policy code:

```text
WAN   / pppoe-WAN   / private 172.20.x.x upstream -> Mapped candidate
WAN2  / pppoe-WAN2  / public IPv4                -> Direct candidate
MODEM / eth1        / private management network -> not a Mapped target
MODEM2/ eth1.2      / private management network -> not a Mapped target
LAN   / br-lan      / LAN                         -> never a Mapped target
WG_HOME              / WireGuard service network  -> never a Mapped target
```

Mapped auto-discovery remains restricted to an active IPv4 **default-route WAN** that has no public IPv4 address. Merely owning an RFC1918/CGNAT address (`10/8`, `172.16/12`, `192.168/16`, `100.64/10`) does not make an interface a mapping target. If future topology makes the private default-WAN identity ambiguous, mapping must fail closed rather than mapping every private interface.

## Current protocol scope

The current Gate implementation supports:

```text
IPv4 / UDP / WireGuard
IPv6 / UDP / WireGuard Direct
Dual-stack / UDP / WireGuard
```

IPv4 Mapped Access is supported when the Remote Gate mapper is available. IPv6 Mapped Access is not implemented; IPv6 uses Direct access only.

Dual-stack selection prefers a single WAN that has both a public IPv4 endpoint and a global IPv6 endpoint. If no such same-WAN pair exists, the UI may combine the best IPv4 and IPv6 endpoints from different WANs. Internet Exit follows the selected Access WAN by family, so split Dual may use one WAN for IPv4 egress and another WAN for IPv6 egress.

The current physical router still has `IPv6 Gate mode: disabled`, so IPv6 and split-Dual behavior is CI/browser/runtime-contract validated but is **not yet counted as real-device PASS**.

TCP, BitTorrent, qBittorrent, DHT, uTP-specific behavior, Shadowsocks, SSR, HTTP, SSH and generic port forwarding remain out of scope unless explicitly requested later.

## Automatic endpoint preference

When the browser has not made a manual selection, the UI derives the default from current endpoint capability rather than WAN names:

```text
IPv4: Public Direct -> Mapped -> observed NAT egress -> Private/CGNAT Try
IPv6: prefer the selected/best IPv4 WAN when it also has Global IPv6,
      otherwise use the best Global IPv6 Direct endpoint
Dual: same-WAN Public IPv4 + Global IPv6
      -> same-WAN Mapped IPv4 + Global IPv6
      -> best IPv4 + best IPv6 across different WANs
```

Internet Exit defaults to the Access WAN for each selected family. Automatic selections are recorded as `auto`; explicit browser changes are recorded as `manual` and are preserved while the selected intent remains available.

Automatic selection never means automatic authorization. A user still has to request `Activate` before a temporary Gate authorization is created.

## Mapper lifecycle

`remote-gate-mapper` is an optional Remote Gate-owned component with an independent lifecycle:

```text
remote-gate-mapper-install.sh install
remote-gate-mapper-install.sh update
remote-gate-mapper-install.sh repair
remote-gate-mapper-install.sh rollback
remote-gate-mapper-install.sh uninstall
remote-gate-mapper-install.sh status
remote-gate-mapper-install.sh status-json
```

Rules:

- install/update must validate exact Package ABI, SHA-256 and `remote-gate-mapper <VERSION> api=1` before activation;
- replacing a current mapper creates one validated rollback copy;
- rollback is accepted only when the backup still matches current VERSION/API/Package ABI/hash;
- uninstall stops Remote Gate mapper runtime, removes only mapper binary/metadata/rollback state and re-syncs the Gate; it does not remove WireGuard or the rest of Remote Gate;
- repair is fail-closed and never treats a mismatched binary as usable;
- missing/uninstalled mapper means only `Mapped Access = unavailable`; Direct/Gate/Internet Exit remain independent.

## Development AArch64 candidate

For the current `aarch64_cortex-a53` device, `dev` may carry a verified AArch64 static candidate so the router can install it with one command during hardware validation. It is development-only and is not equivalent to a stable Release asset.

## Real-device results

The following IPv4 Mapped path has been demonstrated on the current MT7981 router:

```text
CLOSED
-> mapper remains active while mapped ingress is DROP
-> browser Activate authorizes the real cellular IPv4 source only
-> external WireGuard handshake succeeds through the mapped public endpoint
-> Internet Exit through the selected WAN works
-> browser traffic returning through WireGuard does not replace the pinned cellular source
-> Close queues and ACKs a real close command
-> authorization ACCEPT disappears while mapper/STUN control remain
-> a fresh WireGuard attempt reaches mapped ingress and is dropped
-> latest WireGuard handshake timestamp does not advance while CLOSED
```

The CLOSED re-handshake test also produced a packet on the mapped-ingress DROP rule, proving the failure was caused by Gate enforcement rather than by a client that never transmitted.

## PPPoE / mapping-change status

A real `WAN` PPPoE reconnect has already shown the expected fail-closed first half:

```text
old PPPoE session disappears
-> old Mapping disappears
-> active_mappings becomes 0
-> Gate remains CLOSED
-> no old authorization is restored
```

The initial hardware run also exposed a settle race where the new `pppoe-WAN` address was already present before the WAN/default-route inventory was ready. The current `dev` hotplug path therefore performs bounded re-sync after interface-up (`0s -> 2s -> 5s -> 10s`). Internet Exit runtime also validates that its selected WAN, L3 device, main default route and Remote Gate policy-table default route are still current; a changed/missing route clears egress instead of falling back to another main-table WAN.

The **second half still requires post-update hardware confirmation**:

```text
PPPoE reconnect
-> new WAN/default-route inventory settles
-> new Mapping is created automatically
-> Gate is still CLOSED
-> UI shows the current preferred endpoint
-> user explicitly Activates
-> a fresh WireGuard handshake succeeds through the new Mapping
```

A STUN response alone is not proof of inbound reachability. A fresh externally initiated WireGuard handshake is required.
