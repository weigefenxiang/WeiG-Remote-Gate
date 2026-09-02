# AI Handoff

This is the durable continuation entry point for WeiG-Remote-Gate development.

## Mandatory reading order

Before editing, read:

1. `docs/SYSTEMIC-INVARIANTS.md`
2. `docs/PROJECT-RULES.md`
3. `docs/CURRENT-DEVICE-VALIDATION.md`
4. `docs/ARCHITECTURE.md`
5. `docs/SECURITY-MODEL.md`
6. root `DESIGN.md` for visual/UI work.

Do not treat a SHA written in documentation as branch authority. Query the current `dev` HEAD immediately before every write.

## Git workflow

- Repository: `weigefenxiang/WeiG-Remote-Gate`.
- Routine development happens only on fixed branch `dev`.
- Stable branch is `main`.
- Do not create routine feature/version/temporary branches.
- Commit messages are English-only.
- Never force-update refs.
- Re-check `dev` immediately before moving the branch ref. If it advanced, compare paths and replay the intended change on the new HEAD instead of overwriting concurrent work.
- Routine `dev` CI is lightweight. Full Browser Matrix remains `main`-only/manual release validation.
- Never report Browser Matrix PASS or hardware PASS unless that exact validation actually ran.

## Current hardware facts

```text
ImmortalWrt 21.02-SNAPSHOT
mediatek/mt7981
aarch64_cortex-a53
Linux 5.4.x
fw3 + iptables legacy + ipset
WG_HOME / UDP 51820 (current observation only; never a project constant)
```

Observed WAN names/roles are examples, not policy:

```text
WAN  / pppoe-WAN   -> private/CGNAT upstream; Mapped candidate
WAN2 / pppoe-WAN2  -> public IPv4; Direct candidate
```

The current router is user-confirmed IPv6-firewall-capable with `GATE_IPV6='auto'`; IPv6/Dual controls are selectable. That is capability/UI evidence only. IPv6 Gate and Dual data-plane hardware validation remain pending.

## Closed real-device work

Do not reopen these without a new regression:

- IPv4 Mapped CLOSED -> Activate -> external handshake -> Close lifecycle: PASS.
- PPPoE reconnect -> remap -> Gate stays CLOSED -> explicit re-Activate: PASS.
- Client-source feedback-loop protection with active source pinning: PASS.
- Current real-device dashboard data for Client IPv4, Access Endpoint, Internet Exit and WAN list was user-confirmed normal before the current Internet Exit UI refactor.

The current Internet Exit UI refactor is software/contract work only; it does not create a new hardware PASS claim.

## Canonical browser ownership

One feature has one Current Owner.

```text
gate-controls.js
  -> Family / Scope / TTL plan state
  -> Access Endpoint eligibility/ranking
  -> AccessPlan
  -> InternetExitPlan
  -> automatic/manual recommendation
  -> structured PathCard view-model data
  -> single Activate path

endpoint-picker.js
  -> generic picker trigger
  -> desktop popover / mobile sheet
  -> PathCard rendering
  -> selected/focus interaction only

app.js
  -> API/dashboard state
  -> refresh
  -> general dashboard rendering
  -> no Access/Exit policy owner
```

When a new canonical implementation replaces an old runtime implementation, remove the old owner, shadow state, obsolete DOM contract and tests that preserve the old behavior in the same issue chain. Do not keep two implementations alive through version files, CSS overrides, MutationObserver or indefinite compatibility adapters.

## AccessPlan

AccessPlan answers how the external client reaches the registered WireGuard service.

Current user-facing Access methods:

```text
Public IPv4 Direct
Mapped IPv4
observed NAT egress Try
Global IPv6 Direct when capability is available
Relay (future)
```

`Private/CGNAT` remains an internal network fact and is not a selectable public Access Endpoint.

Dual Access contains one IPv4 Endpoint and one IPv6 Endpoint for the same registered WireGuard service. Same-WAN and split-WAN are ordinary plan data. Access Dual may legitimately pair two endpoints; this must not be confused with Internet Exit selection.

Manual Access preferences remain browser-local, non-authoritative hints. They are bound to family and WireGuard service and are revalidated through the current eligible Endpoint set. Restore/fallback never auto-Activates.

## InternetExitPlan: current canonical model

Internet Exit is independent from AccessPlan and is mode-first.

Canonical state:

```text
mode: none | ipv4 | ipv6 | dual
wan4: one validated logical WAN or empty
wan6: one validated logical WAN or empty
```

Canonical interaction:

```text
LAN only
  -> no WAN selector

IPv4
  -> one IPv4 WAN selector

IPv6
  -> one IPv6 WAN selector

Dual
  -> one IPv4 WAN selector
  -> one IPv6 WAN selector
```

Hard rule: Internet Exit must never generate an IPv4-WAN x IPv6-WAN Cartesian product. Adding WAN3/WAN4 only adds rows to the applicable family selector. Dual always contains two scalar family choices regardless of WAN count.

The old browser model based on pre-generated values such as:

```text
ipv4:<WAN>
ipv6:<WAN>
dual:<WAN4>|<WAN6>
```

