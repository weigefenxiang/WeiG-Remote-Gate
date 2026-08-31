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

## Guard boundary

The abstraction is deliberately an INPUT-only guard. It is forbidden from installing Remote Gate filters in FORWARD, so router-local remote access policy is separated from forwarded applications such as qBittorrent.

## Priority and timeout

The guard executes before the normal established/related shortcut. This makes expiration immediate for subsequent ICMP/WireGuard packets even if conntrack still has an older flow entry.

- fw3 inserts `WEIG_REMOTE_GATE` at root INPUT position 1 and uses ipset source entries with independent timeouts.
- fw4 uses `chain-pre/input` and nftables timeout source sets.

## Public-WAN and WireGuard synchronization

The agent discovers active WAN devices, eligible IPv4/IPv6 paths, and local WireGuard listen ports, then synchronizes those values into the firewall backend. Ping can be protected before a WireGuard peer is connected; a WireGuard listen port is protected as soon as it is discovered.

## Multi-WAN local return routing

Return-route state is maintained per authorized source, not merely per family. Each active IPv4 source can receive its own `/32` router-local policy rule and each active IPv6 source its own `/128` rule when the selected WAN is not the ordinary reply path. Expiring one source removes only that source's return-route state.

## Firewall reload recovery

A firewall include runs the backend `restore` action after a firewall rebuild. Protected device/port state is restored. Every still-valid authorization is restored only for its remaining absolute TTL.

## Why there is no WAN HTTP probe

A browser cannot emit raw ICMP Echo. Creating a browser-accessible probe on the public WAN would require a responding service such as HTTP/HTTPS/WebSocket, which violates this project's threat model. The dashboard therefore reports authorization state and real WireGuard runtime data without exposing a management service on the home WAN.
