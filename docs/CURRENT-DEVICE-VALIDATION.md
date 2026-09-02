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

Because IPv6 Gate is disabled, IPv6 Gate and Dual Gate are not real-device PASS. The approved UI contract is to expose the unavailable capability clearly but disable the action rather than allowing a user to enter a flow that cannot Activate. Implementation status must still be checked against current code; this document does not claim that UI change is already deployed.

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

## Approved design target that is not yet hardware validation

The next implementation is expected to follow these documented rules:

- no user-facing Private/CGNAT Access Endpoint;
- Internet Exit modes `none / ipv4 / ipv6 / dual` independent from Access Gate family;
- default exit mode follows Access family only as a recommendation;
- IPv6/Dual controls disabled when IPv6 Gate capability is unavailable;
- Dual PathCard uses two FamilyPathBlocks/four information lines without redundant `Split WAN` text;
- WireGuard `service_port` stays dynamically discovered.

These are approved architecture/UI targets. They are not evidence that the current deployed router/VPS already implements them.

## Investigation notes

For recurring failure patterns, use `SYSTEMIC-INVARIANTS.md` instead of adding another device-specific copy here.

Device-specific reminders:

- use the bounded interface-up settle path before diagnosing PPPoE recovery;
- do not equate mapper active with Gate open;
- do not judge queued Activate from one immediate sample;
- do not treat request source after WG Internet Exit as unconditional client-source authority;
- only actual hardware evidence can close items in the pending list.
