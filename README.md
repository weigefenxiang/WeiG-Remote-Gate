# WeiG-Remote-Gate

**Language:** [English](README.md) · [简体中文](translations/README.zh-CN.md)

**Secure Remote Access Gateway for OpenWrt / ImmortalWrt.**

WeiG-Remote-Gate is a Cloudflare-fronted control plane for Multi-WAN status and temporary private remote access. The home WAN does **not** host an HTTP/HTTPS management service. OpenWrt reports inventory/status and pulls short-lived commands over outbound HTTPS.

## Security and traffic ownership

Remote Gate owns only two kinds of traffic destined to the router itself on protected WAN endpoints:

```text
ICMP / ICMPv6 Echo Request   -> closed by default
WireGuard UDP listen ports   -> closed by default
```

It deliberately operates on router **INPUT** only. It does not install filtering rules in `FORWARD`, does not own NAT, and does not manage unrelated TCP/UDP ports. qBittorrent, DHT/PeX, UPnP/NAT-PMP, DNAT/manual port forwards and forwarded NAS/PC services therefore remain under the original firewall policy.

Two access scopes are available:

- **WireGuard only** — recommended; Ping remains closed.
- **WireGuard + Ping** — also permits Echo Request from the selected source.

For IPv6, Remote Gate controls only Echo Request and the selected router-local WireGuard UDP port. NDP, Router Advertisement, Packet Too Big and other ICMPv6 control traffic fall through to the original firewall policy.

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
OpenWrt
   |
   +-- fw3 or fw4 firewall backend
   +-- IPv4 / IPv6 WAN inventory
   +-- WireGuard discovery
   +-- Multi-WAN control-path selection
   `-- optional runtime capability discovery
```

The Cloudflare hostname is the **control plane**. WireGuard is the **data plane** and must reach the selected home endpoint directly. Never use the Cloudflare Tunnel hostname as a WireGuard UDP endpoint.

## Firewall compatibility

| Platform | Remote Gate backend |
| --- | --- |
| firewall3 / `fw3` | `iptables` + `ipset` timeout |
| firewall4 / `fw4` | `nftables` timeout sets |

The Gate guard is evaluated before the normal `ESTABLISHED,RELATED` shortcut. Existing UCI rules such as `Allow-Ping` are not deleted; the earlier Remote Gate guard wins only for traffic owned by the Gate, and uninstall restores the original firewall behavior.

Known target classes include ImmortalWrt/OpenWrt 21.02-class fw3 systems and modern fw4 systems. Unsupported backends fail closed during installation.

## Schema-2 Multi-WAN endpoint model

The server no longer assumes one public IPv4 WAN. An endpoint may be:

- public IPv4 `Direct`;
- global IPv6 `Direct` when IPv6 Gate capability is enabled;
- NATMap/mapped IPv4 when a supported discovery provider supplies it;
- per-WAN observed IPv4 `NAT egress · Try`;
- private/CGNAT IPv4 `Try` for manual experiments.

Direct/mapped paths are recommended ahead of heuristic/private paths. Private/CGNAT addresses are not falsely described as Internet-reachable; they remain selectable because upstream mappings, NATMap or provider-specific networks may make a path usable.

The OpenWrt agent continuously derives protected IPv4 devices, eligible IPv6 devices and discovered WireGuard listen ports. A temporary authorization is revoked immediately if its WAN device or WireGuard port leaves the current protected policy, even before its TTL expires.

## Dual-stack client sources

IPv4 and IPv6 are independent records for the authenticated browser session. Learning one family never deletes the other.

Source priority:

1. **Cloudflare observation (`verified`)** — the current request's `CF-Connecting-IP`.
2. **Network probe (`heuristic`)** — a short-lived fallback/complement when one family is missing.

v0.3.1 probes missing families independently:

