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

Do not rely on a handoff SHA as branch authority. Query the current `dev` HEAD before every write.

## Git workflow

- Repository: `weigefenxiang/WeiG-Remote-Gate`.
- Develop only on fixed branch `dev`.
- Stable branch: `main`.
- Never create routine feature/dev/version/temporary branches.
- Commit messages are English.
- Never force-update refs.
- If `dev` advances concurrently, fetch/compare changed paths and rebase intended changes onto the latest HEAD. Never overwrite unknown commits.
- Routine `dev` CI is lightweight; full Browser Matrix is `main`-only/manual Release Browser Validation.

## Current real hardware

```text
ImmortalWrt 21.02-SNAPSHOT
mediatek/mt7981
aarch64_cortex-a53
Linux 5.4.x
fw3 + iptables legacy + ipset
WG_HOME / UDP 51820 (current observation, never a hardcoded rule)
```

Observed topology is dynamic:

```text
WAN  / pppoe-WAN   -> private/CGNAT upstream; Mapped candidate
WAN2 / pppoe-WAN2  -> public IPv4; Direct candidate
```

Never encode those literal names, addresses or ports as policy.

## Closed hardware work: do not reopen without a regression

### IPv4 Mapped CLOSED/OPEN/Close lifecycle: PASS

- mapper may remain alive while Gate is CLOSED;
- exact STUN control remains allowed;
- mapped ingress defaults DROP;
- real cellular IPv4 becomes the source-scoped authorization on Activate;
- fresh external WireGuard handshake succeeds while authorized;
- Internet Exit does not replace the pinned real client source with router egress;
- Close clears Gate authorization and Internet Exit while mapper/STUN may remain;
- fresh external handshake is blocked again.

### PPPoE reconnect -> remap -> explicit re-Activate: PASS

- old PPPoE/Mapping disappears;
- authorization is not migrated;
- bounded settle allows WAN/routes/mapping/firewall to converge;
- new Mapping is recreated automatically;
- Gate remains CLOSED;
- explicit fresh Activate is required;
- fresh external WireGuard handshake succeeds through the new Mapping.

Do not require the remap tuple to be numerically different. Current runtime ownership/freshness is authority.

### Client Source feedback-loop fix: PASS

- router Direct/Mapped/egress addresses cannot replace remote client evidence;
- active authorized source is pinned;
- Close request source is not interpreted as authorization source.

## User-confirmed current dashboard state

The user explicitly confirmed the current real-device IPv4 dashboard data is normal for:

```text
Client IPv4
Access Endpoint
Internet Exit
WAN list
```

Do not reopen the generic claim that current IPv4 dashboard data/default selection is wrong unless a new regression is shown.

Manual endpoint-selection persistence on real hardware is still not separately confirmed.

## Current implemented architecture/UI state

The following items are now implemented in `dev` and covered by contract/static CI. They are no longer merely design targets.

### Capability-aware Family control

- IPv4/IPv6/Dual controls remain visible where useful for explanation.
- IPv6 interaction requires current `gate_ipv6` capability.
- Dual requires both IPv4 and IPv6 Gate capability.
- unavailable capability is disabled with a reason instead of creating a selectable-but-unactivatable dead end.

Current known hardware still has IPv6 Gate disabled; this implementation status is not IPv6 hardware PASS.

### Access eligibility

User-facing Access candidates currently include:

```text
Public IPv4 Direct
Mapped IPv4
observed NAT egress Try
Global IPv6 Direct when capability is available
Relay (future)
```

`Private/CGNAT` may remain internal inventory/network classification but is not a selectable public Access Endpoint.

### Internet Exit is an independent plan

Canonical modes:

```text
none
ipv4
ipv6
dual
```

- default recommendation follows the Access family;
- manual user choice may select another supported mode;
- a single-family Access Gate does not force the same Internet Exit family;
- same-WAN and split-WAN Dual are one `InternetExitPlan` model;
- IPv4 outbound eligibility depends on WAN up/default-route authority, not whether the WAN's local IPv4 is public/RFC1918/CGNAT;
- IPv6 outbound eligibility requires WAN up + IPv6 default route + usable Global IPv6;
- Dual remains atomic/fail-closed.

