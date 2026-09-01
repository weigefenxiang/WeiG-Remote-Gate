# Architecture

```text
Cloudflare HTTPS
      |
      v
VPS control plane (loopback-only origin)
      ^
      |
      | outbound HTTPS
      |
OpenWrt agent
      |
      +-- Multi-WAN report
      +-- Direct endpoint discovery
      +-- Mapped Access engine
      +-- local Service Registry
      +-- Multi-WAN control path
      +-- router-local Gate firewall abstraction
      `-- optional runtime WireGuard Internet Exit
```

## Access Method model

Remote Gate describes how Internet traffic reaches a registered home service through an **Access Method**:

```text
Access Endpoint
    |
    +-- Direct
    +-- Mapped
    `-- Relay (future)
```

- **Direct** is public IPv4 or global IPv6 reaching the router directly.
- **Mapped** is a Remote Gate-owned NAT traversal path that maintains an Internet-facing mapping and relays authorized ingress to a locally registered service.
- **Relay** is reserved for a future Remote Gate relay path when direct or mapped access is unavailable.

NATMap is not a dependency, provider type or architectural layer. 0.3.17 owns its Mapping Engine and exposes the generic `Mapped` access method regardless of how the internal traversal implementation evolves.

## Four-layer separation

Ingress architecture is deliberately split into four independent concepts:

```text
Access Endpoint / Access Method
              |
              v
          Access Gate
              |
              v
       Service Adapter
              |
              v
        Local service
```

The responsibilities are:

1. **Access Endpoint**: where the client connects and whether the method is Direct, Mapped or Relay.
2. **Access Gate**: which external source is temporarily allowed to use that ingress and for what TTL.
3. **Service Adapter**: which locally discovered/registered service receives the authorized traffic.
4. **Local service**: WireGuard in 0.3.17; future adapters may include Shadowsocks, ShadowsocksR or other explicitly supported services.

Internet Exit is not part of these ingress layers. It remains an independent outbound feature.

## 0.3.17 Mapped Access path

0.3.17 first implements IPv4 UDP Mapped Access for WireGuard.

```text
Internet client
      |
      | UDP external_address:external_port
      v
ISP / CGNAT mapping
      |
      v
OpenWrt Mapping Engine ingress_port
      |
      | Access Gate: CLOSED / source ACL / TTL
      v
Remote Gate UDP relay
      |
      v
registered WireGuard service_port
      |
      v
WG_HOME -> private LAN
```

The Mapping Engine uses a dedicated local ingress socket rather than requiring the mapper and WireGuard to share the same listen port. This keeps the design compatible with 21.02-class Linux 5.4 systems and avoids relying on newer cross-process socket reuse behavior.

A mapped endpoint distinguishes:

```text
external_port  public NAT-mapped port
 ingress_port  router-local mapper port protected by Access Gate
 service_port  locally validated service listen port
```

For Direct WireGuard all three may be the same. For Mapped Access they may differ and must never be treated as interchangeable.

## Service Registry

The browser is not allowed to submit an arbitrary LAN target or target port.

OpenWrt owns a local Service Registry. A Service Adapter must discover or register a service locally and validate its transport, identity and listen port before that service can appear in an endpoint.

0.3.17 initially registers only WireGuard listeners discovered from local system state. Future Shadowsocks, ShadowsocksR or other adapters must use the same local-registration contract.

The server/browser selects a `service_id`; it does not gain authority to create an arbitrary `192.168.x.x:port` forward.

## Mapping Engine boundary

The Remote Gate Mapping Engine is intentionally narrower than a general-purpose port-mapping platform.

0.3.17 scope:

- IPv4;
- UDP;
- bind to a validated WAN/l3 device;
- public endpoint discovery through STUN-style binding;
- keepalive / mapping refresh;
- mapping-change detection;
- bounded per-client UDP relay state;
- idle timeout;
- sanitized status output;
- WAN reconnect recovery.

Not in 0.3.17:

- generic TCP proxying;
- arbitrary port forwards;
- HTTP/SSH/qBittorrent mapping;
- TURN;
- NATMap package/UCI management;
- user callback scripts;
- generic shell relay loops.

Future transport engines may add TCP or other mechanisms without changing the Direct / Mapped / Relay model.

## Firewall abstraction contract

`remote-gate-firewall.sh` exposes router-local Gate actions on both firewall generations.

The current WireGuard-port contract remains valid for Direct endpoints. Mapped Access extends the protected-port concept so the Gate can authorize a validated registered **ingress port**, while the Service Registry separately validates the target service port.

The interface continues to be backend-neutral:

```text
detect
install
sync ...
activate ...
verify-wireguard ...
clear
restore
status-json
uninstall
```

The agent does not need backend-specific logic. `verify-wireguard` remains a diagnostic action; normal Gate activation does not wait for a WireGuard handshake.

The 0.3.17 implementation must not let the browser invent an ingress port. Only locally registered Direct listeners or Mapping Engine ingress registrations may enter the protected policy.

## CLOSED invariant for Mapped Access

