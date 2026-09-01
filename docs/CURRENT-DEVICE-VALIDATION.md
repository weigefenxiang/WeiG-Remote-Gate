# Current Device Validation

0.3.17 development is currently prioritized around one real router before wider OpenWrt-family compatibility is treated as a release blocker.

## Current hardware target

```text
Distribution: ImmortalWrt 21.02-SNAPSHOT
Target:       mediatek/mt7981
Package ABI:  aarch64_cortex-a53
Kernel:       Linux 5.4.255 / aarch64
Firewall:     fw3 + iptables legacy + ipset
Service:      WG_HOME / UDP 51820
```

Current WAN roles observed on the device:

```text
WAN   / pppoe-WAN   / 172.20.182.224  -> private upstream; Mapped candidate
WAN2  / pppoe-WAN2  / 163.204.223.16  -> public IPv4; Direct
MODEM / eth1        / 192.168.8.12     -> local/upstream-management network; not a Mapped target
MODEM2/ eth1.2      / 192.168.2.22     -> local/upstream-management network; not a Mapped target
LAN   / br-lan      / 192.168.1.1      -> LAN; never a Mapped target
WG_HOME              / 10.77.0.1        -> WireGuard service network; never a Mapped target
```

Mapped auto-discovery remains restricted to an active IPv4 **default-route WAN** that has no public IPv4 address. Merely owning an RFC1918/CGNAT address (`10/8`, `172.16/12`, `192.168/16`, `100.64/10`) does not make an interface a mapping target. If future topology makes the private default-WAN identity ambiguous, mapping must fail closed rather than mapping every private interface.

## Current protocol scope

0.3.17 remains:

```text
IPv4
UDP
WireGuard Service Adapter
```

TCP, BitTorrent, qBittorrent, DHT, uTP-specific behavior, Shadowsocks, SSR, HTTP, SSH and generic port forwarding are out of scope unless explicitly requested later.

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

## Hardware success criteria

The current device is considered Mapped-validated only after this real path succeeds:

```text
WAN / pppoe-WAN / 172.20.182.224
-> mapper binds dedicated UDP ingress
-> STUN returns a public external_address:external_port
-> CLOSED blocks new external WireGuard handshake
-> Activate authorizes the selected external source
-> a new external WireGuard handshake succeeds through the mapped endpoint
-> LAN access succeeds
-> TTL / Close blocks a fresh handshake again
-> PPPoE reconnect or mapping change is reconciled safely
```

A STUN response alone is not proof of inbound reachability. A fresh externally initiated WireGuard handshake is required.
