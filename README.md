# WeiG-Remote-Gate

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
- locally listening WireGuard UDP ports.

The project registers a firewall include so the guard is restored after a firewall reload/restart. Authorization state is restored only for the remaining TTL; expired state is never reopened.

## UI

The dashboard follows `DESIGN.md` and supports:

- Auto / Light / Dark appearance;
- live OS theme changes in Auto mode;
- no dark-mode flash;
- modular CSS and JavaScript;
- responsive desktop/mobile layouts;
- restrained 3D depth and semantic motion.

## Current version

See [`VERSION`](VERSION).

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
```

For fw4:

```sh
fw4 check
fw4 print | grep -n 'WeiG Remote Gate'
nft list set inet fw4 weig_remote_gate_protected_ifname
```

Then test from two different external IPv4 addresses: the authorized address should reach ICMP/WireGuard during the TTL, while the other address remains blocked. Separately verify the qBittorrent listening/forwarded port remains reachable as before.

## License

GPL-3.0-only.
