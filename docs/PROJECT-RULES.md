# Project Rules

These rules are the hard engineering contract for WeiG-Remote-Gate. Read `SYSTEMIC-INVARIANTS.md` with this file; the two documents are normative together.

## Repository workflow

- Repository: `weigefenxiang/WeiG-Remote-Gate`.
- Routine development happens only on the fixed `dev` branch.
- `main` is the validated stable branch.
- Never create routine feature/version/temporary branches.
- Commit messages are English-only.
- Never force-push or force-update refs.
- Before every write, query the current `dev` HEAD. If it advanced, compare changed paths and rebase the intended change on the new HEAD rather than overwriting unknown work.
- Version identity belongs in `VERSION`/software metadata, not branch names.
- Promotion to `main` requires current CI plus the hardware validation required for the release scope.
- Full Browser Matrix remains release validation on `main`/manual workflow; routine `dev` CI stays lightweight.

## Required documentation before editing

Read:

1. `docs/SYSTEMIC-INVARIANTS.md`
2. `docs/PROJECT-RULES.md`
3. `docs/CURRENT-DEVICE-VALIDATION.md`
4. `docs/ARCHITECTURE.md`
5. `docs/SECURITY-MODEL.md`
6. root `DESIGN.md` for any UI/layout/component work.

Visual work must follow the local `DESIGN.md` and use the `awesome-design-md` methodology as a consistency discipline. Do not copy another site's identity; use the methodology to keep this project's own tokens, components and responsive behavior coherent.

## One Current Owner

Every runtime decision/function has exactly one Current Owner.

When a new implementation becomes canonical, the superseded runtime owner must leave runtime in the same issue chain. Remove its shadow state, obsolete DOM contract and tests that preserve its old behavior.

Forbidden ways to keep a second owner alive include:

- version-file or build-id switching between two implementations;
- CSS overrides that leave obsolete runtime markup/logic active underneath;
- `MutationObserver` used to discover or repair policy state owned elsewhere;
- duplicated browser state that mirrors the canonical plan owner;
- indefinite compatibility adapters for an internal implementation boundary.

Compatibility code is justified only for a real external/protocol/rolling-upgrade boundary and must not become a second product-policy owner.

## Stable product vocabulary

User-facing Access Methods are:

```text
Direct
Mapped
Relay (future)
```

NATMap is not a product concept, required package or provider label.

`Private/CGNAT` is an internal network fact when needed for discovery/eligibility. It must not be presented as a selectable public Access Endpoint and must not be exposed as an Internet Exit mode/identity label.

## Core layering contract

Keep these decisions separate:

```text
Network facts / capability
        |
        +--> AccessPlan ------> Access Gate ------> registered service
        |
        `--> InternetExitPlan -------------------> temporary WG egress
