# WeiG-Remote-Gate

**Language:** [English](README.md) · [简体中文](translations/README.zh-CN.md)

**Secure Remote Access Gateway for OpenWrt / LEDE / ImmortalWrt.**

WeiG-Remote-Gate is a Cloudflare-fronted control plane for Multi-WAN status and temporary private remote access. The home WAN does **not** host an HTTP/HTTPS management service. OpenWrt-family routers report inventory/status and pull short-lived commands over outbound HTTPS.

## 0.3.17 direction: Direct / Mapped / Relay

0.3.17 introduces Remote Gate-owned **Mapped Access** for homes that do not have a directly reachable public IPv4 endpoint.

NATMap is **not** a dependency, package requirement, provider name or product concept. Remote Gate owns its own mapping interface and implementation.

User-facing Access Methods are:

```text
Direct
Mapped
Relay   (future)
```

- **Direct** — public IPv4 or global IPv6 reaches the router directly.
- **Mapped** — Remote Gate establishes and maintains a NAT mapping, protects the router ingress with the Access Gate, and relays authorized traffic to a locally registered service.
- **Relay** — reserved for a future relay path when Direct and Mapped are unavailable.

0.3.17 Mapped Access intentionally starts with **IPv4 + UDP + WireGuard**. Direct IPv6 and Dual-stack Gate operation remain supported independently. The architecture leaves Service Adapter interfaces for future protocols such as Shadowsocks and ShadowsocksR without turning Remote Gate into an arbitrary port-forwarding platform.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/SECURITY-MODEL.md`](docs/SECURITY-MODEL.md), [`docs/PROJECT-RULES.md`](docs/PROJECT-RULES.md) and [`docs/CURRENT-DEVICE-VALIDATION.md`](docs/CURRENT-DEVICE-VALIDATION.md).

## Security and traffic ownership

The **Access Gate** owns only Remote Gate-registered router-local ingress on protected WAN endpoints plus optional Ping scope.

For Direct WireGuard today that means:

```text
ICMP / ICMPv6 Echo Request   -> closed by default
WireGuard UDP listen ports   -> closed by default
```

For Mapped Access it also means a locally registered mapper `ingress_port`:

```text
CLOSED
Internet -> mapped public endpoint -> router ingress -> DROP

ACTIVE
approved source -> mapped public endpoint -> router ingress -> mapper -> registered service

TTL / Close
mapping may remain -> router ingress -> DROP
```

A NAT mapping is therefore **not** equivalent to permanently open access.

The Access Gate does not become a generic firewall manager. qBittorrent, DHT/PeX, UPnP/NAT-PMP, user DNAT/manual forwards and unrelated NAS/PC services remain under the original firewall policy.

Two access scopes are available:

- **WireGuard only** — recommended; Ping remains closed.
- **WireGuard + Ping** — also permits Echo Request from the selected source.

For IPv6, the Access Gate controls only Echo Request and registered router-local service ingress. NDP, Router Advertisement, Packet Too Big and other ICMPv6 control traffic fall through to the original firewall policy.

The optional **Internet Exit** is separate from the Access Gate. When explicitly selected, it may temporarily install only the PBR, FORWARD and NAT44/NAT66 state required to send the selected WireGuard client subnet through the selected WAN **per IP family**. A split Dual plan may use one WAN for IPv4 and another for IPv6. Internet Exit does not take ownership of unrelated forwarded traffic and does not persist egress policy in UCI.

## Architecture

```text
Browser
   |
   | HTTPS
   v
Cloudflare
   |
   v
VPS / WeiG-Remote-Gate
127.0.0.1:29444 only
   ^
   |
   | outbound HTTPS inventory / status / pull / ack
   |
OpenWrt-family router
   |
   +-- Multi-WAN discovery
   +-- Access Endpoint discovery
   |     +-- Direct
   |     +-- Mapped
   |     `-- Relay (future)
   +-- local Service Registry
   |     +-- WireGuard
   |     +-- Shadowsocks (future)
   |     +-- ShadowsocksR (future)
   |     `-- other adapters (future)
   +-- Access Gate firewall abstraction
   +-- Mapping Engine
   `-- optional runtime WireGuard Internet Exit
```

The Cloudflare hostname is the **control plane**. Direct/Mapped/Relay endpoints are the **data plane**. Never use the Cloudflare Tunnel hostname as a WireGuard UDP endpoint.

## Access Endpoint and Service Registry model

Remote Gate separates **how traffic reaches home** from **what service receives it**.

```text
Access Endpoint
      |
      +-- Direct
      +-- Mapped
      `-- Relay (future)
             |
             v
        Access Gate
             |
             v
      Service Adapter
             |
             +-- WireGuard       (0.3.17)
             +-- Shadowsocks     (future)
             +-- ShadowsocksR    (future)
             `-- others          (future)
```

