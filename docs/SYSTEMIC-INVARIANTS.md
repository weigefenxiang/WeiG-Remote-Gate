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

A manual selection is remembered while it remains valid. When a dynamic Endpoint id changes, a browser-local fallback may preserve the same user intent only if the stable logical WAN **and Access Method** still match; for Dual, both family WANs and both family Access Methods must match. WAN identity alone is insufficient when Direct, Mapped or future Relay candidates coexist on the same WAN. Older preferences that do not yet contain a method hint may use the historical WAN-only compatibility fallback, but the current eligible selection must enrich the stored hint for subsequent churn. These hints remain non-authoritative UI state: refresh, PPPoE churn, mapping changes or a new recommendation must not create or migrate authorization automatically.

Registered service identity is part of that manual Access intent. A manual Endpoint hint for one WireGuard service must never be WAN/method-fallback-migrated to another service. If the selected service changes or disappears, discard the incompatible manual hint and return to the canonical automatic recommendation for the newly selected service. When there is only one registered WireGuard service, its selector may be hidden as redundant; when multiple valid services exist, the existing service selector must be visible and user-operable. Service Registry/list ordering is discovery output, not user intent. Service switching and service disappearance never auto-Activate.

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

## 10. Fail closed on identity drift and incomplete activation

Runtime state is authoritative only while its validated identity remains current, and a failed or ambiguous multi-step Activate must never leave a wider Gate state behind.

Examples:

- Mapping process/state changes -> old mapped ingress authorization does not migrate;
- PPPoE/L3 identity changes -> old Internet Exit plan is cleared;
- selected policy-table default route disappears -> egress is cleared rather than falling through to main;
- stale mapper JSON without current owned process -> reject;
- incomplete Dual egress -> roll back the whole Dual runtime;
- Gate `OPEN` for the selected plan requires both the current authorized source and the current family Access profile to match the reported runtime `device + ingress_port + scope`; source equality alone is not enough;
- if an active Gate profile differs from the selected WireGuard/WAN/ingress/scope, expose it as an active profile elsewhere, keep Close available and block replacement Activate until Close converges;
- for Mapped Access, `external_port` is never a substitute for the active `ingress_port` when comparing the selected plan with firewall runtime;
- if Gate authorization succeeds but the requested Internet Exit activation then fails, clear Gate authorization and egress before acknowledging failure;
- clearing/replacing pre-existing Internet Exit runtime is itself an Activate side effect, so it must happen only after the Activate command has a durable runtime `pending` journal;
- Internet Exit cleanup is successful only when the owned firewall/PBR runtime is verified absent; a helper must return failure and retain enough state identity for retry when cleanup cannot be proven complete;
- explicit Internet Exit `none` must clear any previous egress before Gate activation and must not rely on a redundant post-Activate cleanup to converge;
- if any pending Activate expires before its ACK is accepted, treat router runtime as ambiguous and queue a Close rollback; for a multi-family batch also clear the remaining batch tail regardless of which member expired;
- if a Close attempt reports failure, keep that same Close pending for retry instead of treating failure as a terminal command result;
- ambiguous WAN/service/port -> omit or reject rather than guess.

## 11. Asynchronous and stale-state investigations

Do not diagnose a failure from one sample taken before the relevant state machine has settled.

Known examples:

- PPPoE `ifup` requires bounded settle for ubus/routes/mapping/firewall;
- Activate is queued/polled/ACKed and an immediate `active=false` sample may be normal;
- Mapping existence and Gate authorization are independent;
- a remap tuple may legitimately be numerically identical to a prior tuple;
- mapper status is valid only with current managed-process ownership.

An ACK timeout is not proof that an Activate command never executed on the router. Expiry of any unacknowledged Activate is therefore an uncertain-runtime condition: the Server archives that Activate, queues a Close rollback and blocks replacement Activate commands until the Close is resolved. For a multi-family batch, the remaining batch tail is also discarded. Expired Close commands do not recursively create more Close commands.

OpenWrt command delivery is effectively at-least-once until the Server accepts an ACK, so an Activate command and its ACK must both be replay-safe. Before any Gate or Internet Exit side effect, the Agent records the command id as `pending` in its runtime command-result journal. After local execution converges, the final `true` or `false` result replaces `pending` before the ACK is sent.

