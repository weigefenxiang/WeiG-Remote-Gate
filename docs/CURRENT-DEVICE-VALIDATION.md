# Current Device Validation

This file records only current-device facts and real-hardware validation status. Architecture and product rules live in `ARCHITECTURE.md`, `PROJECT-RULES.md` and `SYSTEMIC-INVARIANTS.md`.

## Current hardware target

```text
Distribution: ImmortalWrt 21.02-SNAPSHOT
Target:       mediatek/mt7981
Package ABI:  aarch64_cortex-a53
Kernel:       Linux 5.4.x / aarch64
Firewall:     fw3 + iptables legacy + ipset
Service:      WG_HOME / UDP 51820 (current observed device value only)
```

`51820` is not a project constant. WireGuard service port must remain dynamically discovered from the actual listener.

Observed WAN roles on this device are dynamic examples only:

```text
WAN   / pppoe-WAN   -> private/CGNAT upstream; Mapped candidate
WAN2  / pppoe-WAN2  -> public IPv4; Direct candidate
```

Do not encode these literal names, addresses or device IDs as general policy.

## Current capability status

Current physical router:

```text
IPv4 Gate: enabled/validated
IPv6 Gate: disabled
Mapped IPv4: available on the tested fw3 device
```

Because IPv6 Gate is disabled, IPv6 Gate and Dual Gate are not real-device PASS. The approved UI contract exposes the unavailable capability clearly but disables the action rather than allowing a user to enter a flow that cannot Activate. Current `dev` implements that capability-aware model; deployment on the physical router/VPS must still be validated separately from the software contract.

## User-confirmed dashboard data

The user has explicitly confirmed that the current real-device dashboard data for these areas is normal:

```text
Client IPv4
Access Endpoint
Internet Exit
WAN list
```

This closes the prior concern that the default IPv4 dashboard data itself was incorrect.

It does **not** by itself prove manual endpoint-selection persistence across refresh/reconnect.

## Real-device IPv4 Mapped lifecycle: PASS

The following path is real-hardware PASS on the current MT7981/fw3 device:

```text
CLOSED
-> mapper may remain active
-> exact STUN control remains available
-> mapped ingress is DROP
-> fresh external WireGuard handshake does not advance

Activate
-> real cellular IPv4 source is authorized
-> mapped ingress ACCEPT is source-scoped
-> fresh external WireGuard handshake succeeds

Internet Exit
-> router may become browser HTTP egress
-> router external/mapped address is suppressed as client-source evidence
-> the real authorized client source remains pinned

Close
-> Gate authorization is cleared
-> Internet Exit is cleared
-> mapper/STUN runtime may remain
-> mapped ingress returns to DROP
-> fresh WireGuard handshake no longer advances
```

The CLOSED test recorded packets on the mapped-ingress DROP rule, proving the blocked handshake reached the router and was stopped by Gate enforcement.

## PPPoE remap lifecycle: PASS

A representative hardware run changed PPPoE address, public Mapping and mapper ingress.

```text
Before reconnect:
pppoe-WAN IPv4      172.20.53.132
Mapped public       223.73.44.162:24948
Mapper ingress      53835

After reconnect:
pppoe-WAN IPv4      172.20.11.27
Mapped public       223.73.44.74:1625
Mapper ingress      54342
```

After bounded settle:

```text
new PPPoE session is UP
-> new Mapping exists
-> mapped ingress is protected
-> exact STUN control targets the new ingress
-> Gate remains CLOSED
-> no old source authorization migrated
-> Internet Exit remains inactive
```

After a fresh explicit Activate, the external WireGuard handshake succeeded through the new Mapping.

Therefore this complete path is PASS:

```text
PPPoE down/up
-> old mapping/session disappears
-> old authorization does not migrate
-> bounded settle
-> new Mapping rebuilds automatically
-> Gate stays CLOSED
-> user explicitly Activates
-> fresh external WireGuard handshake succeeds
```

A remap does not need to produce numerically different address/port values to be considered fresh; current runtime ownership is the authority.

## Current Mapped port interpretation

A current public Mapped endpoint may look like:

```text
public endpoint: <external_address>:<external_port>
WireGuard:       WG_HOME / UDP <service_port>
```

These ports are independent identities. The external Mapping port must never be treated as proof of the WireGuard listen port.

