# Architecture

```text
Cloudflare HTTPS
      |
      v
VPS control plane (loopback-only origin)
      ^
      |
      | outbound HTTPS
      |
OpenWrt agent
      |
      +-- Multi-WAN report
      +-- Public-WAN discovery
      +-- WireGuard discovery
      `-- Firewall abstraction
            +-- fw3: iptables + ipset
            `-- fw4: nftables
```

## Firewall abstraction contract

`remote-gate-firewall.sh` exposes the same actions on both firewall generations:

```text
detect
install
sync <public-wan-devices> <wireguard-udp-ports>
activate <source-ipv4> <wan-device> <udp-port> <ttl>
clear
restore
status-json
uninstall
```

The agent does not need backend-specific logic.

## Guard boundary

The abstraction is deliberately an INPUT-only guard. It is forbidden from installing Remote Gate filters in FORWARD, so router-local remote access policy is separated from forwarded applications such as qBittorrent.

## Related WeiG qB WebUI project

`weigefenxiang/WeiG-qB-WebUI` is a separate qBittorrent Alternate WebUI project. It owns qBittorrent WebAPI/version compatibility, application Logs/Search/RSS/Settings/Torrent UI and safe browser-side feature enhancement.

Remote Gate does not become a qB API compatibility layer or generic application proxy simply because both projects may be exposed through Cloudflare-managed infrastructure.

```text
Remote Gate
Browser → Cloudflare → Remote Gate control plane ↔ OpenWrt agent
                                      ↓
                           router-local INPUT Gate
                           Ping / WireGuard only

WeiG qB WebUI
Browser → application reverse proxy → WeiG qB WebUI → qB WebAPI → qBittorrent
```

The firewall ownership remains intentionally separate:

```text
router-local Ping / WireGuard UDP → Remote Gate INPUT ownership
forwarded qBittorrent traffic     → existing NAT/FORWARD ownership
```

See [`QB-WEBUI-BOUNDARY.md`](QB-WEBUI-BOUNDARY.md) for the cross-project contract. qB version/capability matrices belong in the qB WebUI repository and must not be duplicated here.

## Priority and timeout

The guard executes before the normal established/related shortcut. This makes expiration immediate for subsequent ICMP/WireGuard packets even if conntrack still has an older flow entry.

- fw3 inserts `WEIG_REMOTE_GATE` at root INPUT position 1 and uses an ipset source entry with timeout.
- fw4 uses `chain-pre/input` and an nftables timeout source set.

## Public-WAN and WireGuard synchronization

The agent discovers active IPv4 default-route interfaces, keeps only public WAN devices, discovers local WireGuard listen ports, and synchronizes those values into the firewall backend. This means Ping is protected even before WireGuard is configured; newly started WireGuard interfaces become protected automatically.

## Firewall reload recovery

A firewall include runs the backend `restore` action after a firewall rebuild. Protected device/port state is restored. An active authorization is restored only for its remaining absolute TTL.

## Why there is no WAN HTTP probe

A browser cannot emit raw ICMP Echo. Creating a browser-accessible probe on the public WAN would require a responding service such as HTTP/HTTPS/WebSocket, which violates this project's threat model. The dashboard therefore reports authorization state and real WireGuard handshake data instead of presenting a fake browser ping.
