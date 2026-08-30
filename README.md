# WeiG-Remote-Gate

**Language:** [English](README.md) · [简体中文](translations/README.zh-CN.md)

**Secure Remote Access Gateway for OpenWrt / ImmortalWrt.**

WeiG-Remote-Gate is a Cloudflare-fronted control plane for Multi-WAN status and temporary private remote access. The home WAN does **not** host an HTTP/HTTPS management service. OpenWrt reports inventory/status and pulls short-lived commands over outbound HTTPS.

## Security goal

Remote Gate owns only two kinds of traffic destined to the router itself on protected WAN endpoints:

```text
ICMP / ICMPv6 Echo Request   -> closed by default
WireGuard UDP listen ports   -> closed by default
```

After an authenticated activation, the VPS selects a source address that was recently observed for the same authenticated browser session through Cloudflare. The browser cannot submit an arbitrary authorization IP.

The temporary authorization is scoped to:

```text
(source IP family + exact source IP + WAN device + WireGuard UDP port)
```

Two access scopes are available:

- **WireGuard only** — recommended; Ping remains closed.
- **WireGuard + Ping** — also permits Echo Request from the authorized source.

Authorization expires automatically after 1, 5, 15 or 30 minutes, or can be closed explicitly.

## It does not blanket-filter WAN traffic

Remote Gate deliberately operates only on the router's **INPUT** path. It does not install filtering rules in `FORWARD`, does not take ownership of NAT, and does not manage unrelated TCP/UDP ports.

Therefore existing services remain under the original firewall policy, including:

- qBittorrent / BitTorrent TCP and UDP;
- DHT / PeX;
- UPnP / NAT-PMP;
- DNAT and manual port forwards;
- forwarded NAS / PC services;
- unrelated router-local ports.

A qBittorrent port forward normally follows PREROUTING/DNAT + FORWARD and never enters the Remote Gate INPUT guard.

## Firewall compatibility

The OpenWrt installer auto-detects the firewall implementation:

| Platform | Remote Gate backend |
| --- | --- |
| firewall3 / `fw3` | `iptables` + `ipset` timeout |
| firewall4 / `fw4` | `nftables` timeout sets |

Unsupported systems fail closed during installation. The user does not need to migrate firewall generations for this project.

Known target classes:

- ImmortalWrt / OpenWrt 21.02 class systems -> fw3 backend;
- modern OpenWrt / ImmortalWrt -> fw4 backend.

### Rule priority

The Gate guard is evaluated before the normal `ESTABLISHED,RELATED` shortcut. This prevents an expired WireGuard authorization from surviving through an old conntrack entry.

- fw3: `WEIG_REMOTE_GATE` is inserted at IPv4 `INPUT` position 1; the IPv6 guard is inserted only while an IPv6 protected-device policy exists.
- fw4: the guard uses `chain-pre/input`, before fw4's inbound conntrack state rule.

Existing UCI rules such as `Allow-Ping` are **not deleted**. While Remote Gate is installed, its earlier guard wins for the traffic it owns. Uninstall restores the original firewall behavior.

For IPv6, Remote Gate controls only Echo Request and the selected router-local WireGuard UDP port. Neighbor Discovery, Router Advertisement, Packet Too Big and other ICMPv6 control traffic fall through to the original firewall policy.

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

The Cloudflare hostname is the **control plane**. WireGuard traffic is the **data plane** and must reach the selected home endpoint directly. Do not point a WireGuard UDP endpoint at a Cloudflare Tunnel hostname.

## v0.3 endpoint and source model

The v0.3 inventory uses a schema-2 endpoint model instead of assuming one IPv4 WAN.

A native endpoint may be:

- a directly reachable public IPv4 on an active WAN;
- a directly reachable global IPv6 on an active WAN, when the local firewall backend reports IPv6 Gate capability.

The VPS remembers recently observed IPv4 and IPv6 client sources **per authenticated browser session**. Selecting IPv4 requires a recent trusted IPv4 observation; selecting IPv6 requires a recent trusted IPv6 observation. A stale browser-local display value is never used for authorization.

The OpenWrt control agent can use healthy IPv4 or IPv6 default-route candidates across Multi-WAN links for its outbound HTTPS control traffic. This control path is independent from the WireGuard data-plane endpoint selected by the user.

### NATMap status

The schema and server endpoint builder understand a mapped IPv4 endpoint provider, but Remote Gate does not install or depend on NATMap. On the current 21.02 compatibility path, the agent does not advertise a mapped endpoint unless a supported discovery implementation supplies one.

The read-only audit can inspect existing `/var/run/natmap/*.json` runtime status without printing NATMap configuration content or Remote Gate secrets. Absence of NATMap is normal and has no effect on native IPv4/IPv6 operation.

## Remote Gate flow

1. Sign in to the Cloudflare-fronted dashboard.
2. The server observes the current request source from the trusted Cloudflare path and associates it with that authenticated session.
3. Choose IPv4 or IPv6, an available access endpoint, a WireGuard interface, access scope and TTL.
4. The VPS resolves the chosen endpoint server-side and queues one short-lived command. The browser never provides the authorization IP, WAN device or WireGuard port as trusted authority.
5. The OpenWrt agent pulls the command over outbound HTTPS.
6. The firewall backend validates that the WAN device and WireGuard port are currently protected, then authorizes only the exact source tuple.
7. The agent ACKs the command; a pending command cannot be silently overwritten by a second Activate/Close request.
8. TTL expiry or **Close now** returns the Gate to the closed state.

## Continuous protection and firewall reloads

The agent continuously synchronizes active WAN devices and locally configured/listening WireGuard UDP ports. Configured WireGuard listen ports can therefore remain fail-closed even while the WireGuard interface is temporarily down.

