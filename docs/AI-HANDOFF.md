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

The current responsive Internet Exit/Gate presentation work is software/contract work only; it does not create a new hardware PASS claim.

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
  -> general dashboard presentation
  -> read-only Current WireGuard Public Endpoint projection from Gate structured rows
  -> no Access/Exit policy owner

theme-bootstrap.js
  -> pre-paint theme/favicon setup
  -> early presentation-module asset loading only
```

`theme-bootstrap.js` must not mutate Gate structure, wrap `window.fetch`, install a Gate `MutationObserver`, resolve selected endpoint policy or become a second Gate presentation/data owner. Canonical GateStatusHero/current-public-endpoint markup belongs in `dashboard.html`. `app.js` may display the already-selected structured PathCard row but may not re-filter or re-rank endpoints.

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

## Responsive Internet Exit rendering

Reuse existing primitives only:

- `segment` for `LAN / IPv4 / IPv6 / Dual` mode;
- `EndpointPicker` for every visible WAN selector;
- one single-family `FamilyPathBlock` for each Exit WAN option;
- `fit-text.js` for all network identity fitting.

Single-family behavior is strict:

```text
IPv4 mode -> only IPv4 trigger/options are visible
IPv6 mode -> only IPv6 trigger/options are visible
Dual mode -> the same IPv4 trigger + the same IPv6 trigger, independently
```

An Internet Exit option contains family + logical WAN + WAN address only. It must not show the opposite family and must not display Access endpoint/service/Mapping port identity. Access Endpoint remains the component that may show `<address>:<port>` because that port is part of the inbound service identity.

Phone and desktop have one semantic implementation. On phone the existing `EndpointPicker` becomes its established bottom sheet; on desktop the same picker becomes its established popover. There is no mobile-only Exit planner, select model or card framework.

Dual Access still uses one PathCard with two FamilyPathBlocks. Dual Internet Exit is different: it uses two independent single-family WAN pickers, not a generated two-family combination card.

Do not create Exit-specific picker/card/fitting frameworks.

## Current WireGuard Public Endpoint presentation

The Current WireGuard Public Endpoint is a read-only projection of the currently selected eligible Access PathCard row. It does not have a second endpoint-selection algorithm.

Healthy presentation is deliberately quiet:

```text
Current WireGuard Public Endpoint
<current endpoint value>
```

Do not restore a persistent line such as:

```text
IPv4 Direct · OpenWrt currently reports
IPv6 Direct · OpenWrt currently reports
```

or equivalent Chinese text. Actionable capability/source/endpoint errors belong to the existing Gate/family status surfaces.

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

Focused coverage for the Internet Exit/Gate presentation chain now includes:

- one canonical `mode + wan4 + wan6` owner;
- removal of old `egressPlans()` Cartesian-product planning;
- removal of `app.js` shadow Exit state;
- generic EndpointPicker consumer semantics surviving field normalization;
- mobile IPv4 Exit exposes only the IPv4 picker/FamilyPathBlock;
- mobile IPv6 Exit exposes only IPv6;
- Dual uses the same two scalar pickers;
- desktop consumes the same semantic controls through the existing picker popover;
- Exit PathCards reject Access-style address+port identity;
- Current WireGuard Public Endpoint has no permanent Direct/OpenWrt-report note;
- old `theme-bootstrap.js` Gate DOM/fetch/Observer owner is absent;
- quiet ready family-note behavior;
- IPv4/IPv6/Dual default recommendations;
- invalid manual WAN fallback without resurrection;
- split Access with independent same-WAN Exit default;
- mixed Access-family / Exit-family Activate payloads;
- zero auto-Activate during selection changes.

Do not call those Browser Matrix PASS until the release workflow actually executes them.

## Highest-frequency systemic mistakes

`SYSTEMIC-INVARIANTS.md` is canonical. The recurring classes to remember are:

1. network fact != capability != recommendation != user plan != runtime authority;
2. AccessPlan != InternetExitPlan;
3. Dual Access endpoint pairing != Dual Internet Exit WAN-pair enumeration;
4. Access endpoint/service-port identity != Internet Exit WAN identity;
5. recommendation/default != authorization;
6. Mapping active != Gate OPEN;
7. external Mapping port != ingress port != WireGuard service port;
8. stale browser/dashboard data != current authority;
9. one function must not have multiple live Current Owners;
10. healthy state should be quiet instead of accumulating redundant status prose;
11. bootstrap/presentation helpers must not rediscover policy owned by Gate controls;
12. mobile/desktop presentation must not become separate semantic implementations;
13. CI/browser evidence != real hardware evidence.

## Real-device items still pending

Do not claim PASS for:

```text
manual endpoint-selection persistence on real hardware
multiple registered WireGuard service selection on real hardware
mode-first/family-pure Internet Exit UI behavior on real hardware
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