Current device fixtures/examples may still contain `51820`; future validation must include a non-51820 WireGuard listener so the dynamic service-port contract is exercised end-to-end.

## Real-device items still pending

Do not report PASS yet for:

```text
manual endpoint-selection persistence on the real device
IPv6 Gate after explicitly enabling it
same-WAN Dual data plane
split-WAN Dual data plane
independent per-family Internet Exit plans on hardware
IPv4 Access with IPv6-only/Dual Internet Exit on hardware
IPv6 Access with IPv4-only/Dual Internet Exit on hardware
Mapped Access on a real fw4/nftables router
non-51820 WireGuard service-port hardware path
```

Manual endpoint-selection persistence now has a software implementation and automated contract coverage on `dev`. The browser stores only non-authoritative plan hints and restores them through the current eligible Endpoint set. Exact Endpoint ids are preferred; after identity churn, current `dev` preserves manual intent with logical WAN plus Access Method rather than WAN alone, so a manually selected Mapped path cannot silently become Direct merely because both methods coexist on the same WAN. Dual preferences retain both family WANs and both family Access Methods and apply the same method-aware fallback. Invalid hints are discarded, legacy hints without method metadata retain the older compatibility fallback, and preference restoration never auto-Activates. The release browser regression now includes same-WAN Direct+Mapped ambiguity, Mapped id churn and Dual constituent-id churn while asserting zero Activate POSTs. Routine `dev` CI validates the static/contract boundary and browser-test syntax; the executable Playwright persistence regression remains in the `main`-only/manual release Browser Matrix, so this is **not** browser-matrix PASS on `dev` and remains **not** real-device PASS.

Dynamic WireGuard service-port handling now has explicit non-default automated coverage on `dev`: schema-3 Direct/Mapped endpoint and activation-command tests use UDP `41194`, while OpenWrt contract tests lock discovery through `wg show <name> listen-port`, Mapping propagation through `--service-port`, and Agent revalidation through the Service Registry. This is CI/contract evidence only; the real-device `WG_HOME / UDP 51820` path has not yet been changed to a non-51820 listener, so the hardware item remains pending.

Access family and Internet Exit family independence now has explicit software coverage on `dev`. Server tests already accept IPv4 Access with IPv6-only or split-Dual Exit plans; the browser regression additionally verifies the actual Activate payload for IPv4 Access -> IPv6-only/Dual Exit and IPv6 Access -> IPv4-only/Dual Exit, including independent `egress_wans.ipv4` / `egress_wans.ipv6` fields and no browser-supplied authorization source. Routine `dev` CI checks the browser-test syntax, while the executable Playwright regression remains wired to the `main`-only/manual release Browser Matrix. The corresponding hardware paths remain pending.

fw4/nftables Mapped restore now has an executable CI harness on `dev`, not only static source assertions. With fake `fw4`/`nft` commands and an isolated injected state directory, the real shell `restore` path is executed to verify that the current mapped `(ifname, ingress_port)` tuple, exact STUN control tuple and current mapped authorization source/device/port are rebuilt into nft set commands, while stale authorization and stale STUN tuples from a changed Mapping are discarded. This is software state-machine/command-generation evidence only; no real fw4/nftables router data plane has been validated, so the hardware item remains pending.

Dual/single-family Internet Exit runtime health checking now also has executable CI coverage. `sync_egress()` no longer treats the presence of any one fw4 egress comment as proof that the whole firewall runtime is healthy: every enabled family must retain its outbound rule, return rule and NAT/NAT66 rule. The fw3 path likewise verifies its family-specific forward/return rules, FORWARD/POSTROUTING jumps and MASQUERADE rule instead of checking only the filter-chain jump. An executable fake-fw4 regression proves that a complete Dual firewall remains active while a Dual runtime with only IPv6 NAT66 removed is detected as incomplete, the old state is cleared and the existing atomic rebuild/fail-closed path is entered. This is software evidence only; same-WAN/split-WAN Dual hardware data-plane validation remains pending.

Single-family Activate failure after Gate authorization now has executable Agent-level CI coverage. The regression runs the real `pull_once()` flow with a fake firewall that successfully authorizes IPv4 and a fake Internet Exit helper that then fails. The required sequence is verified as `firewall activate -> egress enable failure -> firewall clear + egress disable -> failure ACK`, with no success ACK. This closes the software bug where a failed Internet Exit activation could previously leave a single-family Gate authorization active, but it is not additional hardware validation.

