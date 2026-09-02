# Security Model

`SYSTEMIC-INVARIANTS.md` and `PROJECT-RULES.md` are part of this security contract.

## Separate security decisions

Remote Gate separates four authorities:

1. **Access Method / AccessPlan**: how the Internet reaches a registered service.
2. **Access Gate authorization**: which external source may use the selected ingress and for how long.
3. **Service authentication**: owned by the service itself; WireGuard peer keys remain required.
4. **InternetExitPlan**: which WireGuard traffic families may leave through which explicitly validated WANs for a temporary runtime TTL.

A recommendation or UI default is not authority for any of these.

Internet Exit is independent from the Access Gate family. Opening an IPv4 Access Gate does not itself authorize IPv6 ingress, but it may coexist with an explicitly requested IPv6 or Dual outbound Internet Exit when the WireGuard/client/WAN prerequisites are valid.

## Browser and VPS authority limits

The browser/VPS must never gain authority to invent:

- arbitrary LAN target addresses;
- arbitrary service ports;
- arbitrary mapping ingress ports;
- arbitrary WAN devices;
- arbitrary authorization source addresses;
- shell commands or firewall fragments.

The browser selects known IDs/plans. The VPS validates server-owned inventory/session state. OpenWrt independently revalidates the current local authority before changing runtime state.

## Source records and feedback-loop protection

IPv4 and IPv6 client source records are independent per authenticated session.

Observation classes may include verified Cloudflare request sources and shorter-lived family-specific browser probe candidates.

The Activate request does not submit an arbitrary `source_ip` as authority. The server resolves the current trusted source record for the requested family.

Router-owned public identities must never replace the remote-client authorization source merely because browser traffic later returns through WireGuard Internet Exit. Suppress known:

- Direct WAN public addresses;
- current Mapped external addresses;
- observed router egress addresses.

While authorization is active, pin the real authorized client source.

A Close request's current HTTP source is metadata for the request. It is not a new authorization source.

## Service Registry authority

OpenWrt owns the Service Registry.

Every exposed service must be discovered/registered and validated locally before it can appear in an Access Endpoint.

For WireGuard, the current listener and `service_port` are runtime service facts. Never trust a hardcoded `51820` or a browser-supplied value.

The control plane selects `service_id`; OpenWrt revalidates service identity, transport and current listen port before activation.

## Port separation

```text
external_port  Internet-visible endpoint port
ingress_port   router-local ingress protected by Access Gate
service_port   locally validated service listen port
```

Mapped Access is specifically allowed to use different values for all three.

The Access Gate authorizes `ingress_port`. The mapper relays only to the validated registered `service_port`. A Mapping's `external_port` is never service-port authority.

## Direct authorization

For Direct WireGuard, OpenWrt validates:

- source address/family;
- selected WAN and current L3 identity;
- registered WireGuard service;
- ingress/service port;
- scope;
- TTL;
- family capability.

Normal Activate does not require a pre-existing WireGuard handshake. WireGuard authentication still gates the encrypted tunnel itself.

## Mapped Access authorization

Mapped Access uses a Remote Gate-owned mapping/relay path.

Mandatory invariant:

```text
CLOSED
Internet -> mapped endpoint -> ingress_port -> DROP

ACTIVE
approved source -> mapped endpoint -> ingress_port -> mapper -> registered service

TTL / Close
mapping may remain -> ingress_port -> DROP
```

A live Mapping is not authorization.

### STUN control exception

The mapper's STUN discovery/keepalive uses an exact control tuple:

```text
validated WAN device
+ mapper ingress_port
+ resolved STUN IPv4
+ configured STUN source port
```

The control exception must be installed before the general mapped DROP but must never relay control traffic into the service.

Malformed/missing STUN metadata means no go signal and fail-closed behavior.

## Mapping Engine trust boundary

The current mapper scope is IPv4 UDP for registered services.

It must:

- bind only to a validated WAN/L3 device;
- treat runtime/network values as data;
- avoid `eval`, `sh -c` and equivalent runtime command construction;
- bound sessions/memory and expire idle state;
- validate addresses/ports;
- sanitize status/logging;
- avoid secrets in status/logs;
- reject stale/malformed identity;
- survive WAN reconnect without granting stale authority.