```

Rules:

- AccessPlan answers how the Internet reaches the registered service.
- Access Gate answers which external source may use the selected ingress and for how long.
- Service Registry/Adapter answers which locally validated service receives traffic.
- InternetExitPlan answers which WireGuard traffic families leave through which WANs.
- A default/recommendation is never runtime authority.
- Mapping existence is never Gate authorization.
- Access topology must never silently become Internet Exit topology.

## Access Endpoint rules

IPv4 automatic preference:

```text
Public IPv4 Direct
-> Mapped IPv4
-> observed NAT egress Try
```

Do not expose `Private/CGNAT Try` as a user Access Endpoint.

IPv6 Access is Direct only in the current scope and requires a Global IPv6 endpoint plus IPv6 Gate capability.

Dual Access may combine different WANs. Preference is:

```text
same-WAN Public IPv4 Direct + Global IPv6
-> same-WAN Mapped IPv4 + Global IPv6
-> best valid IPv4 + best valid IPv6 across WANs
```

Do not hardcode WAN names or require Dual to share one WAN.

Unavailable IPv6 Gate capability must disable IPv6 interaction with a reason. Dual must be disabled when either required Gate family capability is unavailable. An unavailable family remains visible when useful for explaining device capability, but it must not behave like a valid selectable action.

Normal ready family state is quiet. Do not show a persistent “OpenWrt currently reports/ready” row merely to restate healthy capability. Family explanatory text is for actionable exceptions such as unavailable capability, missing Source or missing Endpoint.

Automatic endpoint selection is `auto`; explicit user selection is `manual`. Refresh or topology churn may recompute a recommendation but must not auto-Activate or migrate authorization.

## Internet Exit rules

Internet Exit is independent from the Access Gate family and Access Endpoint topology.

Canonical modes:

```text
none
ipv4
ipv6
dual
```

Default mode recommendation:

```text
IPv4 Access -> ipv4 exit
IPv6 Access -> ipv6 exit
Dual Access -> dual exit
```

The user may explicitly select another supported exit mode. A single-family Access Gate does not forbid the WireGuard tunnel from using another Internet Exit family when the corresponding WireGuard subnet and WAN capability are valid.

Canonical plan fields are conceptually:

```text
mode
wan4
wan6
source = auto | manual
```

Canonical interaction is exactly:

```text
none -> no WAN selector
ipv4 -> one IPv4 WAN selector
ipv6 -> one IPv6 WAN selector
dual -> one IPv4 WAN selector + one IPv6 WAN selector
```

Never enumerate IPv4-WAN × IPv6-WAN pair combinations for Internet Exit. Adding more WANs must add eligible rows to family selectors, not multiply Dual plan options. Dual has exactly two scalar family choices regardless of WAN count.

Automatic WAN recommendation is independent from Access Endpoint selection. If the best current WAN is eligible for both IPv4 and IPv6, recommend that same WAN for IPv4, IPv6 and both Dual family fields. Otherwise select the best current WAN independently for each family. A split-WAN AccessPlan therefore does not imply a split-WAN InternetExitPlan.

IPv4 egress requires an up WAN with a current IPv4 default route. Its local address may be public, RFC1918 or CGNAT; that classification does not by itself disqualify outbound Internet use.

IPv6 egress requires an up WAN, a current IPv6 default route and usable Global IPv6.

Dual egress is atomic. Same-WAN and split-WAN Dual are representations of one plan. Any family failure rolls back the whole Dual egress runtime.

Runtime identity is authority: selected logical WAN, current L3 device, main default route and Remote Gate policy-table default route must remain valid. Otherwise clear egress fail-closed. Never fall through to an arbitrary main-table WAN or auto-migrate to a new PPPoE session.

## Service Registry and port model

The browser/VPS must never invent an arbitrary LAN target, service or target port.

A service is first discovered/registered and validated locally on OpenWrt. The control plane selects a `service_id`; OpenWrt independently verifies the current service identity before activation.

For WireGuard, the listen port is runtime data discovered from the actual service. Never hardcode `51820` as policy.

Port identities:

```text
external_port  public Direct/Mapping endpoint port
ingress_port   router-local ingress owned/protected by Remote Gate
service_port   validated local service listen port
```

For Direct they may be equal. For Mapped they may differ. Do not collapse them into an ambiguous `local_port` in new schema/code.

`wg_port` may remain only for rolling compatibility where required; new authority uses the explicit service/ingress fields.

## Mapped Access scope

Current 0.3.17 Mapped Access scope:

- IPv4 only;
- UDP only;
- WireGuard service adapter;
- Remote Gate-owned Mapping Engine;
- dedicated ingress port;
- STUN-style discovery/keepalive;
- mapping-change detection;
- bounded UDP relay state;
- validated Multi-WAN binding;
- sanitized status.

Out of scope unless explicitly revised:

- generic TCP proxying;
- arbitrary port-forwarding UI;
- HTTP/SSH/qBittorrent mapping;
- TURN;
- NATMap package/UCI management;
- user callback scripts;
- runtime `eval`/`sh -c` construction from untrusted values.

## Access Gate invariant

Mapped Access may stay mapped while Gate is CLOSED.

```text
CLOSED: Internet -> mapped endpoint -> ingress_port -> DROP
ACTIVE: approved source -> mapped endpoint -> ingress_port -> mapper -> service
TTL/Close: mapping may remain -> ingress_port -> DROP
```

The firewall authorizes `ingress_port`, not merely `service_port`.

`Close access now` clears temporary Gate authorization and temporary Internet Exit state. It does not need to stop the mapper/STUN control runtime.

## Source authority

The current HTTP request source is observation, not unconditional authorization authority.

Known router Direct addresses, Mapped external addresses and router egress addresses must not replace the real remote client source after the browser begins returning through WireGuard Internet Exit.

The currently authorized source is pinned while active. A Close request's `source_ip` is request metadata only and must never be interpreted as a new authorization source.

## Fail-closed requirements

Reject/omit rather than guess when any authoritative identity is ambiguous or stale, including:

- unknown/down WAN;
- wrong/currently changed L3 device;
- invalid public endpoint address;
- unsupported transport;
- invalid port;
- unknown/unvalidated service;
- stale/orphan mapper state;
- incomplete Dual plan;
- missing current policy route;
- mapper artifact/ABI mismatch.

Mapping changes revoke old authorization rather than migrating it.

## OpenWrt-family compatibility

Target the OpenWrt family by capabilities, not branding/version allowlists. OpenWrt, LEDE, ImmortalWrt branding/version strings are metadata only; capability detection is runtime authority and branding/version alone must not be treated as sufficient authority.

- Support detected `fw3 + iptables + ipset` and `fw4 + nft` backends through the firewall abstraction.
- Keep shell compatible with BusyBox `ash`; no Bash-only/GNU-only/Python/Node/router-compiler runtime dependency.
- Detect package manager (`opkg`/`apk`) independently from firewall semantics.
- Select native mapper binaries by exact package ABI; `uname -m` is diagnostic fallback, not sufficient install authority.
- Unknown ABI means Mapped unavailable, not a guessed binary install.
- Optional capabilities degrade independently: missing IPv6 disables IPv6 Gate; missing mapper disables Mapped; missing egress prerequisites disable Internet Exit.
- Older fw3 systems remain valid targets when actual runtime capabilities satisfy the contract.

## UI/component standardization

Do not build separate interaction systems for IPv4, IPv6, Dual, Direct, Mapped or Exit when the same component can represent them.

Approved Access presentation:

```text
PathCard
  -> one FamilyPathBlock for single-family Access
  -> two FamilyPathBlocks for Dual Access