is not the canonical UI/state model anymore and must not return as a second runtime owner. The Activate API still carries the existing validated fields `egress_mode`, `egress_wan` and `egress_wans`; this refactor changes browser planning/interaction, not the OpenWrt egress executor protocol.

Default mode recommendation follows Access family only as a convenience:

```text
IPv4 Access -> IPv4 Exit mode
IPv6 Access -> IPv6 Exit mode
Dual Access -> Dual Exit mode
```

WAN recommendation is independent from Access Endpoint topology. If one current WAN is the best eligible shared IPv4+IPv6 exit, use it for the applicable IPv4/IPv6 selectors. If no shared WAN exists, recommend the best eligible WAN independently per family.

Therefore:

- split-WAN Access does not imply split-WAN Exit;
- changing Access Endpoint must not silently rewrite an Internet Exit WAN selection;
- a single-family Access Gate may use another supported Exit family or Dual Exit;
- invalid manual Exit WAN state falls back to current recommendation and must not resurrect automatically when topology later recovers.

`gate-controls.js` is the sole InternetExitPlan owner. `app.js` must not contain a second `egressSelections`/`egressWan` state implementation.

## Internet Exit rendering

Reuse existing primitives only:

- `segment` for `LAN / IPv4 / IPv6 / Dual` mode;
- `EndpointPicker` for each visible WAN selector;
- one single-family `FamilyPathBlock` for each Exit WAN option;
- `fit-text.js` for all network identity fitting.

Dual Access still uses one PathCard with two FamilyPathBlocks. Dual Internet Exit is different: it uses two independent single-family WAN pickers, not a generated two-family combination card.

Do not create Exit-specific picker/card/fitting frameworks.

## Quiet healthy state

The Gate family note is exception-only.

Healthy/ready IPv4/IPv6/Dual state does not keep a persistent “OpenWrt currently reports/ready” explanatory row. Show family explanatory text only for actionable conditions such as:

- capability unavailable;
- current Source missing;
- reachable Endpoint missing;
- Agent authority unavailable.

## Gate authority remains unchanged

Gate OPEN authority still requires the current authorized source plus the exact selected Access profile (`device + ingress_port + scope`). Any active mismatched runtime remains Close-only. Dual partial runtime remains Close-only. Failed dashboard transport must revoke cached OPEN display authority while preserving only safe Close hints.

Internet Exit selection remains independent from the Gate close-before-switch guard.

Mapped ingress authority continues to use `ingress_port`, never Mapping `external_port`.

WireGuard service port remains dynamically discovered; `51820` is not policy.

## Validation levels

Never conflate:

```text
static/contract test
browser regression
CI
runtime simulator
real-device hardware
```

Routine `dev` CI executes Python/static/runtime checks and JavaScript syntax checks. Release Playwright scripts may be syntax-checked on `dev`, but executable Browser Matrix remains `main`-only/manual.

The Internet Exit mode-first refactor has focused coverage for:

- one canonical `mode + wan4 + wan6` owner;
- removal of old `egressPlans()` Cartesian-product planning;
- removal of `app.js` shadow Exit state;
- generic EndpointPicker consumer semantics surviving field normalization;
- quiet ready family-note behavior;
- IPv4/IPv6/Dual default recommendations;
- independent single-family and Dual WAN selection;
- invalid manual WAN fallback without resurrection;
- split Access with independent same-WAN Exit default;
- mixed Access-family / Exit-family Activate payloads;
- zero auto-Activate during selection changes;
- mobile/desktop browser-regression syntax coverage.

Do not call those Browser Matrix PASS until the release workflow actually executes them.

## Highest-frequency systemic mistakes

`SYSTEMIC-INVARIANTS.md` is canonical. The recurring classes to remember are:

1. network fact != capability != recommendation != user plan != runtime authority;
2. AccessPlan != InternetExitPlan;
3. Dual Access endpoint pairing != Dual Internet Exit WAN-pair enumeration;
4. recommendation/default != authorization;
5. Mapping active != Gate OPEN;
6. external Mapping port != ingress port != WireGuard service port;
7. stale browser/dashboard data != current authority;
8. one function must not have multiple live Current Owners;
9. healthy state should be quiet instead of accumulating redundant status prose;
10. CI/browser evidence != real hardware evidence.

## Real-device items still pending

Do not claim PASS for:

```text
manual endpoint-selection persistence on real hardware
multiple registered WireGuard service selection on real hardware
mode-first Internet Exit UI behavior on real hardware
IPv6 Gate Activate/handshake/Close data plane
same-WAN Dual data plane
split-WAN Dual data plane
independent/mixed Internet Exit family paths on hardware
Mapped Access on a real fw4/nftables router
non-51820 WireGuard service-port hardware path
```

## Development update commands

OpenWrt `dev` refresh:

```sh
REMOTE_GATE_RAW_BASE='https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/dev' \
FORCE=1 \
/usr/lib/remote-gate/update.sh
```

VPS `dev` refresh:

```bash
REMOTE_GATE_RAW_BASE='https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/dev' \
/usr/local/lib/remote-gate/update.sh
```

The VPS updater freezes to one resolved Git SHA. Verify `/usr/local/lib/remote-gate/BUILD` rather than assuming a same-version deployment is current.
