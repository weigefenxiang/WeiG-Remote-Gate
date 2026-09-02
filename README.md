# WeiG-Remote-Gate

**Language:** [English](README.md) · [简体中文](translations/README.zh-CN.md)

**Secure Remote Access Gateway for OpenWrt / LEDE / ImmortalWrt.**

WeiG-Remote-Gate is a Cloudflare-fronted control plane for Multi-WAN status and short-lived private remote access. Home WANs do **not** host an HTTP/HTTPS management service. OpenWrt-family routers report inventory/status and pull commands over outbound HTTPS.

The project is capability-based rather than release-name based. OpenWrt, LEDE and ImmortalWrt branding/version strings are metadata; detected runtime capabilities are authority.

## Product model

User-facing Access Methods are:

```text
Direct
Mapped
Relay   (future)
```

- **Direct** — a public IPv4 or Global IPv6 endpoint reaches the registered router-local service directly.
- **Mapped** — Remote Gate owns a NAT mapping, protects a dedicated router ingress with the Access Gate, and relays authorized traffic to a locally registered service.
- **Relay** — reserved for a future relay transport.

NATMap is **not** a dependency, package requirement, provider name or product concept. Mapped Access is implemented by Remote Gate itself.

Current Mapped scope is deliberately narrow: **IPv4 + UDP + WireGuard**. Generic TCP proxying, arbitrary browser-selected port forwarding, HTTP/SSH/qBittorrent mapping, TURN and user callback execution are out of scope.

## Systemic architecture rule

The most important project invariant is that network facts, capabilities, user plans and runtime authority are different layers:

```text
Network facts / capability
        |
        +--> AccessPlan ------> Access Gate ------> registered service
        |
        `--> InternetExitPlan -------------------> temporary WG egress
```

This means:

- `Private/CGNAT` is a network fact, **not a selectable public Access Endpoint**.
- a Mapping is not Gate authorization;
- Access Endpoint is not Internet Exit;
- a recommended/default plan is not runtime authority;
- the current HTTP request source is observation, not unconditional authorization authority;
- stale WAN/device/mapping/route/service identity must fail closed instead of being guessed or silently migrated.

The normative cross-layer rules live in [`docs/SYSTEMIC-INVARIANTS.md`](docs/SYSTEMIC-INVARIANTS.md). Also read [`docs/PROJECT-RULES.md`](docs/PROJECT-RULES.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/SECURITY-MODEL.md`](docs/SECURITY-MODEL.md) and [`docs/CURRENT-DEVICE-VALIDATION.md`](docs/CURRENT-DEVICE-VALIDATION.md).

## Access Endpoint model

The server does not assume one WAN or hardcode `WAN`/`WAN2`.

Current user-eligible Access candidates are:

- public IPv4 `Direct`;
- Global IPv6 `Direct` when IPv6 Gate capability is available;
- IPv4 UDP `Mapped`;
- per-WAN observed IPv4 `NAT egress · Try` as an experimental fallback;
- future `Relay` when implemented.

Private/RFC1918/CGNAT interface addresses may remain in inventory for diagnostics and outbound eligibility, but they are not presented as public Access Endpoints.

Automatic preference is capability-based:

```text
IPv4: Public Direct -> Mapped -> observed NAT egress Try
IPv6: prefer Global IPv6 on the preferred IPv4 WAN when available,
      otherwise use the best Global IPv6 Direct endpoint
Dual: same-WAN Public IPv4 Direct + Global IPv6
      -> same-WAN Mapped IPv4 + Global IPv6
      -> best valid IPv4 + best valid IPv6 across WANs
```

Dual is allowed to split across WANs. No WAN name is product policy.

## Access Gate and Service Registry

The browser cannot invent an arbitrary `192.168.x.x:port` forward. A service must be discovered/registered and validated locally on OpenWrt before it can receive Remote Gate traffic.

Current service support is WireGuard. Its listen port is runtime data discovered from the actual service; `51820` must never be hardcoded as policy.

