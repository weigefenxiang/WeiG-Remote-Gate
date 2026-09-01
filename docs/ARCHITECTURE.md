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
      +-- Multi-WAN control path
      +-- router-local Gate firewall abstraction
      `-- optional runtime WireGuard Internet Exit
```

## Firewall abstraction contract

`remote-gate-firewall.sh` exposes the same router-local Gate actions on both firewall generations:

```text
detect
install
sync <ipv4-devices> [ipv6-devices] <wireguard-udp-ports>
activate <source> <family> <scope> <wan-device> <udp-port> <ttl> [source-kind]
verify-wireguard <source> <family> <wan-device> <udp-port>
clear
restore
status-json
uninstall
```

The agent does not need backend-specific logic. `verify-wireguard` is a diagnostic action; normal Gate activation does not wait for a WireGuard handshake.

## Control-plane authorization flow

The authenticated browser chooses an IP family and endpoint, but it never supplies an arbitrary `source_ip` in the Activate request. The VPS resolves the selected source from the signed-in session source store, validates the endpoint server-side, and queues a short-lived command.

OpenWrt validates the family, WAN device, discovered WireGuard port, scope and TTL again, then immediately adds that source to the temporary firewall authorization set. WireGuard may be started before or after Activate.

IPv4 and IPv6 can be activated independently or queued together as a Dual transaction. If one family in a Dual batch fails, the remaining family is cancelled so a later success cannot mask the failure.

## Concurrent sources

Each family may contain multiple concurrently authorized source addresses, each with its own absolute expiry. This allows a phone and a computer on different external networks to use the same router-local WireGuard listener and UDP port at the same time.

To keep the firewall rule model exact, concurrent records within one family must share the same WAN device, WireGuard UDP port and access scope. Switching that profile requires closing the existing temporary access first.

## Gate and Internet Exit boundaries

The **Access Gate** is deliberately router-local and INPUT-only. `remote-gate-firewall.sh` must not install generic FORWARD filtering or take ownership of unrelated forwarded applications.

The optional **Internet Exit** is a separate runtime-only data-plane feature implemented by `remote-gate-wireguard-egress.sh`. When the user explicitly selects an Internet Exit WAN, it may temporarily install only the state required for the selected WireGuard interface and family:

```text
WireGuard client subnet
        |
        +-- policy routing -> selected WAN
        +-- scoped FORWARD accept
        `-- scoped NAT44 / NAT66 masquerade
```

The egress helper does not create persistent UCI egress policy. Close, TTL expiry, explicit disable or reboot removes its temporary route rules, routing tables and firewall/NAT state.

This exception is intentionally narrow. qBittorrent, DHT/PeX, UPnP/NAT-PMP, DNAT/manual port forwards, forwarded NAS/PC services and unrelated router traffic remain under the router's existing policy.

## Related WeiG qB WebUI project

`weigefenxiang/WeiG-qB-WebUI` is a separate qBittorrent Alternate WebUI project. It owns qBittorrent WebAPI/version compatibility, application Logs/Search/RSS/Settings/Torrent UI and safe browser-side feature enhancement.

Remote Gate does not become a qB API compatibility layer or generic application proxy simply because both projects may be exposed through Cloudflare-managed infrastructure.

```text
Remote Gate control path
Browser -> Cloudflare -> Remote Gate control plane <-> OpenWrt agent
                                      |
                                      `-> router-local INPUT Gate

Optional WireGuard Internet Exit
WireGuard client -> WG interface -> temporary PBR/FORWARD/NAT -> selected WAN

WeiG qB WebUI
Browser -> application reverse proxy -> WeiG qB WebUI -> qB WebAPI -> qBittorrent
```

The firewall ownership remains intentionally separate:

```text
router-local Ping / WireGuard UDP -> Remote Gate Access Gate INPUT ownership
selected WG subnet Internet Exit  -> temporary scoped PBR/FORWARD/NAT ownership
forwarded qBittorrent traffic     -> existing router NAT/FORWARD ownership
```

See [`QB-WEBUI-BOUNDARY.md`](QB-WEBUI-BOUNDARY.md) for the cross-project contract. qB version/capability matrices belong in the qB WebUI repository and must not be duplicated here.

## Priority and timeout

The Gate guard executes before the normal established/related shortcut. This makes expiration immediate for subsequent ICMP/WireGuard packets even if conntrack still has an older flow entry.

- fw3 inserts `WEIG_REMOTE_GATE` at root INPUT position 1 and uses ipset source entries with independent timeouts.
- fw4 uses `chain-pre/input` and nftables timeout source sets.

Internet Exit has its own runtime TTL and reconciliation. It is not evidence that the Access Gate is open, and Access Gate authorization alone is not evidence that Internet Exit is active.

## Public-WAN and WireGuard synchronization

The agent discovers active WAN devices, eligible IPv4/IPv6 paths, and local WireGuard listen ports, then synchronizes those values into the firewall backend. Ping can be protected before a WireGuard peer is connected; a WireGuard listen port is protected as soon as it is discovered.

## Multi-WAN local return routing

Return-route state is maintained per authorized source, not merely per family. Each active IPv4 source can receive its own `/32` destination-specific router-local policy rule and each active IPv6 source its own `/128` rule when the selected WAN is not the ordinary reply path. Expiring one source removes only that source's route state.

This router-local return routing is separate from Internet Exit policy routing. Internet Exit routes packets arriving from the selected WireGuard interface; Gate return routing keeps locally generated WireGuard handshake replies on the WAN where the authorized request arrived.

## Firewall reload recovery

A firewall include runs the Gate backend `restore` action after a firewall rebuild. Protected device/port state is restored. Every still-valid authorization is restored only for its remaining absolute TTL.

Internet Exit remains runtime-only and is reconciled from its temporary state rather than committed as persistent firewall/network UCI configuration.

## Why there is no WAN HTTP probe

A browser cannot emit raw ICMP Echo. Creating a browser-accessible probe on the public WAN would require a responding service such as HTTP/HTTPS/WebSocket, which violates this project's threat model. The dashboard therefore reports authorization state and real WireGuard runtime data without exposing a management service on the home WAN.