The browser cannot create arbitrary `192.168.x.x:port` forwards. A service must be discovered or registered locally on the router and independently validated before it can become an endpoint target.

0.3.17 initially registers validated WireGuard listeners only.

## Mapped Access port model

Mapped endpoints distinguish three ports:

```text
external_port  public NAT-mapped port seen by the Internet
ingress_port   router-local Mapping Engine port protected by Access Gate
service_port   locally validated service listen port
```

For Direct WireGuard these may be identical. For Mapped Access they may differ.

This distinction is required for old OpenWrt-family compatibility because the mapper does not need to share the WireGuard socket.

## 0.3.17 Mapping Engine scope

The first Remote Gate mapping implementation is intentionally small:

- IPv4 only;
- UDP only;
- one validated WAN/l3 device per mapping;
- STUN-style public endpoint discovery;
- keepalive and mapping refresh;
- mapping-change detection;
- dedicated local ingress socket;
- bounded per-client UDP relay sessions;
- idle timeout;
- sanitized status output;
- WAN reconnect recovery;
- WireGuard Service Adapter.

It does **not** provide generic TCP proxying, arbitrary port forwarding, HTTP/SSH/qBittorrent mapping, TURN, NATMap package/UCI management or user callback scripts.

Future transport engines may add TCP or other mechanisms behind the same Direct / Mapped / Relay and Service Adapter contracts.

## NAT / CGNAT capability boundary

Mapped Access cannot guarantee that every carrier or ISP CGNAT is traversable. Success depends on upstream NAT mapping/filtering behavior and UDP policy.

Remote Gate must therefore describe a successfully observed mapping as **Mapped**, not as a guaranteed public IP service. If traversal is unavailable, Direct/IPv6 and existing Remote Gate capabilities continue normally.

## Firewall compatibility

| Detected stack | Remote Gate backend |
| --- | --- |
| firewall3 / `fw3` + `iptables` + `ipset` | `fw3-iptables` |
| firewall4 / `fw4` + `nft` | `fw4-nftables` |

The Gate guard is evaluated before the normal `ESTABLISHED,RELATED` shortcut. Existing UCI rules such as `Allow-Ping` are not deleted; the earlier Remote Gate guard wins only for traffic owned by the Gate, and uninstall restores the original firewall behavior.

Compatibility is capability-based, not release-number based. An older LEDE/OpenWrt/ImmortalWrt derivative with the required fw3/runtime capabilities is not rejected merely because of age; modern fw4 systems use the nftables backend. Unsupported firewall capabilities fail closed during installation.

On fw3/iptables systems, runtime Internet Exit operations wait for the xtables lock instead of treating a short-lived concurrent firewall update as an immediate failure.

## OpenWrt / LEDE / ImmortalWrt compatibility

Remote Gate uses one OpenWrt-family capability contract instead of maintaining a hardcoded version allowlist.

Core rules:

- BusyBox/POSIX `/bin/sh` remains the script baseline;
- `rc.common` is the service framework baseline;
- procd is preferred when available, with a PID-owned `rc.common` fallback for older compatible systems;
- package management is detected independently: older systems commonly use `opkg`, while newer OpenWrt may use `apk`;
- firewall generation is detected from actual `fw3/iptables/ipset` or `fw4/nft` capabilities;
- optional IPv6, Mapped Access and Internet Exit capabilities degrade independently;
- no compiler is required on the router;
- no NATMap or other third-party traversal package is required.

Native mapper delivery uses the exact OpenWrt **Package ABI**, not `uname -m` or a broad MIPS/ARM guess. The read-only audit reports package manager, Package ABI, kernel machine and libc separately. Unknown ABI values fail safe. Legacy CPU families that cannot safely share a portable static binary are assigned to an exact OpenWrt SDK build tier instead of receiving a newer-ISA executable.

**OpenWrt/ImmortalWrt 21.02-class fw3 is a hardware-validated sample, not the minimum supported release.** Older LEDE/OpenWrt derivatives may be compatible when the required runtime/firewall capabilities exist; newer releases do not gain support merely from their version number if required capabilities were removed.

## Multi-WAN endpoint model

The server does not assume one public IPv4 WAN. An endpoint may be:

- public IPv4 `Direct`;
- global IPv6 `Direct` when IPv6 Gate capability is enabled;
- Remote Gate IPv4 UDP `Mapped`;
- per-WAN observed IPv4 `NAT egress · Try`;
- private/CGNAT IPv4 `Try` for manual experiments.

When the user has not made a manual choice, endpoint preference is capability-based rather than tied to WAN names:

