# Security Model

## Control plane and data plane

Remote Gate separates four decisions:

1. **Access Method** decides how the Internet reaches a locally registered service: Direct, Mapped, or a future Relay path.
2. **Access Gate authorization** decides which external source address may use the selected router-local ingress for a limited TTL.
3. **Service authentication** remains owned by the service itself. For WireGuard, public-key authentication still decides which peer may establish the encrypted tunnel.
4. **Internet Exit** optionally decides whether traffic from an authenticated WireGuard client subnet may be forwarded through a selected WAN for a limited runtime TTL.

A temporary Gate authorization does not replace WireGuard authentication and does not make a mapped endpoint permanently open.

Normal Activate does not require a pre-existing WireGuard handshake. This allows a user to open the Gate from the authenticated web console and start WireGuard afterwards.

## Source records

IPv4 and IPv6 are independent source records in the authenticated browser session.

- **Cloudflare observed / verified**: learned from the authenticated HTTPS request path.
- **Candidate**: a short-lived address reported by the browser after a family-specific public IP echo probe. It is useful when the dashboard request itself used the other family.

The Activate body never carries an arbitrary `source_ip`. The VPS resolves the selected family from the session source store and validates the selected endpoint server-side. Candidate records are therefore session-bound and CSRF-protected, but they are not equivalent to a WireGuard peer proof; possession of a valid WireGuard peer key remains required to establish the data-plane tunnel.

## Service Registry authority

The browser and VPS must never be allowed to invent an arbitrary LAN target or target port.

OpenWrt owns a local Service Registry. Every service exposed through Remote Gate must be discovered or registered locally and validated before it can become an Access Endpoint.

0.3.17 initially registers only WireGuard listeners. Future Shadowsocks, ShadowsocksR or other adapters must follow the same local-registration contract.

A control-plane request identifies a known endpoint/service. It does not gain authority to submit an arbitrary `192.168.x.x:port`, arbitrary ingress port, shell command or forwarding rule.

## Direct temporary authorization

After the VPS queues a command, OpenWrt independently validates:

- source address and IP family;
- selected protected WAN device;
- selected registered ingress;
- registered local service identity;
- access scope;
- TTL;
- IPv6 Gate capability when applicable.

For Direct WireGuard, the registered ingress port is the discovered WireGuard listen port.

If validation succeeds, OpenWrt creates the temporary source authorization. The historical WireGuard activity verifier remains available through the explicit `verify-wireguard` diagnostic action but is not part of normal Activate.

## Mapped Access authorization

Mapped Access uses a dedicated mapper ingress port that may differ from the WireGuard service port.

A mapped endpoint distinguishes:

- `external_port`: the Internet-visible NAT mapping;
- `ingress_port`: the router-local Mapping Engine socket protected by the Access Gate;
- `service_port`: the locally validated service listen port.

The Access Gate authorizes **ingress_port**. The Service Registry separately validates **service_port**. The browser must not be able to substitute either value.

The critical invariant is:

```text
CLOSED
Internet -> mapped public endpoint -> router ingress -> DROP

ACTIVE
approved source -> mapped public endpoint -> router ingress -> mapper -> registered service

TTL / Close
mapping may still exist -> router ingress -> DROP
```

A long-lived NAT mapping is therefore not equivalent to long-lived access.

## Mapping Engine trust boundary

The 0.3.17 Mapping Engine is intentionally limited to IPv4 UDP traversal and relay for registered services.

It must:

- bind only to a validated WAN/l3 device;
- validate all addresses and ports;
- treat STUN/network/runtime values as data only;
- use bounded session state and idle expiry;
- expose sanitized status only;
- avoid logging tokens, private keys or other secrets;
- survive malformed input and WAN reconnect without crashing the Agent;
- never execute runtime values through `eval`, `sh -c` or equivalent command construction.

Malformed, stale or ambiguous mapper state is fail-closed: the mapped endpoint is omitted.

Mapped Access is optional. If no compatible mapper binary is available for a router architecture, Direct endpoints, IPv6 Gate and existing Remote Gate behavior continue normally.

## Concurrent sources

A family may hold multiple authorized source addresses simultaneously. Each source has its own expiry and source-kind metadata. This supports multiple devices or networks using the same registered service ingress concurrently.

The shared firewall profile for a family remains exact: active records must use the same WAN device, registered ingress port and scope. A request attempting to change that profile while other sources remain active fails closed and asks the user to close existing access first.

