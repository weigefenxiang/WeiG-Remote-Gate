# AI Handoff

This file is a durable handoff for continuing 0.3.17 development without repeating already-closed investigations.

## Repository workflow

- Repository: `weigefenxiang/WeiG-Remote-Gate`
- Development branch: fixed `dev`
- Stable branch: `main`
- Never create feature/version/temporary branches for routine work.
- Commit messages are English-only.
- Do not expand scope into TCP, generic port forwarding, qBittorrent or unrelated SDK work unless a real regression requires it.
- Before editing, read `docs/PROJECT-RULES.md`, `docs/CURRENT-DEVICE-VALIDATION.md`, `docs/ARCHITECTURE.md` and `docs/SECURITY-MODEL.md`.

The runtime code baseline immediately before this docs-only handoff was:

```text
a842de1df88468de93d1a3e40ad6c4e31be1b325
```

Always query the current `dev` HEAD before writing because later docs/test commits may be newer while runtime code is unchanged.

## Current real-device target

```text
ImmortalWrt 21.02-SNAPSHOT
mediatek/mt7981
aarch64_cortex-a53
Linux 5.4.x
fw3 + iptables legacy + ipset
WG_HOME / UDP 51820
```

Observed topology is dynamic. Do not encode these names as policy:

```text
WAN  / pppoe-WAN   -> private/CGNAT upstream; Mapped candidate
WAN2 / pppoe-WAN2  -> public IPv4; Direct candidate
```

Another router can assign these capabilities to different logical WANs.

## Hardware-validated IPv4 Mapped lifecycle

The following is real-device PASS, not merely CI:

```text
CLOSED
-> mapper may remain active
-> mapped ingress is DROP
-> fresh external WireGuard handshake does not advance

Activate
-> real cellular IPv4 source is authorized
-> Mapped ingress ACCEPT is source-scoped
-> fresh WireGuard handshake succeeds

Internet Exit
-> dashboard traffic may return through the home router
-> router external/mapped address is suppressed as client-source evidence
-> active real client source remains pinned

Close
-> all Gate authorization is cleared
-> Internet Exit is cleared
-> mapper/STUN control may remain
-> fresh handshake is blocked again
```

## Hardware-validated PPPoE remap lifecycle

Representative test:

```text
Before:
pppoe-WAN     172.20.53.132
public Mapping 223.73.44.162:24948
local ingress 53835

After PPPoE reconnect:
pppoe-WAN     172.20.11.27
public Mapping 223.73.44.74:1625
local ingress 54342
```

After the bounded settle sequence, `active_mappings=1`, the new ingress was protected, Gate stayed CLOSED and Internet Exit stayed inactive. After a fresh explicit Activate, WireGuard `latest-handshake` advanced from `1788280607` to `1788287352`, and the new ingress ACCEPT rule carried real packets.

Therefore this complete path is PASS:

```text
PPPoE down/up
-> old Mapping disappears
-> old authorization does not migrate
-> WAN/default route settles
-> new Mapping is rebuilt automatically
-> Gate remains CLOSED
-> fresh explicit Activate
-> fresh external WireGuard handshake succeeds through the new Mapping
```

## Important implemented fixes

Do not regress these:

- IPv4-first family preference while IPv6 remains selectable.
- Explicit CLOSE clears Gate authorization and Internet Exit but does not need to stop the mapper.
- Kernel-enforced TTL for authorization.
- Interface-down policy resync and bounded interface-up settle (`0s -> 2s -> 5s -> 10s`).
- Mapping changes revoke old authorization instead of migrating it.
- Stale mapper status is rejected unless the managed mapper process is current.
- Orphan mapper runtimes are cleaned safely by exact process ownership.
- Router egress/mapped public addresses are suppressed as client-source evidence.
- The currently authorized client source is pinned while Gate is active.
- Browser candidate submissions equal to router egress are explicitly rejected.
- Endpoint defaults are capability-based: Public Direct IPv4 before Mapped; IPv6 prefers the same best IPv4 WAN when possible.
- Automatic endpoint selection is marked `auto`; explicit user choice is `manual`.
- Dual prefers same-WAN public IPv4 + global IPv6, then same-WAN Mapped IPv4 + IPv6, then split WAN.
- Split Dual carries `egress_wan_ipv4` and `egress_wan_ipv6`; same-WAN/legacy `egress_wan` remains compatible.
- OpenWrt split Dual egress is one transaction, not two independent enable calls.
- Partial Dual failures roll back temporary authorization/egress fail-closed.
- Internet Exit sync validates selected WAN/L3/main default route/Remote Gate policy-table default route; stale routing clears egress instead of falling through to `main`.
- Browser CI no longer runs Playwright `--with-deps`, avoiding slow Ubuntu APT/Azure mirror downloads.

## Recurring investigation mistakes

1. Do not call PPPoE address/mapped-port changes a bug. Old connectivity is expected to die; test automatic remap and fail-closed behavior.
2. Do not inspect immediately after `ifup`. Give netifd/ubus/routes/mapper/firewall the settle window.
3. Do not equate Mapping existence with Gate authorization.
4. Do not conclude Activate failed from one immediate `active=false` sample; command polling/ACK may lag the click.
5. Do not use the current HTTP request source blindly once WG Internet Exit is active; it can be the router's own public address.
6. Do not interpret the source attached to a Close request as the authorization source.
7. Do not confuse Access Endpoint (ingress) with Internet Exit (egress).
8. Do not hardcode `WAN`/`WAN2` or a known public address.
9. Do not force Dual onto one WAN; split Dual is valid when families live on different WANs.
10. Do not let split egress fall through to an arbitrary main-table WAN after route loss.
11. Do not migrate authorization to a new mapper ingress after PPPoE/remap changes.
12. Do not require a remap tuple to be numerically different; the same tuple can be reassigned.
13. Do not inspect only `server/app/main.py` for all routes; `server/remote-gate.py` extends the handler.
14. Do not trust mapper JSON without managed-process ownership/currentness.
15. Do not create a second endpoint preference engine while `endpointScore()` is the shared ordering primitive.
16. Do not use old CI red runs as blockers when current HEAD is green.

## Current automated validation

Current CI covers:

- Python unit/contracts
- Python compile
- BusyBox/POSIX shell syntax
- native mapper host build/check
- JavaScript syntax
- browser layout regression
- same-WAN automatic endpoint defaults
- split-WAN Dual browser regression and activate payload
- split Dual server/agent/runtime contracts
- egress policy-route fail-closed contract

Always validate the current `dev` HEAD rather than historical workflow failures.

## Remaining real-device work

Next priority is not more PPPoE mapping work; that path is already PASS.

Continue with:

```text
1. Close Gate and disable phone WireGuard.
2. Refresh the real dashboard without touching endpoint controls.
3. Verify IPv4 automatically chooses the real Public Direct WAN and Internet Exit follows that WAN.
4. Verify manual endpoint selection remains respected.
5. When ready, explicitly enable/test IPv6 Gate on hardware.
6. Validate same-WAN Dual data plane.
7. Validate split-WAN Dual and per-family Internet Exit on hardware.
8. Later validate Mapped Access on a real fw4/nftables router.
```

Do not report IPv6/same-WAN Dual/split-WAN Dual as real-device PASS until those tests are actually performed.

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

The VPS updater freezes a deployment to one resolved commit SHA. Do not assume a same-version deployment is current without checking `/usr/local/lib/remote-gate/BUILD`.