```text
IPv4: Public Direct -> Mapped -> observed NAT egress -> Private/CGNAT Try
IPv6: prefer the best IPv4 WAN when it also has Global IPv6,
      otherwise use the best Global IPv6 Direct endpoint
Dual: same-WAN Public IPv4 + Global IPv6
      -> same-WAN Mapped IPv4 + Global IPv6
      -> best IPv4 + best IPv6 across different WANs
```

Internet Exit defaults to the Access WAN for each family. A split Dual Access plan therefore defaults to split per-family Internet Exit as well. Explicit manual selections remain user-controlled while still valid.

The OpenWrt-family agent continuously derives protected WAN devices, eligible IPv6 devices and registered local service ingress. A temporary authorization is revoked immediately if its WAN device or registered ingress leaves the current protected policy, even before its TTL expires.

## Dual-stack client sources

IPv4 and IPv6 are independent records for the authenticated browser session. Learning one family never deletes the other.

Source records may come from the authenticated Cloudflare request path or a short-lived family-specific browser candidate probe. The normal Activate body does not carry an arbitrary authorization address as authority; the VPS resolves the selected family from the session source store.

A router-owned external or Mapped address is never accepted as new client evidence. This matters after WireGuard Internet Exit is enabled: the dashboard HTTP request may return through the home router and appear to originate from the router itself. While Gate access is active, the actual authorized client source is pinned against that feedback loop.

When both families are usable, the UI may prefer IPv4 initially, but this is not a lock. Manual family/endpoint choices are preserved while the selected intent remains available.

## Dashboard interaction system

The dashboard follows the design-system discipline documented in [`DESIGN.md`](DESIGN.md), with visual changes reviewed against hierarchy, spacing, elevation, motion and accessibility rather than isolated ad-hoc CSS.

### EndpointPicker

The browser-native endpoint `<select>` remains an internal state bridge. `EndpointPicker` provides structured WAN/method/address information, selected feedback, desktop popover/mobile sheet behavior, focus containment, ARIA selected state and reduced-motion support.

The UI presents user-facing methods as `Direct`, `Mapped` and eventually `Relay`; internal mapper implementation names are not exposed as the primary concept.

### DurationControl

Quick presets remain:

```text
1m | 5m | 15m | 30m | Custom
```

`Custom` supports half-hour steps from 0.5h through 12h. The browser is not duration authority; both VPS and OpenWrt independently validate the allowed TTL values.

## Remote Gate flow

1. Sign in to the Cloudflare-fronted dashboard.
2. VPS records the current authenticated request source; the browser may best-effort complete a missing IPv4/IPv6 family.
3. The dashboard automatically proposes the best current Access Endpoint and matching Internet Exit; the user may override either selection.
4. VPS resolves the selected session source and endpoint server-side and queues the short-lived command transaction only after explicit `Activate`.
5. The router pulls the command over outbound HTTPS.
6. The router validates the WAN/device, registered ingress/service and TTL again.
7. Access Gate authorizes only the selected source on the selected registered ingress.
8. If the endpoint is Mapped, the Mapping Engine relays only through its locally registered mapping/service relationship.
9. If Internet Exit is selected, the independent egress helper validates and installs its temporary scoped per-family path.
10. TTL expiry or **Close access now** clears the applicable temporary authorization/runtime state.

## Optional IPv6 Gate

IPv6 is an optional data-plane capability. Fresh installs default to `GATE_IPV6=auto`; legacy upgrades preserve conservative behavior until enabled/tested. IPv4 operation does not depend on IPv6 support.

The outbound control transport is separate from IPv6 Gate. The agent can use healthy IPv4/IPv6 Multi-WAN paths for report/pull/ack even when IPv6 data-plane Gate is disabled.

## Optional WireGuard Internet Exit

Internet Exit is runtime-only and independent from the Access Endpoint. The initial Internet Exit choice follows the selected Access Endpoint WAN **per family**, while a user can manually select another eligible WAN and that manual choice is preserved for that family.

Supported modes are IPv4, IPv6 and Dual. Same-WAN Dual may use one logical WAN for both families; split Dual may use different IPv4 and IPv6 WANs. Dual installation is transactional: both requested families must validate and install successfully or the helper rolls back the partial runtime state. If a selected WAN/L3/default route or Remote Gate policy-table default route is no longer current, runtime egress is cleared fail-closed rather than silently falling back to another main-table WAN.

No persistent Internet Exit UCI policy is created. Disable, Close, TTL expiry, failure rollback or reboot leaves Internet Exit off.

## Safe update

### VPS

From v0.3 onward the local updater is preserved at:

```bash
/usr/local/lib/remote-gate/update.sh
```