`Close access now` clears all temporary IPv4 and IPv6 Gate authorizations and any active runtime Internet Exit state owned by the same control flow.

## IPv4 and IPv6

IPv4 and IPv6 authorization sets are independent. The UI may activate IPv4 only, IPv6 only, or queue both in one Dual transaction. A failed family stops the Dual batch instead of allowing a later family to hide the failure.

Mapped Access in 0.3.17 is IPv4/UDP only. IPv6 remains Direct when a global IPv6 endpoint and IPv6 Gate capability are available.

Return routing is maintained per authorized source and per family, so multiple `/32` IPv4 or `/128` IPv6 client destinations can coexist on Multi-WAN systems.

For Internet Exit, IPv4, IPv6 and Dual are explicit modes. Dual egress is transactional: both families must validate and install successfully or the helper rolls back the partial runtime state.

## Public-address filtering

Addresses exposed as public inventory/endpoint candidates must be globally reachable unicast. The VPS filters inventory at its authoritative storage boundary and cleans previously stored inventory when the dashboard is read.

The policy excludes link-local, private/CGNAT where public reachability is required, loopback, unspecified, multicast, documentation and other IANA special-purpose non-globally-reachable ranges. IPv6 must also be inside Internet Global Unicast `2000::/3`.

WireGuard ULA such as `fd00::/8` is intentionally valid as an **internal tunnel subnet** for Internet Exit even though it is not valid as a public WAN endpoint.

## Firewall ownership

### Access Gate

The Access Gate owns only router-local policy for:

- ICMP/ICMPv6 Echo Request when the selected scope includes Ping;
- locally registered Direct service ingress such as discovered WireGuard UDP listen ports;
- locally registered Mapped Access ingress ports owned by the Remote Gate Mapping Engine;
- optional short diagnostic verification windows.

The Access Gate must not install generic FORWARD rules, rewrite unrelated DNAT/SNAT, or take ownership of qBittorrent, UPnP, NAT-PMP or unrelated application traffic.

### Mapping relay

The Mapping Engine may relay authorized UDP datagrams from its registered ingress socket to a validated local service socket. This is not authority for generic LAN forwarding.

0.3.17 must not expose an arbitrary target-address/target-port API. Future Service Adapters must register and validate their targets locally.

### Internet Exit

Internet Exit is a separate, opt-in runtime capability. When explicitly enabled, Remote Gate may temporarily own only the path from the selected WireGuard client subnet to the selected WAN:

- source/interface-scoped policy routing;
- source/interface-scoped FORWARD acceptance required for that WireGuard egress path;
- NAT44 MASQUERADE for the selected IPv4 WireGuard subnet when IPv4 egress is enabled;
- NAT66 MASQUERADE for the selected IPv6 WireGuard ULA subnet when IPv6 egress is enabled.

The helper does not persist these egress rules in UCI. Disable, Close, TTL expiry, failed transactional activation or reboot removes the temporary egress state.

This ownership does **not** extend to ordinary LAN forwarding, qBittorrent/DHT/PeX, UPnP/NAT-PMP, DNAT/manual forwards, NAS/PC forwarding or other router traffic.

## Multi-WAN identity and return path

Every endpoint must resolve to one validated logical WAN and one l3 device. Ambiguous association is rejected rather than guessed.

When an authorized external source reaches a non-default WAN, Remote Gate installs only a destination-specific router-local policy route so locally generated replies leave through the same WAN. Each source is tracked independently and its route disappears when that source expires or all access is closed.

This Gate return path is distinct from Internet Exit PBR. The former routes locally generated/mapper-related service replies toward the authorized external source; the latter routes packets received from the WireGuard interface toward the explicitly selected Internet Exit WAN.

## Old OpenWrt baseline

OpenWrt/ImmortalWrt 21.02-class fw3 systems remain supported.

Security and compatibility rules for that baseline are:

- do not assume Linux 5.6+ cross-process socket reuse;
- use a dedicated mapper ingress port rather than requiring the mapper to share the WireGuard listen socket;
- do not require a compiler on the router;
- do not require NATMap or another third-party traversal package;
- absence of a compatible mapper binary must disable only Mapped Access, not the rest of Remote Gate.

## Project hard rules

The engineering invariants in [`PROJECT-RULES.md`](PROJECT-RULES.md) are part of this security model. Any implementation that needs to relax them must update and review the documented contract before code changes are accepted.
