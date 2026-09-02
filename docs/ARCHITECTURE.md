# Architecture

This document describes the intended architecture contract. `SYSTEMIC-INVARIANTS.md` explains the cross-layer mistakes this structure is designed to prevent.

## System overview

```text
Browser
  |
  | Cloudflare HTTPS
  v
VPS control plane (loopback-only origin)
  ^
  |
  | outbound authenticated HTTPS
  |
OpenWrt Agent
  |
  +-- Network inventory / capabilities
  +-- Service Registry
  +-- Direct endpoint discovery
  +-- Mapping Engine
  +-- Access Gate firewall abstraction
  +-- Multi-WAN return routing
  `-- temporary WireGuard Internet Exit
```

The browser is a control surface. It is not authority for arbitrary WAN/device/source/service/port values.

## Canonical data flow

Remote Gate uses five conceptual stages:

```text
1. NetworkFacts
      |
2. CapabilityModel
      |
      +------------------+
      |                  |
3a. AccessPlan      3b. InternetExitPlan
      |                  |
4. Server command validation
      |
5. OpenWrt re-validation and runtime authority
```

### NetworkFacts

Examples:

- logical WAN and current L3 device;
- WAN up/down state;
- default routes;
- local IPv4 classification;
- Global IPv6 addresses;
- current Mapping tuple;
- registered WireGuard service/listen port;
- current client-source observations.

Facts are not automatically user choices or runtime authority.

### CapabilityModel

Capabilities answer what is currently possible: IPv4 Gate, IPv6 Gate, Mapped Access, valid egress families, etc.

A missing optional capability disables only that feature. Unsupported IPv6 Gate must disable IPv6/Dual interaction before Activate rather than allowing a late failure path.

## AccessPlan

AccessPlan answers how an external client reaches one locally registered service.

Access Methods:

```text
Direct
Mapped
Relay (future)
```

Current IPv4 automatic ordering:

```text
Public Direct
-> Mapped
-> observed NAT egress Try
```

`Private/CGNAT` is not a user-facing Access Endpoint. It remains an internal network fact used where required for discovery and mapping eligibility.

IPv6 is currently Direct only and requires Global IPv6 plus IPv6 Gate capability.

### Dual AccessPlan

A Dual plan contains one IPv4 endpoint and one IPv6 endpoint for the same registered WireGuard service.

They may use the same or different WANs.

Preference:

```text
same-WAN Public IPv4 Direct + Global IPv6
-> same-WAN Mapped IPv4 + Global IPv6
-> best valid IPv4 + best valid IPv6 across different WANs
```

Split-WAN is normal plan data, not a different subsystem.

Automatic selection is recommendation only. Manual intent is preserved while valid. No plan change creates authorization until explicit Activate.

Browser-only plan preference persistence may remember non-authoritative UI hints such as selected family, WireGuard name, Endpoint ID and WAN fallback identity. `plan-preferences.js` stores only those hints in browser `localStorage`; it must never persist session/CSRF data, client-source authority, Gate authorization or runtime TTL state. Every restore is revalidated through the current `gate-controls.js` option set. Missing or stale identities are discarded, and preference restore must never call Activate.

## InternetExitPlan

Internet Exit is an independent outbound plan. It is not part of Access Endpoint selection and is not constrained to the Access Gate family.

Canonical form:

```text
mode: none | ipv4 | ipv6 | dual
wan4: validated logical WAN or empty
wan6: validated logical WAN or empty
source: auto | manual
```

Default recommendation follows the current Access family for convenience:

```text
IPv4 Access -> ipv4 exit
IPv6 Access -> ipv6 exit
Dual Access -> dual exit
```

The user may explicitly select another supported mode. For example, an IPv4 Access Gate may coexist with IPv6-only or Dual Internet Exit if the WireGuard client configuration and selected WAN capabilities support that traffic.

Egress eligibility is route-based, not public-address-based:

- IPv4: WAN up + current IPv4 default route;
- IPv6: WAN up + current IPv6 default route + usable Global IPv6;
- Dual: both family plans validate; same WAN or split WAN.

A CGNAT/RFC1918 local IPv4 WAN can therefore be a valid IPv4 Internet Exit even though it is not a public Access Endpoint.

Dual egress is transactional and atomic. Same-WAN calls the same logical plan as split-WAN; split execution may use `enable-split`, but there is no second product model.

## Service Registry and ServiceDescriptor

OpenWrt owns service discovery/registration.

Canonical WireGuard service identity:

```text
service_id
service_type = wireguard
transport = udp
name
service_port
```

`service_port` is discovered from the actual current listener. `WG_HOME / UDP 51820` is a possible runtime observation, not an architectural constant.

The browser/VPS selects a known `service_id`; OpenWrt revalidates the current service before activation. The control plane cannot invent a LAN target or arbitrary port forward.

## Endpoint port model

```text
external_port  Internet-visible endpoint port
ingress_port   router-local ingress protected by Access Gate
service_port   registered service listen port
```

Direct WireGuard often uses one numeric port for all three.

Mapped Access normally may use different values:

```text
Internet client
  -> external_address:external_port
  -> ISP/CGNAT Mapping
  -> Mapping Engine ingress_port
  -> Access Gate
  -> UDP relay
  -> WireGuard service_port