Mapped Access keeps three port identities separate:

```text
external_port  public Direct/Mapping endpoint port
ingress_port   router-local Remote Gate ingress protected by Access Gate
service_port   validated local service listen port
```

For Direct they may be equal. For Mapped they may differ.

Mapped lifecycle:

```text
CLOSED
Internet -> mapped endpoint -> ingress_port -> DROP

ACTIVE
approved source -> mapped endpoint -> ingress_port -> mapper -> registered service

TTL / Close
mapping may remain -> ingress_port -> DROP
```

The mapper/STUN control path may remain active while the Gate is CLOSED. Mapping existence must never be treated as authorization.

## Source authority

IPv4 and IPv6 client sources are independent records for the authenticated browser session.

Source evidence may come from a Cloudflare HTTP observation or a short-lived family-specific carrier candidate probe. The normal Activate body does not carry an arbitrary authorization address as authority; the VPS resolves the selected family from the session source store.

Router-owned Direct addresses, Mapped external addresses and router Internet Exit addresses are rejected as replacement client evidence. While Gate access is active, the authorized remote source is pinned so the browser returning through WireGuard Internet Exit cannot overwrite itself with the router egress address.

## Internet Exit

Internet Exit is runtime-only and **independent from the Access Gate family**.

Canonical modes are:

```text
none
ipv4
ipv6
dual
```

The default recommendation follows the current Access family (`IPv4 -> ipv4`, `IPv6 -> ipv6`, `Dual -> dual`), but the user may explicitly select another supported exit mode. A single-family Access Gate does not prohibit another WireGuard Internet Exit family when the corresponding tunnel subnet and WAN capability are valid.

IPv4 egress requires an up WAN and current IPv4 default route. The WAN's local IPv4 may be public, RFC1918 or CGNAT; that classification does not by itself disqualify outbound Internet use.

IPv6 egress requires an up WAN, current IPv6 default route and usable Global IPv6.

Dual egress may be same-WAN or split-WAN and is atomic: if either requested family fails validation/install, the whole Dual runtime rolls back. If the selected WAN/L3/default route or Remote Gate policy-table default route is no longer current, egress is cleared fail-closed rather than silently falling through to another WAN.

No persistent Internet Exit UCI policy is created. Disable, Close, TTL expiry, failure rollback or reboot leaves Internet Exit off.

## Firewall and platform compatibility

| Detected stack | Remote Gate backend |
| --- | --- |
| `fw3` + `iptables` + `ipset` | `fw3-iptables` |
| `fw4` + `nft` | `fw4-nftables` |

The Access Gate owns only Remote Gate-registered router-local ingress plus optional Echo Request scope. Internet Exit owns only its temporary WireGuard-subnet PBR/FORWARD/NAT44/NAT66 path. Unrelated qBittorrent/DHT/PeX, UPnP/NAT-PMP, DNAT/SNAT, NAS/PC services and arbitrary ports remain under the user's original firewall policy.

Compatibility rules include:

- BusyBox/POSIX `/bin/sh` baseline;
- `rc.common`, with procd when available and a PID-owned fallback where required;
- independent `opkg`/`apk` detection;
- exact Package ABI authority for native mapper delivery;
- no router compiler requirement;
- unsupported optional capabilities degrade independently instead of breaking unrelated Direct/Gate functions.

An OpenWrt/ImmortalWrt 21.02-class fw3 device is a hardware-validated sample, not a minimum release number.

## Dashboard component model

UI work follows [`DESIGN.md`](DESIGN.md) and the `awesome-design-md` methodology as a consistency discipline.

Access Endpoint and Internet Exit reuse the same structured picker/card primitive:

```text
PathCard
  -> one FamilyPathBlock for IPv4 or IPv6
  -> two FamilyPathBlocks for Dual
```

Dual is represented by two family blocks/four information lines. Same-WAN and split-WAN Dual use the same DOM and do not need redundant `Split WAN` / `Split Exit` labels.

