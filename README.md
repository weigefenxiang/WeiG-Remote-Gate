# WeiG-Remote-Gate

**Language:** [English](README.md) · [简体中文](translations/README.zh-CN.md)

**Secure Remote Access Gateway for OpenWrt / ImmortalWrt.**

WeiG-Remote-Gate is a Cloudflare-fronted control plane for Multi-WAN status and temporary private remote access. The home WAN does **not** host an HTTP/HTTPS management service. OpenWrt reports status and pulls one-time commands over outbound HTTPS.

## Security goal

Remote Gate owns exactly two kinds of traffic destined to the router itself on active public WANs:

```text
ICMP echo-request     -> closed by default
WireGuard UDP ports   -> closed by default
```

After an authenticated dashboard activation, only the server-derived current client IPv4 is temporarily allowed to:

```text
ping the selected public WAN IPv4
reach the selected WireGuard UDP listen port
```

The authorization automatically expires after 1, 5, 15 or 30 minutes.

## It does not blanket-filter WAN traffic

Remote Gate deliberately operates only on the router's **INPUT** path. It does not install filtering rules in `FORWARD` and does not manage unrelated TCP/UDP ports.

Therefore existing services continue to use the original firewall policy, including:

- qBittorrent / BitTorrent TCP and UDP
- DHT / PeX
- UPnP / NAT-PMP
- DNAT and manual port forwards
- forwarded NAS / PC services
- unrelated router-local ports

A qBittorrent port forward is normally handled by PREROUTING/DNAT + FORWARD and never reaches the Remote Gate INPUT guard.

## Firewall compatibility

The OpenWrt installer auto-detects the firewall implementation:

| Platform | Remote Gate backend |
| --- | --- |
| firewall3 / `fw3` | `iptables` + `ipset` timeout |
| firewall4 / `fw4` | `nftables` timeout set |

The user never needs to migrate firewall generations for this project. Unsupported systems fail closed during installation.

Known target examples:

- ImmortalWrt 21.02 / OpenWrt 21.02 class systems -> fw3 backend
- modern OpenWrt / ImmortalWrt -> fw4 backend

## Rule priority

The Gate guard is evaluated before the normal `ESTABLISHED,RELATED` shortcut. This matters when a temporary WireGuard authorization expires: the next matching packet is blocked immediately instead of surviving because of an old conntrack entry.

- fw3: `WEIG_REMOTE_GATE` is inserted at `INPUT` position 1.
- fw4: the guard uses `chain-pre/input`, before fw4's inbound conntrack state rule.

Existing UCI rules such as `Allow-Ping` are **not deleted**. While Remote Gate is installed, its earlier guard wins. Uninstalling Remote Gate restores the original firewall behavior.

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
   | outbound HTTPS report / status / pull / ack
   |
OpenWrt
   |
   +-- firewall backend auto-detection
   |     +-- fw3 -> iptables + ipset
   |     `-- fw4 -> nftables
   +-- WireGuard discovery
   +-- public-WAN discovery
   `-- Multi-WAN inventory