- IPv4: IPv4-only `api.ipify.org`, useful for mobile carrier NAT/CGNAT/NAT64/464XLAT paths;
- IPv6: IPv6-only `api6.ipify.org`, useful when the dashboard itself currently reaches Cloudflare through IPv4 but the device also has usable IPv6.

The authenticated browser posts only the probe result to a session+CSRF-protected endpoint. A later Cloudflare observation for the same family replaces the heuristic value. The normal Activate request still does not carry a raw authorization IP as authority; the VPS resolves the selected family from the session source store.

When both families are usable, the UI **recommends IPv4 first**, but this is not a lock. After the user manually selects IPv6, refreshes preserve that selection while IPv6 remains usable.

## v0.3.1 tactile interaction system

The dashboard follows the design-system discipline documented in [`DESIGN.md`](DESIGN.md), with visual changes reviewed against the hierarchy/spacing/elevation/motion/accessibility approach used by `awesome-design-md` rather than applying isolated shadows or ad-hoc CSS.

### Canonical Wei.G brand icon

The persistent header control and favicon both use the canonical `server/app/static/Wei.G.ico`. The header renders it in a rounded tactile chassis with restrained rim light, contact shadow, hover lift and pressed compression. Clicking it still opens the Utility Sheet.

### EndpointPicker

The browser-native endpoint `<select>` remains only as an internal state bridge and is hidden from the visible UI. `EndpointPicker` provides:

- a structured closed trigger with WAN, family/provider and address/port;
- tactile EndpointCards with Primary/Try state and selected feedback;
- a compact anchored interaction surface on desktop;
- a safe-area-aware Bottom Sheet on mobile;
- Escape/backdrop close, focus containment and ARIA selected state;
- reduced-motion support.

### DurationControl

Quick presets are exactly:

```text
1m | 5m | 15m | 30m | Custom
```

There is no 1h preset.

`Custom` opens a tactile DurationCrown range:

```text
minimum  0.5h
maximum  12h
step     0.5h
```

Every custom detent can provide a short synthesized mechanical tick plus optional light haptic feedback. Sound and haptics are independently switchable in Utility Sheet and stored only as browser-local preferences.

The browser is not the duration authority. Both VPS and OpenWrt firewall independently validate `1m/5m/15m/30m` or half-hour custom steps up to 12h.

## Remote Gate flow

1. Sign in to the Cloudflare-fronted dashboard.
2. VPS records the current Cloudflare-observed source; the browser best-effort completes the missing IPv4/IPv6 family with a short-lived probe.
3. Choose IPv4 or IPv6, an Endpoint, WireGuard interface, Access Scope and duration.
4. VPS resolves the selected session source and endpoint server-side and queues one short-lived command.
5. OpenWrt pulls the command over outbound HTTPS.
6. The firewall validates that the selected WAN device and WireGuard port are still protected, then authorizes only the selected source tuple.
7. OpenWrt ACKs the one-time command. A pending command cannot be silently overwritten.
8. TTL expiry or **Close access now** closes the Gate.

## Optional IPv6 Gate

IPv6 is an optional data-plane capability. Fresh installs default to `GATE_IPV6=auto`; legacy upgrades preserve conservative behavior by adding `GATE_IPV6=disabled` until the operator enables/tests it. IPv4 operation does not depend on IPv6 support.

The outbound control transport is separate from IPv6 Gate. The agent can use healthy IPv4/IPv6 Multi-WAN paths for report/pull/ack even when IPv6 data-plane Gate is disabled.

## NATMap status

Remote Gate understands mapped endpoint records but does not install or require NATMap. The 21.02 compatibility path can safely operate without it. The read-only audit may inspect existing `/var/run/natmap/*.json` runtime status without printing NATMap configuration or Remote Gate secrets.

## Adaptive workspace

