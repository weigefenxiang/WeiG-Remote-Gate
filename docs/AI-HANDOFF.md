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

Do not rely on an old handoff SHA. Query the current `dev` HEAD before every write.

## Git workflow

- Repository: `weigefenxiang/WeiG-Remote-Gate`.
- Develop only on fixed branch `dev`.
- Stable branch: `main`.
- Never create routine feature/dev/version/temporary branches.
- Commit messages are English.
- Never force-update refs.
- If `dev` advances concurrently, fetch/compare changed paths and rebase intended changes onto the latest HEAD. Never overwrite unknown commits.

The runtime-code baseline immediately before the current docs consolidation is:

```text
ed837796e30ede137ca5671db7f683df1675039d
```

That commit standardized responsive network identity fitting. The docs commit that contains this handoff will be newer while the runtime code may still be unchanged.

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

Never encode those literal names as policy.

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

The user explicitly confirmed that these real-device values are normal:

```text
Client IPv4
Access Endpoint
Internet Exit
WAN list
```

Do not reopen the generic claim that current IPv4 dashboard data is wrong unless a new regression is shown.

Manual endpoint-selection persistence on real hardware is still not separately confirmed.

## Approved next architecture/UI target

The next implementation must follow the contracts already written in `SYSTEMIC-INVARIANTS.md`, `PROJECT-RULES.md` and `ARCHITECTURE.md`.

Key points:

1. **Capability-aware Family control**
   - current device IPv6 Gate is disabled;
   - IPv6 remains explainable/visible but disabled;
   - Dual is disabled when IPv6 Gate is unavailable;
   - unavailable capability must not lead to a selectable-but-unactivatable dead end.

2. **Dual PathCard**
   - one generic `PathCard` with two `FamilyPathBlock`s;
   - four information lines:

   ```text
   IPv4   <WAN>   <Direct|Mapped|...>
   <IPv4 endpoint>
   IPv6   <WAN>   <Direct|...>
   <IPv6 endpoint>
   ```

   - same DOM/component for same-WAN and split-WAN;
   - remove redundant `Dual`, `Split WAN` and `Split Exit` presentation.

3. **Internet Exit decoupled from Access family**
   - modes: `none / ipv4 / ipv6 / dual`;
   - IPv4 Access defaults to IPv4 Exit, IPv6 to IPv6 Exit, Dual to Dual Exit;
   - this is recommendation only; user may select another supported mode;
   - same-WAN/split-WAN Dual are one InternetExitPlan model;
   - backend/API/OpenWrt validation must treat the egress plan as independent authority.

4. **Private/CGNAT presentation**
   - keep classification internally when needed;
   - remove user-facing `Private/CGNAT Try` Access Endpoint;
   - do not show `Private/CGNAT` as an Internet Exit product label;
   - a CGNAT WAN can still be a valid IPv4 outbound exit when routing prerequisites are valid.

5. **Dynamic WireGuard service port**
   - do not hardcode `51820`;
   - Service Registry remains the only authority for current WireGuard listen port;
   - keep `external_port`, `ingress_port`, `service_port` distinct;
   - add non-51820 regression coverage.

6. **No new wheels**
   - `gate-controls.js` owns policy/plans/view model;
   - `endpoint-picker.js` owns picker/PathCard rendering;
   - `fit-text.js` remains the only fitting engine;
   - `interaction.css` owns generic PathCard/EndpointPicker interaction styling;
   - use root `DESIGN.md` and awesome-design-md methodology for visual consistency;
   - do not create Dual/IPv6/Mapped/Exit-specific replacement frameworks.

These are approved targets, not claims that current deployed code/hardware already implements or validates them.

## Systemic investigation mistakes

Do not duplicate the full list here. `SYSTEMIC-INVARIANTS.md` is canonical.

Highest-frequency reminders:

- Access Endpoint != Internet Exit;
- network fact != user product option != runtime authority;
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