```

Never infer the WireGuard service port from the Mapping external port.

## Mapping Engine

Current scope:

- IPv4 UDP;
- bind to validated WAN/L3;
- STUN-style endpoint discovery/keepalive;
- dedicated local ingress socket;
- mapping-change detection;
- bounded client relay state and idle expiry;
- sanitized status;
- WAN reconnect recovery.

A Mapping may remain alive while Gate is CLOSED.

```text
CLOSED: public mapping -> ingress_port -> DROP
ACTIVE: authorized source -> ingress_port -> mapper -> service
TTL/Close: mapping may remain -> ingress_port -> DROP
```

### Exact STUN control path

STUN control is an exact exception, not service access.

```text
validated WAN device
+ mapper ingress_port
+ resolved STUN IPv4
+ STUN source port
```

Startup ordering remains:

```text
resolve STUN
-> bind ingress
-> publish prepared control tuple
-> sync firewall
-> install STUN allow + mapped DROP
-> signal go
-> discover/refresh Mapping
```

Missing/invalid control metadata fails closed.

## Access Gate authorization

Activate body identifies selected family/endpoint/plan but does not grant the browser authority to submit an arbitrary authorization source or arbitrary ingress/service port.

The VPS resolves the current session source and validates the endpoint. OpenWrt independently verifies:

- family;
- source identity;
- WAN/device;
- service identity;
- ingress/service ports;
- access method;
- scope;
- TTL;
- family capability;
- optional InternetExitPlan.

Dual Gate authorization is a batch. Both endpoint records must target the same registered WireGuard service. Partial failure rolls back the batch.

## Source model

IPv4 and IPv6 source observations are independent per authenticated session.

Known router-owned addresses are suppressed as client-source replacements:

- Direct WAN public addresses;
- current Mapped external addresses;
- observed router egress addresses.

When Gate authorization is active, the real authorized source stays pinned so WireGuard Internet Exit cannot create a feedback loop in which the router's own egress becomes the new client identity.

A Close request source is request metadata, not authorization authority.

## Multi-WAN return routing

Each authorized external source has family-scoped destination-specific router-local return routing when required.

This solves replies for both Direct and Mapped ingress and is separate from Internet Exit PBR.

```text
Access return routing:
router-local reply -> authorized external source -> ingress WAN

Internet Exit routing:
packet from WireGuard -> selected egress WAN for that family
```

Do not merge these two route models.

## Internet Exit runtime authority

Temporary egress owns only the WireGuard subnet path:

```text
WG client subnet
  -> family-scoped policy route
  -> selected WAN
  -> scoped FORWARD
  -> NAT44/NAT66 where required
```

For each enabled family, runtime reconciliation validates:

- selected logical WAN is still up;
- saved/current L3 device identity matches;
- ordinary default route still exists through that device;
- Remote Gate policy-table default route still exists through that device.

Any mismatch clears the temporary egress state. No automatic migration to another WAN or PPPoE session is allowed.

## UI architecture

The browser has one generic path presentation language.

```text
PathCard
  -> FamilyPathBlock[]
```

Single-family path: one block.

Dual path: two blocks, rendered as four information lines:

```text
IPv4   WAN2   Direct
223.73.44.6:7179
IPv6   WAN    Direct
[240e:....]:51820
```

Same-WAN, split-WAN, Direct and Mapped use the same component tree. Differences are data, not component families.

Do not repeat `Dual`, `Split WAN` or `Split Exit` labels when the two family rows already communicate the topology.

Internet Exit uses the same PathCard structure but does not expose internal `Private/CGNAT` classification as a user-facing role.

### Browser module ownership

- `gate-controls.js`: endpoint eligibility, endpoint ordering, capability, AccessPlan, InternetExitPlan, auto/manual selection and structured view model;
- `plan-preferences.js`: browser-only persistence adapter for non-authoritative manual plan hints; it never decides endpoint eligibility and never creates authorization;
- `endpoint-picker.js`: visible picker trigger, desktop popover/mobile sheet, PathCard rendering, selected/focus state;
- `fit-text.js`: the only NetworkIdentityText fitting engine;
- `interaction.css`: generic EndpointPicker/PathCard interaction styling;
- root `DESIGN.md`: visual tokens/component/responsive rules.

Do not add separate `dual-*`, `ipv6-*`, `mapped-*` or `exit-*` frameworks when the owning generic module can express the behavior.

## OpenWrt-family compatibility

Compatibility is capability-driven, not distribution-name/version-driven.

- fw3 and fw4 remain behind the firewall abstraction;
- shell remains BusyBox/POSIX compatible;
- package manager detection is independent from firewall semantics;
- mapper artifact selection uses exact package ABI;
- unavailable optional capability degrades independently;
- older fw3 devices remain supported when required capabilities exist.

## Validation model

Do not merge validation categories.

```text
CI/contract/browser evidence != real hardware evidence
```

Real-device PASS is recorded only from actual device tests. Current hardware status is maintained in `CURRENT-DEVICE-VALIDATION.md`.

## Related boundaries

Remote Gate does not own arbitrary forwarded application traffic, qBittorrent/DHT/PeX, UPnP/NAT-PMP or generic port forwarding. See `QB-WEBUI-BOUNDARY.md` for the qB WebUI project boundary.