Maintaining a NAT mapping is not equivalent to opening the Gate.

```text
CLOSED
Internet -> public mapped endpoint -> ingress_port -> DROP

ACTIVE
approved source -> public mapped endpoint -> ingress_port -> mapper -> service

TTL / Close
public mapping may remain -> ingress_port -> DROP
```

This invariant is mandatory. A long-lived mapping is acceptable only while the Access Gate remains authoritative for source authorization.

## Exact STUN control path

The mapper must receive STUN replies on the same UDP socket that owns `ingress_port`. A generic mapped-ingress DROP would otherwise block the mapper's own discovery/keepalive traffic.

0.3.17 therefore treats STUN as a separate **control tuple**, not as user access:

```text
WAN device
+ ingress_port
+ resolved STUN IPv4
+ STUN source port
= exact control allow
```

The startup order is intentionally strict:

```text
resolve STUN peer
-> bind mapper ingress
-> publish prepared status + STUN tuple
-> synchronize firewall
-> install exact STUN control allow
-> install mapped-ingress DROP
-> create mapper go signal
-> perform STUN discovery
```

fw3 implements the control exception as an exact `device + source IPv4 + source port + destination ingress_port` ACCEPT before the mapped DROP. fw4 uses an `ifname . inet_service . ipv4_addr . inet_service` concatenated set before the mapped-ingress set.

The control exception is not a service bypass. The native mapper accepts control processing from the resolved STUN socket only, validates the current STUN transaction, and never relays packets from that STUN socket into the registered service. If the STUN tuple is missing or invalid, `prepared` never advances to `go`.

## Control-plane authorization flow

The authenticated browser chooses an IP family, endpoint and registered service, but it never supplies an arbitrary `source_ip`, WAN device, ingress port or service target as authority. The VPS resolves the selected source from the signed-in session source store, validates the endpoint server-side, and queues a short-lived command.

OpenWrt independently validates the family, selected WAN/device, registered ingress, local service identity, scope and TTL before creating temporary authorization.

IPv4 and IPv6 can be activated independently or queued together as a Dual transaction. A Dual request carries one validated endpoint per family. Both endpoints must resolve to the same registered WireGuard service, but they do not have to use the same WAN. If one family in a Dual batch fails, the remaining family is cancelled and any partial access is rolled back so a later success cannot mask the failure.

## Endpoint preference and Dual plans

The browser derives an automatic default from current endpoint capability; it must never hard-code a literal `WAN`, `WAN2`, interface address or device identity as the preferred path.

The default ordering is:

```text
IPv4
Public Direct -> Mapped -> observed NAT egress -> Private/CGNAT Try

IPv6
Global Direct on the preferred IPv4 WAN when available
-> otherwise the best Global Direct IPv6 endpoint

Dual
same-WAN Public IPv4 + Global IPv6
-> same-WAN Mapped IPv4 + Global IPv6
-> best IPv4 + best IPv6 across different WANs
```

A same-WAN Dual plan remains preferred when one WAN genuinely offers the best pair. When no suitable same-WAN pair exists, a split plan is valid, for example:

```text
IPv4 Access -> WAN-A
IPv6 Access -> WAN-B
```

Automatic endpoint state is marked `auto`. A user's explicit change is marked `manual` and is preserved while the selected intent is still available. If a dynamic endpoint disappears, the UI may re-resolve the same WAN intent or fall back to the current preferred endpoint, but it never creates a Gate authorization by itself.

Automatic selection is therefore convenience only. `Activate` remains the authority boundary.

## Concurrent sources

Each family may contain multiple concurrently authorized source addresses, each with its own absolute expiry. This allows a phone and a computer on different external networks to use the same service endpoint at the same time.

To keep the firewall rule model exact, concurrent records within one family must share the same WAN device, registered ingress port and access scope. Switching that profile requires closing the existing temporary access first.

## Gate and Internet Exit boundaries

The **Access Gate** is deliberately router-local. It owns only Remote Gate registered ingress traffic and optional Ping scope. It must not install generic FORWARD filtering or take ownership of unrelated forwarded applications.

The optional **Internet Exit** is a separate runtime-only data-plane feature implemented by `remote-gate-wireguard-egress.sh`. When the user enables Internet Exit, each active family has one explicitly validated egress WAN. A single-stack request therefore has one WAN; same-WAN Dual can share one WAN; split Dual can use different WANs for IPv4 and IPv6.

```text
WireGuard client subnet
        |
        +-- IPv4 policy routing -> selected IPv4 WAN
        +-- IPv6 policy routing -> selected IPv6 WAN
        +-- scoped FORWARD accept
        `-- scoped NAT44 / NAT66 masquerade