Activate command expiry now has unified Server queue coverage for ACK-loss ambiguity. Any pending Activate that reaches its 60-second delivery deadline without an accepted ACK is treated as possibly executed on the router: the Server archives the old command and queues a Close with `rollback_for_command`, rather than allowing a replacement Activate. Dual commands additionally retain `rollback_for_batch` and discard the remaining batch tail. Late ACKs for the expired Activate cannot revive it, while an expired Close does not recursively create another Close. This is control-plane software evidence only; it does not add real-device validation.

Agent-side Activate delivery is executable-tested as an at-least-once, replay-safe transaction. Before Gate or Internet Exit side effects, the Agent writes a runtime `pending` command-result journal. A completed result is journaled before ACK. The regression suite proves that an initial success ACK returning HTTP 503 causes the next pull of the same command to replay the identical ACK without a second firewall Activate or egress enable; a same-id `pending` journal after interrupted execution causes only `firewall clear + egress disable + failure ACK`, never command re-execution; and an old journal from a different command is rolled back before a new Activate when the saved state is `pending` or even final `true`, because local success does not prove the Server accepted that ACK. Only a saved `false` result is known not to represent live authorization. This is executable software/CI evidence only and does not add any real-device PASS item.

Activate cleanup convergence now has executable coverage across both the Agent and Internet Exit helper. The Agent regression proves that clearing pre-existing egress happens only after the current Activate id is journaled as `pending`; an injected first `egress disable` failure prevents any firewall Activate, and a final failure ACK is emitted only after the rollback cleanup succeeds. The explicit Exit=`none` path is also exercised: old egress is cleared exactly once before Gate activation and no post-Activate duplicate disable is used. At the helper layer, fw3/fw4 firewall ownership and policy-routing state are re-read after deletion; incomplete cleanup returns nonzero and retains `wireguard-egress.conf` so a later pass can retry with the same runtime identity. The fake-fw4 harness models both successful deletion and a stuck deletion that must preserve state. This is executable software/CI evidence only and does not add real-device PASS.

Firewall authorization cleanup now also has executable fw3/fw4 retry coverage. The public `clear` command performs a conservative kernel authorization flush before and after the legacy state/rebuild path, verifies that per-family authorization state files are actually gone, and returns nonzero if any kernel auth-set flush or state convergence cannot be proven. The fw4 harness injects a first failure while clearing the source authorization set and verifies that source/ifname/ping-ifname/port authorization sets remain independently retryable even after the source state file has been removed; the fw3 harness exercises the same retry property for the ipset authorization set. This software evidence closes the helper-level false-success path used by Agent rollback, but it does not replace a real injected failure test on the physical router.

Close failure handling now also has explicit Server queue coverage. A `gate-close-failed` ACK keeps the same Close command pending, preserves its existing Close deadline, records the failed attempt and blocks new Activate commands. The same id remains pullable for another idempotent Close attempt; only a successful Close ACK makes the command terminal and clears the queue. This is software control-plane evidence only, not proof that a real router can recover from an injected firewall-clear failure.

## Implemented software model; hardware validation still pending

Current `dev` implements the documented architecture/UI rules below:

- no user-facing Private/CGNAT Access Endpoint;
- Internet Exit modes `none / ipv4 / ipv6 / dual` independent from Access Gate family;
- default exit mode follows Access family only as a recommendation;
- IPv6/Dual controls disabled when IPv6 Gate capability is unavailable;
- Dual PathCard uses two FamilyPathBlocks/four information lines without redundant `Split WAN` text;
- WireGuard `service_port` stays dynamically discovered.

These are implemented software/contract properties. They are **not** evidence that every corresponding path has already passed on the current physical router/VPS. Only the explicit real-device PASS sections above close hardware validation.

## Investigation notes

For recurring failure patterns, use `SYSTEMIC-INVARIANTS.md` instead of adding another device-specific copy here.

Device-specific reminders:

- use the bounded interface-up settle path before diagnosing PPPoE recovery;
- do not equate mapper active with Gate open;
- do not judge queued Activate from one immediate sample;
- do not treat request source after WG Internet Exit as unconditional client-source authority;
- only actual hardware evidence can close items in the pending list.