A successful Activate result has one additional ordering boundary: the Agent must publish the post-side-effect synchronized runtime status before sending the success ACK. If that status publication fails, the saved `true` journal remains authoritative for retry and the success ACK is deferred. This prevents the Server from advancing the transaction while its current Agent authority still describes the pre-Activate runtime.

The Server ACK endpoint is idempotent only for an exact replay of the most recent terminal result: the command id must match `queue.last`, and the repeated boolean must match the stored terminal state (`done` for `true`, `failed` for `false`). Such a replay returns success without advancing `pending`/`next` again and without duplicating activity. A repeated ACK with the opposite boolean remains a conflict.

When an accepted successful ACK advances a multi-command batch, the Server stamps the successor with `predecessor_command_id` at that moment. That field is Server-generated evidence that the predecessor success was already consumed. It is not present merely because two commands were originally placed in the same batch.

The journal follows these fail-closed rules:

- if the first ACK response is lost, the same command id only replays the saved final ACK and must not repeat Gate or egress side effects;
- a finalized journal is retried even when the next command pull is empty, so a single/final command does not depend on receiving the first ACK response to clear its local journal;
- if the same command id is later found in `pending`, local execution is uncertain, so Gate authorization and Internet Exit are cleared before a failure result is journaled and ACKed;
- if a journal belongs to a different command id, a saved `false` result is safe to discard without rollback; a saved `true` result is also safe to preserve only when the current command explicitly names that exact saved id as `predecessor_command_id`; every other saved `true`, `pending` or invalid state may represent live unacknowledged runtime and must be rolled back before the new Activate may execute;
- if the Agent cannot create the pre-side-effect journal, it must not perform Activate side effects;
- if the Agent cannot persist the final result, it must roll back runtime rather than acknowledge a success that cannot be replayed safely;
- rollback is part of the same Activate transaction: if Gate/egress cleanup is incomplete, keep the journal `pending` with rollback intent, do not ACK a final result, do not run a replacement Activate, and retry cleanup only until convergence.

The `predecessor_command_id` exception does not weaken ordinary stale-journal handling. An unrelated or unproven prior success still rolls back first. The exception exists only because the Server can issue the successor proof after it has durably accepted the predecessor success.

The journal belongs to the same runtime-authority lifetime as the firewall/egress state and therefore lives in the runtime namespace rather than becoming long-lived configuration state.

Close is intentionally asymmetric with Activate: re-executing Close is safe because it only reduces access. A failed Close ACK therefore leaves the same Close command pending under its existing deadline, records the failed attempt and lets the Agent pull the same id again. The Server must not extend the deadline automatically on each failure, and it must not allow a new Activate while that Close remains pending. Only a successful Close ACK is terminal.

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

The raw Agent report and the current authority view are different layers. `agent-status.json` preserves the last sanitized Agent POST and must only be written by the Agent status endpoint. Dashboard reads project that raw report through the shared fail-closed freshness helper in memory. A stale or inventory-unsynced projection must never be persisted back over the raw report.

A projected `may_have_active_runtime=true` is only a last-known safety hint. It may keep `Close` visible when current Agent authority is unavailable, because Close reduces access. It must never make the Gate appear OPEN, enable Activate, restore WireGuard/egress runtime claims, or otherwise become authorization authority.

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
12. Is last-known diagnostic state kept separate from the projected authority view, with any stale runtime hint limited to safe Close behavior only?
13. Can an Activate be retried, ACK-lost or interrupted without repeating uncertain side effects; is the final ACK idempotent, is success status published before success ACK, and is a batch predecessor preserved only through Server-generated accepted-predecessor proof?
14. Does every expired unacknowledged Activate converge through a Close rollback, and does a failed Close stay retryable until success or its existing Close deadline?
15. Are pre-Activate cleanup and rollback themselves journal-covered, verified to completion, and retry-only when convergence is incomplete?
16. Does any Gate OPEN indicator require the current source **and** the current family `device + ingress_port + scope` profile, with mismatched active profiles forced through Close-before-switch?