```

By default the browser aligns each Internet Exit family with the corresponding Access WAN. A manual exit choice remains possible where the selected WAN satisfies that family's egress requirements.

The egress helper does not create persistent UCI egress policy. Close, TTL expiry, explicit disable or reboot removes its temporary route rules, routing tables and firewall/NAT state. The helper also treats WAN/policy-route identity as runtime authority: if the selected WAN is no longer up/current, its L3 device changes, or the Remote Gate policy-table default route disappears, egress is cleared rather than silently falling back to a different main-table WAN.

This exception is intentionally narrow. qBittorrent, DHT/PeX, UPnP/NAT-PMP, DNAT/manual port forwards, forwarded NAS/PC services and unrelated router traffic remain under the router's existing policy.

## Related WeiG qB WebUI project

`weigefenxiang/WeiG-qB-WebUI` is a separate qBittorrent Alternate WebUI project. It owns qBittorrent WebAPI/version compatibility, application Logs/Search/RSS/Settings/Torrent UI and safe browser-side feature enhancement.

Remote Gate does not become a qB API compatibility layer or generic application proxy simply because both projects may be exposed through Cloudflare-managed infrastructure.

```text
Remote Gate control path
Browser -> Cloudflare -> Remote Gate control plane <-> OpenWrt agent
                                      |
                                      `-> router-local Access Gate

Mapped Access data path
Internet -> NAT mapping -> registered router ingress -> Access Gate -> Service Adapter

Optional WireGuard Internet Exit
WireGuard client -> WG interface -> temporary per-family PBR/FORWARD/NAT -> selected WAN(s)

WeiG qB WebUI
Browser -> application reverse proxy -> WeiG qB WebUI -> qB WebAPI -> qBittorrent
```

The firewall ownership remains intentionally separate:

```text
registered router-local ingress      -> Remote Gate Access Gate ownership
selected WG subnet Internet Exit     -> temporary scoped PBR/FORWARD/NAT ownership
forwarded qBittorrent traffic        -> existing router NAT/FORWARD ownership
```

See [`QB-WEBUI-BOUNDARY.md`](QB-WEBUI-BOUNDARY.md) for the cross-project contract. qB version/capability matrices belong in the qB WebUI repository and must not be duplicated here.

## Priority and timeout

The Gate guard executes before the normal established/related shortcut so expiration applies immediately to subsequent owned packets even when conntrack still has an older flow entry.

- fw3 inserts its Remote Gate guard at root INPUT position 1 and uses ipset source entries with independent timeouts.
- fw4 uses `chain-pre/input` and nftables timeout source sets.

Internet Exit has its own runtime TTL and reconciliation. It is not evidence that the Access Gate is open, and Access Gate authorization alone is not evidence that Internet Exit is active.

## WAN, service and endpoint synchronization

The agent discovers active WAN devices and eligible IPv4/IPv6 paths. The Service Registry discovers locally supported services. The Mapping Engine may register mapped ingresses for eligible services. Only validated values are synchronized into the firewall backend and inventory.

Ambiguous WAN/device association, unknown service identity, malformed mapper state or invalid ingress is fail-closed: that endpoint is omitted rather than guessed.

Interface-down re-synchronizes the protected Gate state immediately. Interface-up/update performs bounded settle re-synchronization so PPPoE/default-route inventory can converge without keeping an unbounded second state machine. A new Mapping may be discovered after the new WAN state settles, but old Gate authorization and Internet Exit authority are never migrated to a changed WAN/session automatically.

## Multi-WAN local return routing

Return-route state is maintained per authorized source, not merely per family. Each active IPv4 source can receive its own `/32` destination-specific router-local policy rule and each active IPv6 source its own `/128` rule when the selected WAN is not the ordinary reply path. Expiring one source removes only that source's route state.

This router-local ingress return routing is intentionally shared by Direct and Mapped access. Direct WireGuard replies and mapper-generated replies are both locally generated traffic destined for the authorized external source; the same per-source route contract keeps them on the WAN where the ingress arrived. This is separate from Internet Exit policy routing, which routes packets received from the WireGuard interface toward the selected Internet Exit WAN for that family.

## Firewall reload recovery

A firewall include runs the Gate backend `restore` action after a firewall rebuild. Protected device/ingress state is restored. Every still-valid authorization is restored only for its remaining absolute TTL.

Internet Exit remains runtime-only and is reconciled from its temporary state rather than committed as persistent firewall/network UCI configuration.

## Old OpenWrt compatibility

OpenWrt/ImmortalWrt 21.02-class fw3 systems remain supported.

The router is not expected to have a compiler. Mapped Access is therefore an optional runtime capability that depends on a compatible Remote Gate mapper binary being available for the device architecture. If the mapper is unavailable, the Agent, Direct endpoints, IPv6 Gate and Internet Exit continue to operate normally.

## Why there is no WAN HTTP probe

A browser cannot emit raw ICMP Echo. Creating a browser-accessible probe on the public WAN would require a responding service such as HTTP/HTTPS/WebSocket, which violates this project's threat model. The dashboard therefore reports authorization state and real runtime data without exposing a management service on the home WAN.

## Project rules

The non-negotiable development, security and compatibility rules are documented in [`PROJECT-RULES.md`](PROJECT-RULES.md). Architecture changes must update that contract before implementation when they alter an invariant.