The updater preserves hostname, login credentials, `WRITE_TOKEN`, sessions/state, creates a rollback backup under `/var/backups/weig-remote-gate/`, restarts the localhost-only service, checks health plus the Agent API and restores the old application on failure.

### OpenWrt family

v0.3+ installs/preserves its own updater, uninstaller, platform helper and read-only audit utility. Update creates application/config/state plus firewall/network backups, preserves WireGuard configuration, validates shell syntax, rebuilds Remote Gate-owned state and fails back to the previous installation if validation fails.

Mapper availability is optional. An unsupported/missing mapper binary must not turn an otherwise valid update into a broken Remote Gate installation.

## Safe uninstall

Both VPS and router-side installations have one-command uninstallers with dry-run support. They create local backups first, remove only resources owned by Remote Gate and perform residual checks. The router uninstaller does **not** blindly restore an old whole-firewall snapshot and does not remove WireGuard by default. Cloudflare Tunnel resources are not automatically deleted.

Mapped Access cleanup removes only Remote Gate-owned mapper binaries/runtime state. It never removes unrelated user NAT/firewall/service configuration.

## Current version and branch workflow

See [`VERSION`](VERSION) for the software version. Repository branch names do not contain the version number.

The repository workflow is:

```text
dev  -> development, fixes and CI
main -> validated stable state
```

All routine work is committed to the single fixed `dev` branch. Core + Native cross-build + Chromium regression CI must pass before the validated `dev` state is promoted to `main`.

Do not create `dev/*`, `feature/*`, version branches or temporary development branches. The complete hard contract is in [`docs/PROJECT-RULES.md`](docs/PROJECT-RULES.md).

## Validation status

### Hardware validated fw3 baseline

The fw3 IPv4 Access Gate and IPv4 UDP Mapped path have been validated end-to-end on a real ImmortalWrt 21.02-class MT7981 router using iptables legacy + ipset, PPPoE/CGNAT upstream, Cloudflare control plane and a router-local WireGuard listener.

Real-device validation now includes:

```text
CLOSED mapped ingress blocks a fresh external WireGuard handshake
Activate authorizes the actual cellular source and a fresh mapped handshake succeeds
WireGuard Internet Exit can be enabled without replacing the pinned client source with router egress
Close removes authorization while the mapper/STUN control path may remain
CLOSED re-handshake reaches the mapped ingress DROP and does not advance latest-handshake
PPPoE reconnect removes the old Mapping without migrating authorization
bounded interface settle rebuilds a new Mapping automatically
Gate remains CLOSED on the new Mapping until a fresh explicit Activate
fresh WireGuard handshake succeeds through the rebuilt Mapping
```

The representative PPPoE run changed the private PPPoE address, public mapped endpoint and mapper ingress, then successfully established a fresh handshake through the new mapping. Exact addresses and ports are runtime values and are not product assumptions.

The runtime WireGuard Internet Exit path has also been exercised on real hardware. Current split-Dual behavior is covered by CI/browser/runtime contracts but is not yet counted as real-device PASS while IPv6 Gate remains disabled on the current router.

This hardware sample establishes a validated fw3 baseline; it is not a version-number minimum for the OpenWrt-family capability contract.

### Remaining validation before wider promotion

Still pending as distinct hardware work:

```text
real-dashboard automatic Public Direct default + matching Internet Exit
IPv6 Gate after explicitly enabling it
same-WAN Dual data plane
split-WAN Dual data plane and per-family Internet Exit
Mapped Access on a real fw4/nftables device
```

At least one real fw4 path still requires Mapped Access validation before wider promotion. Additional historical CPU/ABI classes keep their own binary-validation status rather than inheriting support from another architecture.

See [`docs/CURRENT-DEVICE-VALIDATION.md`](docs/CURRENT-DEVICE-VALIDATION.md) for the exact current hardware matrix and investigation pitfalls.

## Production checks

Read-only router diagnostics:

```sh
/usr/lib/remote-gate/remote-gate-platform.sh summary
/usr/lib/remote-gate/remote-gate-audit.sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
/usr/lib/remote-gate/remote-gate-mapping.sh status-json
/usr/lib/remote-gate/remote-gate-wireguard-egress.sh status-json
```

0.3.17 exposes sanitized Mapping Engine and Service Registry status without printing mapper payloads, service secrets, WireGuard private keys or Remote Gate credentials.

For each Gate family verify CLOSED -> Activate -> actual service traffic -> TTL -> CLOSED, and separately confirm existing qBittorrent/UPnP/DNAT/FORWARD behavior remains unchanged. For Internet Exit, verify the selected WireGuard subnet uses only the selected per-family WAN and that Close/TTL cleanup removes temporary egress state.

## License

GPL-3.0-only.