The VPS/API accepts explicit `egress_mode`; legacy requests that omit it retain backward-compatible derivation. Existing OpenWrt execution primitives are reused rather than creating a second egress executor.

### Shared PathCard

Access Endpoint and Internet Exit reuse the same picker/card renderer:

```text
PathCard
  -> one FamilyPathBlock for IPv4 or IPv6
  -> two FamilyPathBlocks for Dual
```

Dual presentation is four information lines:

```text
IPv4   <WAN>   <Access Method when applicable>
<IPv4 endpoint/address>
IPv6   <WAN>   <Access Method when applicable>
<IPv6 endpoint/address>
```

Same-WAN and split-WAN use the same DOM. Do not restore redundant `Dual · Split WAN` / `Split Exit` presentation.

Module ownership remains:

- `gate-controls.js`: policy/state/plan/view-model;
- `endpoint-picker.js`: shared picker/PathCard rendering;
- `fit-text.js`: only NetworkIdentityText fitting engine;
- `interaction.css`: generic PathCard/EndpointPicker interaction styling;
- `DESIGN.md`: visual contract.

Do not create Dual/IPv6/Mapped/Exit-specific replacement frameworks.

### NetworkIdentityText

`fit-text.js` is the single fitting engine for public WG Endpoint, Client IPs, authorization source, WAN identities/addresses, picker cards and equivalent network identities.

Long values start at normal semantic size and shrink only when actual overflow occurs. Do not reintroduce component-local IPv6/WAN/Dual fitting utilities.

### Dynamic WireGuard service port

Service Registry remains authority for the actual WireGuard listen port.

Keep these identities distinct:

```text
external_port
ingress_port
service_port
```

Do not hardcode `51820`. Automated coverage includes a non-51820 WireGuard service-port path; hardware validation of a non-51820 listener remains pending.

## Automated validation state

Routine `dev` CI covers:

- Python contract tests;
- Python compile;
- shell syntax;
- native mapper host build/check;
- production JavaScript syntax;
- syntax of `tests/browser_layout.mjs` and `tests/browser_split_dual.mjs`.

The release browser tests were updated for the current plan encoding:

```text
ipv4:<WAN>
ipv6:<WAN>
dual:<WAN4>|<WAN6>
```

They also assert one FamilyPathBlock for single-family PathCard and two for Dual PathCard. Routine `dev` CI only syntax-checks those browser scripts; it does **not** execute the full Browser Matrix. Full Linux/Windows Chromium execution remains `main`-only/manual Release Browser Validation.

README and Chinese README are guarded by `tests/test_documentation_contract.py` so old Private/CGNAT Try, old source terminology and obsolete routine-Chromium-CI wording do not silently return.

## Systemic investigation mistakes

Do not duplicate the full list here. `SYSTEMIC-INVARIANTS.md` is canonical.

Highest-frequency reminders:

- Access Endpoint != Internet Exit;
- network fact != capability != user plan != runtime authority;
- external Mapping port != mapper ingress port != WireGuard service port;
- recommendation/default != authorization;
- Mapping active != Gate open;
- current HTTP source after WG egress != automatically the remote client;
- WAN names/addresses/51820 are runtime observations, not policy constants;
- stale/early samples are not settled state;
- CI/browser PASS != hardware PASS;
- extend shared modules instead of creating parallel ranking/planning/fitting/picker engines.

## Current real-device items still pending

Do not claim PASS for:

```text
manual endpoint-selection persistence
IPv6 Gate
same-WAN Dual data plane
split-WAN Dual data plane
independent Internet Exit family-mode hardware paths
fw4/nftables Mapped Access
non-51820 WireGuard service-port hardware path
```

## Development update commands

OpenWrt same-version `dev` refresh:

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
