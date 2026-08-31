# Security Model

## Control plane and data plane

Remote Gate separates two decisions:

1. **Control-plane authorization** decides which external source address may send router-local WireGuard UDP traffic (and optionally Echo Request) for a limited TTL.
2. **WireGuard authentication** still decides which peer may establish the encrypted tunnel. A temporary Gate authorization does not replace WireGuard public-key authentication.

Normal Activate no longer requires a pre-existing WireGuard handshake. This allows a user to open the Gate from the authenticated web console and start WireGuard afterwards.

## Source records

IPv4 and IPv6 are independent source records in the authenticated browser session.

- **Cloudflare observed / verified**: learned from the authenticated HTTPS request path.
- **Candidate**: a short-lived address reported by the browser after a family-specific public IP echo probe. It is useful when the dashboard request itself used the other family.

The Activate body never carries an arbitrary `source_ip`. The VPS resolves the selected family from the session source store and validates the selected endpoint server-side. Candidate records are therefore session-bound and CSRF-protected, but they are not equivalent to a WireGuard peer proof; possession of a valid WireGuard peer key remains required to establish the data-plane tunnel.

## Direct temporary authorization

After the VPS queues a command, OpenWrt independently validates:

- source address and IP family;
- selected protected WAN device;
- dynamically discovered WireGuard UDP listen port;
- access scope;
- TTL;
- IPv6 Gate capability when applicable.

If validation succeeds, OpenWrt immediately creates the temporary source authorization. The historical WireGuard activity verifier remains available through the explicit `verify-wireguard` diagnostic action but is not part of normal Activate.

## Concurrent sources

A family may hold multiple authorized source addresses simultaneously. Each source has its own expiry and source-kind metadata. This supports multiple devices or networks using the same WireGuard listener concurrently.

The shared firewall profile for a family remains exact: active records must use the same WAN device, WireGuard UDP port and scope. A request attempting to change that profile while other sources remain active fails closed and asks the user to close existing access first.

`Close access now` clears all temporary IPv4 and IPv6 authorizations.

## IPv4 and IPv6

IPv4 and IPv6 authorization sets are independent. The UI may activate IPv4 only, IPv6 only, or queue both in one Dual transaction. A failed family stops the Dual batch instead of allowing a later family to hide the failure.

Return routing is maintained per authorized source and per family, so multiple `/32` IPv4 or `/128` IPv6 client destinations can coexist on Multi-WAN systems.

## Public-address filtering

Addresses exposed as public IPv6 inventory/endpoint candidates must be globally reachable unicast. The VPS filters inventory at its authoritative storage boundary and cleans previously stored inventory when the dashboard is read.

The policy excludes link-local (`fe80::/10`), unique-local (`fc00::/7`), loopback, unspecified, multicast, documentation and other IANA special-purpose non-globally-reachable ranges. IPv6 must also be inside Internet Global Unicast `2000::/3`.

## Firewall ownership

Remote Gate owns only router-local `INPUT` policy for:

- ICMP/ICMPv6 Echo Request when the selected scope includes Ping;
- dynamically discovered WireGuard UDP listen ports;
- optional short WireGuard UDP-only diagnostic verification windows.

Remote Gate must not own or rewrite `FORWARD`, DNAT, SNAT/MASQUERADE, UPnP, NAT-PMP, qBittorrent forwarding, or unrelated firewall rules.

## Multi-WAN return path

When an authorized source reaches a non-default WAN, Remote Gate installs only a destination-specific router-local policy route so locally generated WireGuard responses leave through the same WAN. Each source is tracked independently and its route disappears when that source expires or all access is closed.
