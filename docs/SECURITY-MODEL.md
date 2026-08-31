# Security Model

## Trust levels

Remote Gate distinguishes an observed source from an authorized source.

- **Cloudflare verified**: the source family observed by the VPS through the authenticated control request.
- **Candidate**: an address returned to the browser by a public IPv4/IPv6 echo service. It may be useful for CGNAT discovery but is never sufficient for firewall authorization.
- **WireGuard verified**: the address obtained from fresh authenticated WireGuard peer activity on the selected WAN and dynamically discovered WireGuard listen port. This is the final authorization source.

The browser cannot submit an `authorized source_ip`.

## Candidate verification

For an Activate request, OpenWrt snapshots the selected WireGuard listener and opens an exact-source WireGuard UDP verification window for a few seconds. A successful fresh peer handshake or receive counter change must identify the same source.

If the candidate is not the actual UDP egress (for example, carrier CGNAT maps HTTP and UDP differently), the exact-source window closes and a second short **WireGuard-only discovery** window is opened on the selected WAN and WireGuard UDP port. Only authenticated WireGuard peer activity can produce the final source. Multiple peers becoming active during discovery is ambiguous and fails closed.

Verification windows never open Ping and never touch `FORWARD`.

## IPv4 and IPv6

IPv4 and IPv6 authorizations are independent records with independent source address, WAN device, WireGuard port, scope and expiry. The UI may activate IPv4 only, IPv6 only, or queue both families in one dual-stack request. Each family must pass its own WireGuard verification.

Return routing is also maintained per family so IPv4 and IPv6 can use different WAN policy tables without overwriting each other.

## Public-address filtering

Addresses exposed as public IPv6 inventory/endpoint candidates must be globally reachable unicast. The VPS filters inventory at its authoritative storage boundary and cleans previously stored inventory when the dashboard is read.

The policy excludes link-local (`fe80::/10`), unique-local (`fc00::/7`), loopback, unspecified, multicast, documentation and other IANA special-purpose non-globally-reachable ranges. IPv6 must also be inside Internet Global Unicast `2000::/3`.

## Firewall ownership

Remote Gate owns only router-local `INPUT` policy for:

- ICMP/ICMPv6 echo request when the selected scope includes Ping;
- dynamically discovered WireGuard UDP listen ports;
- short WireGuard UDP-only verification windows.

Remote Gate must not own or rewrite `FORWARD`, DNAT, SNAT/MASQUERADE, UPnP, NAT-PMP, qBittorrent forwarding, or unrelated firewall rules.

## Multi-WAN return path

When a verified WireGuard source arrives on a non-default WAN, Remote Gate installs only a destination-specific router-local policy route so the locally generated WireGuard response leaves through the same WAN. IPv4 and IPv6 route state are independent and removed with authorization expiry/close.