```

Dual Access card presentation is four information lines:

```text
IPv4   <WAN>   <Access Method when applicable>
<IPv4 endpoint/address>
IPv6   <WAN>   <Access Method when applicable>
<IPv6 endpoint/address>
```

Internet Exit reuses the same `EndpointPicker`/single-family `FamilyPathBlock` renderer for each WAN field. Dual Exit is two independent family pickers, not one generated two-family combination card.

Do not add redundant `Dual`, `Split WAN` or `Split Exit` text where family controls already express the topology.

Module ownership:

- `gate-controls.js`: sole browser policy/state/AccessPlan/InternetExitPlan/view-model owner;
- `endpoint-picker.js`: picker/Card rendering and interaction only;
- `fit-text.js`: only NetworkIdentityText fitting engine;
- `app.js`: refresh/general dashboard rendering only; never a second Access/Exit selection owner;
- `interaction.css`: generic PathCard/EndpointPicker interaction styling;
- `DESIGN.md`: visual contract.

Do not add mode-specific fitting utilities, pickers or card frameworks.

## Firewall ownership

Access Gate owns only Remote Gate registered router-local ingress plus optional Echo Request scope.

Internet Exit owns only its temporary WireGuard-subnet family-scoped PBR/FORWARD/NAT44/NAT66 path.

Never take ownership of unrelated LAN forwarding, qBittorrent/DHT/PeX, UPnP/NAT-PMP, user DNAT/SNAT, NAS/PC services or arbitrary ports.

## Validation truth rules

Keep validation levels explicit:

```text
contract/static test
browser regression
CI
runtime simulation
real hardware
```

Only real user-provided hardware evidence may be recorded as hardware PASS.

Do not use historical CI red runs as evidence against current HEAD when the failure was a stale test contract and current HEAD is green.

Every behavior change needs focused automated coverage at the appropriate layer. Hardware-dependent claims remain pending until exercised on actual hardware.