The project registers a firewall include so the guard is restored after firewall reload/restart. Authorization state is restored only for the remaining TTL; expired state is not reopened.

When `GATE_IPV6=disabled`, or when there are no IPv6 protected devices, fw3 removes the idle IPv6 INPUT jump instead of leaving an empty guard chain attached.

## WireGuard note for OpenWrt / ImmortalWrt 21.02

On some 21.02-class builds, adding a new UCI interface with `proto='wireguard'` and running only:

```sh
/etc/init.d/network reload
```

can leave the interface in a `proto: none` / `NO_DEVICE` state even when `/lib/netifd/proto/wireguard.sh` exists. A full network restart may be required once:

```sh
/etc/init.d/network restart
```

This briefly reconnects WAN interfaces. Do not run it remotely without a recovery path. Verify afterward with:

```sh
ifstatus <wireguard-interface>
wg show interfaces
wg show all listen-port
```

## Adaptive dashboard workspace

The dashboard is English-first with automatic Simplified Chinese support and manual language override.

Current UI behavior includes:

- Auto / Light / Dark appearance; on mobile the frequent control is a compact theme button and lower-frequency controls live in the utility sheet;
- adaptive desktop Main Canvas + Utility Rail, with System and Activity kept together instead of wasting a full-width row;
- Arrange mode and browser-local layout preferences on desktop;
- fixed mobile card order with drag disabled for reliable touch scrolling;
- IPv4 and IPv6 client sources displayed independently;
- complete single-line IPv6 display with dynamic font fitting;
- endpoint, family, scope and TTL selection driven by reported capabilities;
- one-line expandable activity records;
- the CLOSED Gate orb and the Activate button sharing the same activation eligibility and action path.

Browser-local UI preferences are not security authority.

## Updating an existing VPS

### v0.2.x -> v0.3 transition

Do **not** rely on the old v0.2.x installed updater for the first v0.3 transition: its fixed file list predates the new schema-2 modules. Bootstrap with the updater from the target release instead:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main/server/update.sh \
  -o /tmp/remote-gate-update.sh

bash -n /tmp/remote-gate-update.sh
bash /tmp/remote-gate-update.sh
```

The updater preserves the existing hostname, login credentials, `WRITE_TOKEN`, sessions and state, creates a rollback backup under `/var/backups/weig-remote-gate/`, restarts the localhost-only service, verifies `/healthz` and the Agent API, and restores the previous application on failure.

Starting with v0.3, the updater is installed and preserved at:

```bash
/usr/local/lib/remote-gate/update.sh
```

so later releases can use the local updater directly.

## Updating an existing OpenWrt installation

Older installations may not yet contain `/usr/lib/remote-gate/update.sh`. For the first transition, download the updater from the target release and run that temporary copy. v0.3 then installs and preserves its own updater, uninstaller and read-only audit utility.

The OpenWrt updater backs up application/config/state plus firewall/network snapshots for recovery, preserves existing WireGuard configuration, validates shell syntax before replacement, rebuilds only Remote Gate-owned INPUT objects, and verifies `ready=true` before restarting the agent.

## Current version

See [`VERSION`](VERSION). Development builds remain marked `0.3.0-dev` until staging and real-device validation are complete.

## Validation status

### Already hardware-validated

The fw3 IPv4 path has been validated end-to-end on a real ImmortalWrt 21.02-class router using `iptables` legacy + `ipset`, PPPoE public WAN, Cloudflare Tunnel control plane and a router-local WireGuard UDP listener.

Verified sequence:

```text
CLOSED
  -> public IPv4 ICMP Echo blocked
  -> public WireGuard UDP blocked

ACTIVATE
  -> only the dashboard-derived trusted IPv4 entered the timeout authorization
  -> source-specific ACCEPT preceded the general DROP
  -> WireGuard handshake and real traffic succeeded

TTL EXPIRED
  -> authorization disappeared
  -> ICMP and WireGuard UDP returned to DROP
  -> a fresh WireGuard handshake could not be established
```

During that validation, the Gate remained INPUT-only. Existing qBittorrent / UPnP / DNAT / FORWARD behavior was not taken over by Remote Gate.

### Implemented and CI-tested, pending final hardware validation

v0.3 implements the corresponding IPv6 Gate path for fw3/fw4, including exact IPv6 source authorization, Echo-Request-only ICMPv6 handling, IPv6 WireGuard UDP protection, empty-policy jump cleanup and IPv4/IPv6 Multi-WAN control transport. These paths are covered by automated tests and syntax/browser CI, but the new IPv6 data-plane behavior has **not yet been declared hardware-validated on the 21.02 fw3 device**.

The fw4/nftables backend follows the same security model but likewise is not part of the documented fw3 real-device validation above.

## Production validation

Start with the read-only audit and firewall state:

```sh
/usr/lib/remote-gate/remote-gate-audit.sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
```

For fw3 IPv4:

```sh
iptables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v4
iptables -S WEIG_REMOTE_GATE
```

For fw3 IPv6 when enabled:

```sh
ip6tables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v6
ip6tables -S WEIG_REMOTE_GATE_V6
```

For fw4:

```sh
fw4 check
fw4 print | grep -n 'WeiG Remote Gate'
nft list set inet fw4 weig_remote_gate_protected_ifname_v4
nft list set inet fw4 weig_remote_gate_protected_ifname_v6
```

For each tested family, verify that only the authorized external source reaches the selected WireGuard endpoint during the TTL and that a fresh handshake fails after expiry. Separately verify the existing qBittorrent listening/forwarded port remains reachable exactly as before.

## License

GPL-3.0-only.