A compatible mapper binary is optional capability. Missing mapper disables only Mapped Access.

## Internet Exit authority

Internet Exit is explicit, temporary and independent from AccessPlan.

Modes:

```text
none
ipv4
ipv6
dual
```

The selected plan identifies one validated WAN per enabled family. Same-WAN and split-WAN Dual are both valid.

IPv4 egress can use a WAN whose local address is RFC1918/CGNAT if it has a valid current IPv4 default route. `Private/CGNAT` classification is not an outbound security disqualifier by itself and must not be confused with public Access Endpoint eligibility.

IPv6 egress requires current IPv6 default routing and usable Global IPv6.

Dual egress is transactional. Both family paths must validate/install or the whole egress runtime rolls back.

Temporary ownership is limited to the selected WireGuard subnet path:

- family-scoped policy routing;
- scoped FORWARD acceptance;
- NAT44 for selected IPv4 WG subnet where required;
- NAT66 for selected IPv6 WG ULA subnet where required.

Runtime authority remains valid only while:

- logical WAN is up;
- current L3 device matches the saved plan;
- ordinary default route remains on that device;
- Remote Gate policy-table default route remains on that device.

Any mismatch clears egress. Never silently fall through to another main-table WAN or migrate to a new PPPoE session.

## Dual transactions

Dual Access contains one validated IPv4 endpoint and one validated IPv6 endpoint for the same registered WireGuard service. The WANs may differ.

If either family authorization fails, cancel/roll back the batch so a later success cannot hide a partial failure.

Dual Internet Exit is independent from Dual Access. It may share Access WAN recommendations, but its runtime WAN/family authority is its own validated plan.

## Public-address filtering

Public Access Endpoint addresses must be globally reachable unicast.

Exclude private/CGNAT, loopback, link-local, unspecified, multicast, documentation and other special-use ranges where public reachability is required. IPv6 public endpoints must be valid Internet Global Unicast.

This filtering is for public Access Endpoint authority. It does not mean a private/CGNAT WAN cannot provide outbound Internet Exit.

WireGuard ULA remains valid as an internal tunnel subnet for IPv6 Internet Exit.

## Multi-WAN identity

Every endpoint resolves to one logical WAN and one current L3 device. A Dual AccessPlan may contain two independent endpoint identities.

Ambiguous association is rejected rather than guessed.

Router-local return routing is maintained per authorized external source and family so replies leave through the ingress WAN when needed. This is separate from Internet Exit PBR.

PPPoE/interface churn never grants authority to migrate Gate or Internet Exit state automatically.

## Firewall ownership

Access Gate owns only:

- registered router-local Direct ingress;
- registered Mapped ingress;
- exact STUN control tuples;
- optional Echo Request scope;
- bounded diagnostic verification windows.

Internet Exit owns only its temporary WireGuard-subnet PBR/FORWARD/NAT path.

Remote Gate does not own unrelated LAN forwarding, qBittorrent/DHT/PeX, UPnP/NAT-PMP, manual DNAT/SNAT, NAS/PC forwarding or arbitrary ports.

## Native mapper supply chain

Routers must not compile the mapper during normal install/update.

Artifact selection uses exact OpenWrt-family package ABI, not a broad CPU guess. Unknown ABI fails closed to Mapped unavailable.

A candidate passes separate validation levels:

1. strict build;
2. architecture/startup smoke (for example QEMU user emulation);
3. real OpenWrt-family hardware data-plane validation.

CI artifacts are not automatically production release artifacts. Automatic installation requires exact manifest identity and cryptographic checksum.

## OpenWrt-family compatibility security

Distribution branding/version is not a security decision.

Detect actual capabilities:

- fw3/iptables/ipset or fw4/nft;
- package ABI;
- package manager when needed;
- service manager/runtime capabilities.

Optional capability failure degrades only that feature. Shell remains BusyBox/POSIX compatible.

## Validation truth

Never describe CI, fixtures, browser tests or emulation as real-device PASS.

Real-hardware claims are recorded only from actual user-provided device evidence in `CURRENT-DEVICE-VALIDATION.md`.