Long network identities use the single shared `fit-text.js` NetworkIdentityText engine. Do not create separate IPv6/WAN/Dual fitting utilities.

## Control/data-plane flow

1. Sign in to the Cloudflare-fronted dashboard.
2. VPS records authenticated HTTP source evidence; the browser may best-effort fill a missing family with a carrier candidate.
3. The dashboard proposes an AccessPlan and InternetExitPlan; the user may override either selection.
4. Only explicit `Activate` creates a short-lived command transaction.
5. OpenWrt pulls the command over outbound HTTPS.
6. OpenWrt revalidates WAN/device, service/ingress identity and TTL from current local runtime state.
7. Access Gate authorizes only the resolved remote source on the selected registered ingress.
8. Mapped Access resolves the current mapping again at activation time.
9. Internet Exit independently validates and installs its temporary family-scoped route/NAT plan when selected.
10. TTL or **Close access now** clears temporary Gate authorization and temporary Internet Exit state; Mapping may remain CLOSED/protected.

The Cloudflare hostname is the **control plane**. Direct/Mapped/Relay endpoints are the **data plane**. Never use the Cloudflare Tunnel hostname as a WireGuard UDP endpoint.

## Repository workflow and validation layers

```text
dev  -> development, fixes and routine CI
main -> validated stable state
```

Routine development uses only the fixed `dev` branch. Do not create `dev/*`, `feature/*`, version or temporary development branches. Commit messages are English-only and refs are never force-updated.

Routine `v0.3.x CI` on `dev` stays lightweight: Python contract tests/compile, shell syntax, native mapper host build/check and JavaScript syntax. The full Linux + Windows Chromium **Release Browser Validation** is a separate `main`-only/manual release layer.

Validation levels are not interchangeable:

```text
contract/static test
browser regression
CI
runtime simulation
real hardware
```

Only actual user-provided device results count as hardware PASS.

## Current hardware-validation boundary

Real-device validation on the current fw3/iptables-legacy/ipset baseline includes:

- IPv4 Mapped Gate CLOSED -> explicit Activate -> fresh external WireGuard handshake -> Close/CLOSED lifecycle;
- source-feedback-loop protection while WireGuard Internet Exit is active;
- PPPoE reconnect -> old Mapping disappears -> bounded settle -> new Mapping rebuilds -> Gate remains CLOSED -> fresh explicit Activate -> fresh handshake succeeds;
- current real-device IPv4 Client / Access Endpoint / Internet Exit / WAN dashboard data and default selection reported normal.

Still pending as separate hardware work:

- manual endpoint-selection persistence across refresh/topology change;
- IPv6 Gate after explicitly enabling it;
- same-WAN Dual data plane;
- split-WAN Dual plus per-family Internet Exit data plane;
- Mapped Access on a real fw4/nftables device.

Do not infer those pending items from CI or simulations. See [`docs/CURRENT-DEVICE-VALIDATION.md`](docs/CURRENT-DEVICE-VALIDATION.md) for the authoritative matrix.

## Update, uninstall and diagnostics

VPS updater:

```sh
/usr/local/lib/remote-gate/update.sh
```

OpenWrt updater and read-only diagnostics are installed under `/usr/lib/remote-gate/`. Updates preserve user credentials/configuration, back up owned state, validate before replacement and roll back on failure. Missing/unsupported mapper delivery makes Mapped unavailable; it must not break unrelated Remote Gate operation.

Useful read-only router checks:

```sh
/usr/lib/remote-gate/remote-gate-platform.sh summary
/usr/lib/remote-gate/remote-gate-audit.sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
/usr/lib/remote-gate/remote-gate-mapping.sh status-json
/usr/lib/remote-gate/remote-gate-wireguard-egress.sh status-json
```

Uninstall removes only Remote Gate-owned resources and does not blindly restore an old whole-firewall snapshot or remove WireGuard by default.

## License

GPL-3.0-only.
