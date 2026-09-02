# Systemic Invariants

This document is the cross-layer engineering checklist for WeiG-Remote-Gate. It exists because several bugs and repeated investigations came from the same structural mistakes rather than from one isolated function.

When another document contains older wording that conflicts with an invariant here, update the older document before implementing code. Do not create a second interpretation in code.

## 1. The recurring root cause: collapsing different layers

The project must keep these concepts separate:

```text
Observed network facts
        |
        v
Capability / eligibility model
        |
        +-------------------+
        |                   |
        v                   v
   AccessPlan         InternetExitPlan
        |                   |
        v                   v
 Access Gate auth      Egress runtime
        |                   |
        +---------+---------+
                  v
          registered service
```

The most common systemic failure is treating one layer as if it were another.

Examples of wrong reasoning:

- a private/CGNAT local WAN address is a **network fact**, not a user-facing Access Endpoint;
- a WAN being recommended by the UI is not runtime authority to migrate an active Gate or Internet Exit session;
- an existing Mapping is not proof that the Gate is OPEN;
- the current HTTP request source is not automatically the authorized remote client source;
- an Access Endpoint is not an Internet Exit;
- a Mapped external port is not the WireGuard listen port;
- a CI contract failure is not a real-router data-plane failure;
- a browser rendering test is not hardware validation.

## 2. Product concepts must not leak implementation facts

User-facing concepts are intentionally small and stable.

Access Methods:

```text
Direct
Mapped
Relay (future)
```

Do not expose implementation/provider names such as NATMap as the product concept.

`Private/CGNAT` remains an internal network classification when needed for discovery, filtering and mapping eligibility. It is not a selectable public Access Endpoint and must not be presented as an Internet Exit product mode.

An IPv4 WAN behind CGNAT may still be a valid Internet Exit when it is up and has the required default route. Access eligibility and egress eligibility are therefore different policies.

## 3. Access and Internet Exit are independent plans

**AccessPlan** answers:

> How does an external client reach the registered WireGuard service?

**InternetExitPlan** answers:

> After WireGuard is established, which address families leave through which validated WANs?

They may default to related WANs for convenience, but neither derives runtime authority from the other.

Canonical Internet Exit modes are:

```text
none
ipv4
ipv6
dual
```

The approved UI/default policy is:

```text
IPv4 Access -> default Internet Exit mode ipv4
IPv6 Access -> default Internet Exit mode ipv6
Dual Access -> default Internet Exit mode dual
```

The user may explicitly choose another supported exit mode, including IPv6-only or Dual exit while the Access Gate itself was opened through IPv4, and vice versa. Runtime validation decides whether the selected WAN(s) can actually provide those families.

A canonical plan is conceptually:

```text
mode: none | ipv4 | ipv6 | dual
wan4: logical WAN or empty
wan6: logical WAN or empty
source: auto | manual
```

Dual egress is one transaction. Same-WAN Dual and split-WAN Dual are two forms of the same plan, not separate subsystems.

## 4. Port identities are never interchangeable

For a registered WireGuard service:

```text
external_port  = Internet-visible Direct/Mapping endpoint port
ingress_port   = router-local ingress protected by Access Gate
service_port   = locally validated WireGuard listen port
```

For Direct access they may be equal. For Mapped access they are allowed to differ.

`service_port` is dynamic runtime service identity. The Service Registry must discover it from the router (for WireGuard, from the actual listener such as `wg show <name> listen-port`). Never hardcode `51820` as architecture or policy. `51820` is only a possible current-device value or test fixture.

The browser/VPS cannot invent any of these ports as authority.

## 5. Capability precedes interaction

A feature that is not available must not be presented as an apparently valid action that fails only after the user enters the flow.

For IP Family controls:

- IPv4, IPv6 and Dual may remain visible so the user understands the device capability;
- unavailable IPv6 is disabled with an explanatory reason;
- Dual is disabled when either required Gate family capability is unavailable;
- if a previously selected family becomes unavailable, selection falls back to a currently valid family without creating authorization.

Capability changes never auto-Activate.

## 6. One policy engine per decision

Do not create parallel implementations for the same policy.

Hard examples:

- `endpointScore()` remains the shared endpoint ordering primitive;
- Access eligibility must have one canonical decision path, not one filter in `app.js` and another contradictory filter in `gate-controls.js`;
- Internet Exit planning must use one canonical plan validator, not separate IPv4/IPv6/Dual planners;
- `fit-text.js` remains the only NetworkIdentityText fitting engine;
- EndpointPicker remains the visible picker infrastructure; do not create separate Dual, IPv6, Mapped or Exit picker frameworks.

A helper inside the owning module is preferred over a new single-purpose module when the responsibility already belongs to that module.

## 7. UI architecture: PathCard, not mode-specific cards

Visual changes must be reviewed against the root `DESIGN.md` and the methodology referenced by:

`https://github.com/voltagent/awesome-design-md`

The approved presentation primitive is:

```text
PathCard
  -> FamilyPathBlock[1] for IPv4 or IPv6
  -> FamilyPathBlock[2] for Dual
```

A Dual Access card uses four information lines:

```text
IPv4   WAN2   Direct
223.73.44.6:7179
IPv6   WAN    Direct
[240e:....]:51820
```

The same structure applies to same-WAN and split-WAN plans. Do not create different DOM/component trees for them.

Do not repeat low-value labels such as `Dual`, `Split WAN` or `Split Exit` inside a card when the two family rows already express that fact.

Access rows may show `Direct`, `Mapped` or another real Access Method. Internet Exit rows show family/WAN/address information without leaking `Private/CGNAT` as a product label.

Module ownership:

