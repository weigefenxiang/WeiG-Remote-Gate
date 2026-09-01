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

## PPPoE / mapping-change hardware PASS

The current `dev` settle/reconciliation path has now passed the complete real-router PPPoE reconnect lifecycle.

A representative run changed all three relevant identities:

```text
Before reconnect:
pppoe-WAN IPv4      172.20.53.132
Mapped public       223.73.44.162:24948
Mapper ingress      53835

After reconnect:
pppoe-WAN IPv4      172.20.11.27
Mapped public       223.73.44.74:1625
Mapper ingress      54342
```

After the reconnect and bounded settle window:

```text
pppoe-WAN is UP
-> active_mappings = 1
-> inventory contains the new current Mapping
-> protected_mapped_ingress_v4 = 1
-> exact STUN control ACCEPT targets the new ingress
-> generic mapped ingress remains DROP
-> Gate remains active=false
-> source_count=0 / authorized_sources=[]
-> Internet Exit remains inactive
```

The user then explicitly selected the new Mapped endpoint and activated access. A fresh external WireGuard handshake advanced from `1788280607` to `1788287352`, and the new mapped ingress rule recorded authorized packets (`match-set weig_remote_gate_auth_v4 src`) before the fallback DROP. This proves the path was the new Mapping rather than the Direct WireGuard port.

The complete hardware result is therefore:

```text
PPPoE down/up
-> old PPPoE session and Mapping disappear
-> no old Gate authorization migrates
-> WAN/default-route inventory settles
-> new Mapping is created automatically
-> Gate remains CLOSED
-> user explicitly Activates the new Mapping
-> temporary source authorization is installed on the new ingress
-> fresh WireGuard handshake succeeds through the new public Mapping
```

The hotplug path performs bounded re-sync after interface-up (`0s -> 2s -> 5s -> 10s`). Internet Exit runtime independently validates that its selected WAN, L3 device, main default route and Remote Gate policy-table default route remain current; a changed/missing route clears egress instead of silently falling back to another main-table WAN.

A STUN response alone is never proof of inbound reachability. A fresh externally initiated WireGuard handshake is required.

## Investigation pitfalls and recurring mistakes

The following mistakes occurred during 0.3.17 development and should not be repeated:

1. **Do not treat a changed PPPoE address or changed mapped endpoint as a failure.** Reconnect is expected to invalidate the old session. The test is whether a new Mapping is rebuilt safely.
2. **Do not inspect immediately after `ifup` and declare recovery broken.** PPPoE address, ubus inventory, default routes, mapper state and firewall state can settle at different times. Use the bounded settle path and inspect after it completes.
3. **Do not equate `mapper active` with `Gate open`.** A Mapping may stay active continuously while mapped ingress remains DROP. Authorization is a separate state.
4. **Do not equate the first post-click `active=false` sample with Activate failure.** The router agent polls commands asynchronously. Confirm the command/ACK or wait for the firewall authorization before judging the result.
5. **Do not use the dashboard request source blindly as client authorization evidence after WireGuard Internet Exit is enabled.** The HTTP request can return through the home router and appear to come from the router's own external address. Router egress/mapped addresses must be suppressed and the currently authorized real client source pinned.
6. **Do not interpret `source_ip` attached to a Close request as an authorization source.** For Close it can simply be the HTTP request source; Close clears authorization rather than creating it.
7. **Do not confuse Access Endpoint with Internet Exit.** Access Endpoint selects where WireGuard enters; Internet Exit selects where authenticated WireGuard traffic leaves. They default to the same WAN per family but are separate controls.
8. **Do not hardcode `WAN`, `WAN2`, interface numbering or a particular public IP.** Default selection is capability-based. Another router may expose the public Direct path on a different logical WAN.
9. **Do not require Dual to use one WAN.** Same-WAN public IPv4 + global IPv6 is preferred, but split Dual is valid when the best IPv4 and IPv6 endpoints belong to different WANs. Egress must then be tracked per family.
10. **Do not allow split Dual egress to degrade to an unspecified main-table route.** If the selected WAN/L3/policy-table route is no longer current, clear runtime egress fail-closed.
11. **Do not migrate authorization across Mapping changes.** A new mapped ingress requires a fresh explicit Activate even when the logical WAN name is unchanged.
12. **Do not assume the external address or port must change on every reconnect.** A reconnect may receive the same tuple again; freshness must be based on current runtime ownership/status rather than inequality alone.
13. **Do not inspect only `server/app/main.py` and conclude an API route is missing.** The formal server entry is `server/remote-gate.py`, which extends the handler and owns some routes such as the client-source candidate endpoint.
14. **Do not use stale mapper status as authority.** Mapper status is valid only while the corresponding managed process is alive and owned; orphan/stale runtime state must be rejected or cleaned.
15. **Do not preserve duplicate endpoint-ranking implementations.** `endpointScore()` remains because it is the shared primitive for IPv4/IPv6/Dual ordering; avoid creating a second competing preference engine.
16. **Do not use `npx playwright install --with-deps chromium` in the main CI.** It caused slow Ubuntu APT downloads through Azure mirrors. The browser job installs the pinned Playwright package and Chromium without OS-package installation.

## Remaining real-device work

IPv4 Mapped Access, CLOSED/OPEN lifecycle, Close, source pinning and PPPoE remap recovery are real-device PASS on the current fw3 MT7981 sample.

Still pending as separate hardware validation:

```text
Automatic default Public Direct endpoint + matching Internet Exit on the real dashboard
IPv6 Gate after explicitly enabling it on the router
Same-WAN Dual data plane
Split-WAN Dual data plane and per-family Internet Exit
Mapped Access on a real fw4/nftables device
```

Do not report those items as hardware PASS until they have been exercised on the relevant real device.