```

The Cloudflare hostname is the **control plane**. WireGuard traffic is the **data plane** and must reach the selected home WAN public IPv4 directly. Do not point a WireGuard UDP endpoint at a Cloudflare Tunnel hostname.

## Remote Gate flow

1. Sign in to the Cloudflare-fronted dashboard.
2. The server derives the client address from the trusted Cloudflare request path.
3. Select a reported public WAN, WireGuard interface and TTL.
4. The VPS queues a short-lived one-time command; the browser cannot submit an arbitrary authorization IP.
5. The OpenWrt agent pulls the command over outbound HTTPS.
6. The firewall backend authorizes only the selected `(source IPv4, WAN device, WireGuard port)` tuple.
7. ICMP echo and the selected WireGuard UDP port become reachable from that source only.
8. Timeout expiry or **Close now** returns the Gate to the closed state.

## Continuous protection and firewall reloads

The agent continuously synchronizes:

- active public-WAN `l3_device` values;
- configured and locally listening WireGuard UDP ports.

Configured WireGuard listen ports are protected even before the WireGuard interface is fully up. This keeps the public UDP port fail-closed during interface startup or netifd problems.

The project registers a firewall include so the guard is restored after a firewall reload/restart. Authorization state is restored only for the remaining TTL; expired state is never reopened.

## WireGuard note for OpenWrt / ImmortalWrt 21.02

On some 21.02-class builds, adding a new UCI interface with `proto='wireguard'` and running only:

```sh
/etc/init.d/network reload
```

can leave the new interface in a state similar to:

```text
proto: none
NO_DEVICE
```

while `/lib/netifd/proto/wireguard.sh` is present. A full network restart may be required once so netifd registers and brings up the new protocol interface:

```sh
/etc/init.d/network restart
```

This briefly reconnects WAN interfaces, so do not run it remotely without a safe recovery path. Verify afterward with:

```sh
ifstatus <wireguard-interface>
wg show interfaces
wg show all listen-port
```

Remote Gate can still protect the configured WireGuard UDP listen port while the interface itself is down.

## Adaptive dashboard workspace

The dashboard follows `DESIGN.md` and is English-first while providing automatic Simplified Chinese support.

It supports:

- Auto / Light / Dark appearance with live OS theme changes in Auto mode;
- automatic Simplified Chinese for `zh`-class browser languages, with English fallback;
- manual `EN / 中文` switching stored only in the browser;
- an adaptive desktop card workspace instead of a fixed grid;
- desktop Arrange mode with drag-and-drop plus button-based reordering;
- browser-local `Compact / Normal / Wide` card sizes and Reset layout;
- fixed mobile card priority with drag disabled to preserve touch scrolling;
- simultaneous display of browser-observed IPv4 and IPv6 values;
- full IPv6 display on exactly one line with dynamic font fitting;
- compact WireGuard Handshake / Traffic / LAN-access guidance;
- restrained depth and semantic motion.

Browser-local remembered IP addresses are **display-only**. They are never submitted as a trusted Gate authorization source.

The currently hardware-validated data-plane authorization remains IPv4. If the dashboard request itself arrives over IPv6, the UI displays that IPv6 address but disables IPv4 activation rather than trusting a stale browser-saved IPv4. IPv6/Dual controls remain unavailable until the matching firewall data plane is implemented and hardware-validated.

## Updating an existing VPS

Existing Remote Gate installations can update application files without regenerating the hostname, login credentials, `WRITE_TOKEN`, sessions, or state:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main/server/update.sh \
  -o /tmp/remote-gate-update.sh

bash /tmp/remote-gate-update.sh
```

The updater creates a backup under `/var/backups/weig-remote-gate/`, restarts the localhost-only service, verifies `/healthz`, verifies the Agent API, and restores the previous application files if the update fails.

## Current version

See [`VERSION`](VERSION).

## Real-device validation

The fw3 backend has been validated end-to-end on a real ImmortalWrt 21.02-class router using `iptables` legacy + `ipset`, PPPoE public WAN, Cloudflare Tunnel control plane and a router-local WireGuard UDP listener.

The verified sequence was:

```text
CLOSED
  -> public ICMP echo blocked
  -> public WireGuard UDP blocked

ACTIVATE
  -> only the dashboard-derived current IPv4 added to the timeout set
  -> source-specific ICMP ACCEPT before the general DROP
  -> source-specific WireGuard UDP ACCEPT before the general DROP
  -> WireGuard handshake and traffic succeeded

TTL EXPIRED
  -> authorization set became empty
  -> source-specific ACCEPT rules disappeared
  -> ICMP and WireGuard UDP returned to DROP
  -> a fresh WireGuard handshake could not be established
```

During the same validation, the Remote Gate chain remained INPUT-only. Existing qBittorrent / UPnP / DNAT / FORWARD behavior was not taken over by Remote Gate.

The fw4/nftables backend is implemented for modern OpenWrt/ImmortalWrt and follows the same security model; the hardware validation described above specifically covers the fw3 path.

## Production validation

After installation, verify the backend shown by:

```sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
```

For fw3:

```sh
iptables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v4
iptables -S WEIG_REMOTE_GATE
```

For fw4:

```sh
fw4 check
fw4 print | grep -n 'WeiG Remote Gate'
nft list set inet fw4 weig_remote_gate_protected_ifname
```

Then test from two different external IPv4 addresses: the authorized address should reach ICMP/WireGuard during the TTL, while the other address remains blocked. After the TTL, disable and re-enable the WireGuard client and verify that no fresh handshake is established. Separately verify the qBittorrent listening/forwarded port remains reachable as before.

## License

GPL-3.0-only.