- `gate-controls.js`: capability, eligibility, AccessPlan, InternetExitPlan, automatic/manual selection and structured view-model data;
- `endpoint-picker.js`: trigger/sheet/popover/card rendering and interaction only;
- `fit-text.js`: the only responsive fitting engine for complete network identities;
- `interaction.css`: generic picker/PathCard interaction styling;
- `DESIGN.md`: visual/component/responsive contract.

Avoid classes/modules such as `dual-card`, `split-wan-card`, `ipv6-fit`, `mapped-picker` or other mode-specific wheels when the generic primitive can express the state.

## 8. Recommendation is not authority

Automatic selection is convenience only.

The system may recommend:

```text
IPv4 Access: Public Direct -> Mapped -> observed NAT egress Try
IPv6 Access: preferred IPv4 WAN when it also has usable Global IPv6 -> best Global IPv6 Direct
Dual Access: same-WAN Public+IPv6 -> same-WAN Mapped+IPv6 -> split best pair
```

There is no user-facing `Private/CGNAT Try` Access Endpoint.

A manual selection is remembered while it remains valid. Refresh, PPPoE churn, mapping changes or a new recommendation must not create or migrate authorization automatically.

`Activate` remains the authority boundary.

## 9. Dynamic identity must never be hardcoded

Never encode current-device observations as general policy:

- `WAN` / `WAN2` names;
- `pppoe-WAN` / `pppoe-WAN2` devices;
- a current public IPv4/IPv6 address;
- current Mapping tuple;
- WireGuard port `51820`;
- distribution branding or release number.

Use validated runtime identity: logical WAN + current L3 device + current route/service/mapping state.

## 10. Fail closed on identity drift

Runtime state is authoritative only while its validated identity remains current.

Examples:

- Mapping process/state changes -> old mapped ingress authorization does not migrate;
- PPPoE/L3 identity changes -> old Internet Exit plan is cleared;
- selected policy-table default route disappears -> egress is cleared rather than falling through to main;
- stale mapper JSON without current owned process -> reject;
- incomplete Dual egress -> roll back the whole Dual runtime;
- ambiguous WAN/service/port -> omit or reject rather than guess.

## 11. Asynchronous and stale-state investigations

Do not diagnose a failure from one sample taken before the relevant state machine has settled.

Known examples:

- PPPoE `ifup` requires bounded settle for ubus/routes/mapping/firewall;
- Activate is queued/polled/ACKed and an immediate `active=false` sample may be normal;
- Mapping existence and Gate authorization are independent;
- a remap tuple may legitimately be numerically identical to a prior tuple;
- mapper status is valid only with current managed-process ownership.

Wait for the defined bounded settle/ACK boundary, then inspect authoritative state.

## 12. Validation categories must not be conflated

Keep these labels separate:

```text
static/contract test PASS
browser regression PASS
CI PASS
runtime simulator PASS
real-device hardware PASS
```

Only user-provided real-hardware evidence can close a hardware validation item. Never infer hardware PASS from CI, fixtures or browser tests.

Historical failed CI runs are not blockers when the current HEAD is green and the failure was an obsolete contract.

## 13. Git/concurrency rules are part of correctness

Routine development uses `dev` only.

Before a write:

1. query current `dev` HEAD;
2. base the change on that HEAD;
3. before updating the ref, verify `dev` has not advanced unexpectedly;
4. if it advanced, compare paths and rebase the intended change onto the latest HEAD;
5. never force-update or overwrite unknown commits.

Commit messages are English.

## 14. Fresh Agent authority requires synchronized facts

A recently received Agent status is not sufficient runtime authority by itself. Current control-plane authority requires both:

```text
status report is inside the shared Server freshness window
+
current OpenWrt inventory is synchronized with the VPS
```

The Server owns this decision. Browser code must consume the Server-projected `agent.fresh` value and must not create another clock threshold.

Current schema-3 Agents explicitly publish `inventory_synced`. A failed inventory upload must publish `inventory_synced=false`, which immediately makes cached Gate, WireGuard, Internet Exit, Mapping and transport claims non-authoritative even if `reported_at` is recent. Missing `inventory_synced` remains a rolling-upgrade compatibility path for older Agents; new Agents must publish it explicitly.

`Activate` requires fresh Agent authority on the Server before source observation, endpoint validation or queue creation. UI disabled state is never the security boundary.

Command delivery must preserve the asymmetric safety rule:

```text
fresh status + synchronized inventory -> normal command pull
inventory not synchronized            -> do not pull commands
status publication failed             -> close-only pull
```

A close-only pull may inspect the pending command because GET `/api/v1/agent/pull` does not consume it. `Close` may execute and ACK because it reduces access. `Activate` must remain queued and unacknowledged until the Agent has successfully published fresh synchronized status again.

This preserves long-lived Close delivery without allowing a previously queued Activate to execute while the VPS lacks current Agent authority.

## 15. Pre-change checklist

Before implementing any network/UI change, answer all of these:

1. Is this a network fact, a capability, a recommendation, a user plan, or runtime authority?
2. Does AccessPlan remain independent from InternetExitPlan?
3. Are `external_port`, `ingress_port` and `service_port` still distinct?
4. Is every WAN/device/service/port value runtime-derived rather than hardcoded?
5. Is there already an owning module/helper that should be extended instead of adding a new wheel?
6. Will unavailable capability be disabled before interaction rather than failing late?
7. Does the change stay fail-closed when WAN/PPPoE/Mapping identity changes?
8. Are auto selection and explicit Activate still separate?
9. Are tests labeled by their real validation level?
10. If the UI changed, does the design follow `DESIGN.md`, PathCard/NetworkIdentityText and the awesome-design-md methodology?
11. Does Activate still require fresh, inventory-synchronized Agent authority while Close remains deliverable under degraded control-plane conditions?