- Desktop: Main Canvas + Utility Rail; Activity/System stay readable instead of shrinking into tiny utility cards.
- Mobile/tablet: independent fixed flow `Gate -> Client -> WireGuard -> WAN -> Activity -> System`; desktop drag/span state cannot overlap mobile cards.
- IPv6 remains complete on one line and dynamically fits available width.
- Activity records remain one-line summaries with expandable details.
- CLOSED Gate orb and Activate button share the same eligibility/action path.
- Auto/Light/Dark, language, interaction feedback and Sign out remain standardized utility controls.

## Safe update

### VPS

For a first transition from an old v0.2.x installation, download the current updater instead of relying on the old fixed file list:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main/server/update.sh \
  -o /tmp/remote-gate-update.sh

bash -n /tmp/remote-gate-update.sh
bash /tmp/remote-gate-update.sh
```

From v0.3 onward the local updater is preserved at:

```bash
/usr/local/lib/remote-gate/update.sh
```

The updater preserves hostname, login credentials, `WRITE_TOKEN`, sessions/state, creates a rollback backup under `/var/backups/weig-remote-gate/`, restarts the localhost-only service, checks `/healthz` plus the Agent API and restores the old application on failure.

### OpenWrt

Older installs may need to download the current `openwrt/update.sh` once. v0.3+ then installs/preserves its own updater, uninstaller and read-only audit utility. Update creates application/config/state plus firewall/network backups, preserves WireGuard configuration, validates shell syntax, rebuilds only Remote Gate-owned INPUT objects and fails back to the previous installation if validation fails.

## Safe uninstall

Both VPS and OpenWrt have one-command uninstallers with dry-run support. They create local backups first, remove only resources owned by Remote Gate and perform residual checks. OpenWrt does **not** blindly restore an old whole-firewall snapshot and does not remove WireGuard by default. Cloudflare Tunnel resources are not automatically deleted.

## Current version

See [`VERSION`](VERSION). Development commits use the `-dev` suffix. The release workflow for this repository is: develop on the version branch, require Core + Chromium regression CI to pass, audit the final diff, then fast-forward `main`.

## Validation status

### Hardware validated

The fw3 IPv4 path has been validated end-to-end on a real ImmortalWrt 21.02-class router using iptables legacy + ipset, PPPoE public WAN, Cloudflare control plane and a router-local WireGuard listener. Verified behavior included CLOSED blocking, source-specific Activate, real WireGuard traffic, TTL expiry, fresh-handshake failure after expiry, and preservation of the INPUT-only boundary.

### Implemented and automated-CI tested

Current automated coverage includes:

- schema-2 IPv4/IPv6 endpoint building and ordering;
- public/private/CGNAT/NAT-egress Try paths;
- independent IPv4/IPv6 session sources and probe replacement rules;
- IPv4-first recommendation with manual IPv6 preservation;
- `WireGuard only` / `WireGuard + Ping` scopes;
- custom TTL validation through 12h in VPS and OpenWrt policy;
- fw3/fw4 contract checks and IPv6 Echo-only policy;
- Android/mobile layout overlap regression;
- custom EndpointPicker, Wei.G BrandIcon and DurationControl interaction contracts;
- Chromium regression at 320x800, 360x800, 390x844, 412x915, 768x1024, 1024x768, 1366x768, 1440x900 and 1920x1080.

IPv6 Gate, carrier/NAT source behavior, NAT-egress Try paths and fw4 remain subject to real-network/hardware validation before being described as hardware validated.

## Production checks

Read-only OpenWrt diagnostics:

```sh
/usr/lib/remote-gate/remote-gate-audit.sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
```

fw3 IPv4:

```sh
iptables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v4
iptables -S WEIG_REMOTE_GATE
```

fw3 IPv6 when enabled:

```sh
ip6tables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v6
ip6tables -S WEIG_REMOTE_GATE_V6
```

For each family verify CLOSED -> Activate -> actual WireGuard traffic -> TTL -> CLOSED, and separately confirm existing qBittorrent/UPnP/DNAT/FORWARD behavior remains unchanged.

## License

GPL-3.0-only.
