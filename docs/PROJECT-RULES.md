# Project Rules

These rules are the hard engineering contract for WeiG-Remote-Gate. New features must preserve them unless the project explicitly revises this document first.

## Branch and version workflow

- Routine development, fixes, tests and CI use the single fixed `dev` branch.
- `main` is the validated stable branch.
- Do not create `dev/*`, `feature/*`, version-number branches or temporary long-lived development branches.
- The software version lives in `VERSION` and in software-visible version metadata, not in branch names.
- Commit messages are written in English.
- Promotion to `main` happens only after Core CI, Browser CI and required hardware validation pass.
- Never force-overwrite an unknown `main`-only commit.

## 0.3.17 product direction

0.3.17 introduces Remote Gate-owned **Mapped Access**. NATMap is not a dependency, product concept, provider name or required package.

The user-facing Access Methods are:

```text
Direct
Mapped
Relay   (future)
```

Their meanings are:

- **Direct**: the Internet can reach a router endpoint directly through public IPv4 or global IPv6.
- **Mapped**: Remote Gate establishes and maintains an Internet-facing NAT mapping and routes authorized ingress to a registered local service.
- **Relay**: a future Remote Gate relay path when direct or mapped access is unavailable.

The implementation may evolve internally without changing these user-facing concepts.

## Layering contract

Remote Gate keeps four layers separate:

```text
Access Endpoint
    |
    +-- Direct
    +-- Mapped
    `-- Relay (future)
            |
            v
       Access Gate
            |
            v
     Service Adapter
            |
            +-- WireGuard        (0.3.17)
            +-- Shadowsocks      (future)
            +-- ShadowsocksR     (future)
            `-- other adapters   (future)
```

Rules:

- Access Method answers **how Internet traffic reaches the router**.
- Access Gate answers **which external source may use that ingress and for how long**.
- Service Adapter answers **which locally registered service receives the authorized traffic**.
- Internet Exit remains a separate outbound feature and must never be merged into ingress mapping logic.

## Service Registry security rule

The browser and VPS must never be able to invent an arbitrary LAN target or target port.

A service must first be discovered or registered locally on OpenWrt and independently validated there. An endpoint refers to a local `service_id`; it does not grant the browser authority to submit `192.168.x.x:port`, shell commands or arbitrary forwarding rules.

0.3.17 initially registers only validated WireGuard listeners. Future Shadowsocks, ShadowsocksR or other adapters must follow the same local-registration rule.

## Mapped Access scope for 0.3.17

0.3.17 intentionally starts small:

- IPv4 NAT traversal only.
- UDP transport only.
- WireGuard service adapter only.
- Dedicated local ingress port; do not require sharing the WireGuard listen socket.
- STUN-style public endpoint discovery and mapping refresh.
- Mapping-change detection.
- Bounded UDP relay/session state.
- Multi-WAN binding to one validated logical WAN + l3 device.
- Status output that contains no secrets.

0.3.17 does not add:

- generic TCP proxying;
- arbitrary port-forwarding UI;
- HTTP/SSH/qBittorrent mapping;
- TURN server;
- generic proxy platform;
- NATMap package management;
- NATMap UCI management;
- user script callbacks;
- shell `eval` or runtime command construction from untrusted values.

Future transport engines may add TCP or other mechanisms behind the same Access Method / Service Adapter contract.

## Access Gate invariant

Mapped Access does not mean permanently open access.

A public mapping may exist continuously, but when the Gate is CLOSED the mapped ingress must remain unusable by unapproved Internet sources.

```text
CLOSED
Internet -> mapped public endpoint -> router ingress -> DROP

ACTIVE
approved source -> mapped public endpoint -> router ingress -> service adapter

TTL / Close
mapping may remain -> router ingress -> DROP
```

The firewall must authorize the actual **ingress port**, not merely the service's target port.

## Endpoint port model

Mapped endpoints distinguish three ports:

- `external_port`: public NAT-mapped port seen on the Internet.
- `ingress_port`: router-local port owned by the mapping engine and protected by the Access Gate.
- `service_port`: validated local service listen port, initially the WireGuard listen port.

For Direct WireGuard these values may be identical. For Mapped Access they are allowed to differ.

Do not collapse these meanings back into one ambiguous `local_port` field in new schema/code.

## Fail-closed rules

Mapping/endpoint creation must be rejected or ignored when any required identity is ambiguous, including:

- unknown or down WAN;
- ambiguous logical WAN/l3 device association;
- invalid or special-use public address;
- invalid port;
- unsupported transport;
- unknown service;
- unvalidated service target;
- missing mapper runtime;
- malformed or stale mapper state.

An unavailable optional mapping capability is not a dashboard error. Direct, IPv6 and existing Remote Gate features must continue to work.

## Old OpenWrt compatibility

OpenWrt/ImmortalWrt 21.02-class fw3 systems remain a supported baseline.

- Do not assume Linux 5.6+ socket-sharing behavior.
- Do not require a compiler on the router.
- Do not make a third-party NAT traversal package a hard dependency.
- If no compatible Remote Gate mapper binary is available for the router architecture, Mapped Access stays unavailable while all existing features continue normally.

## Firewall ownership

Access Gate owns only Remote Gate registered router-local ingress plus optional Echo Request scope. It must not become a generic firewall manager.

Internet Exit may own only its existing temporary WireGuard-subnet PBR/FORWARD/NAT44/NAT66 path.

Do not take ownership of unrelated:

- LAN forwarding;
- qBittorrent/DHT/PeX;
- UPnP/NAT-PMP;
- user DNAT/SNAT;
- NAS/PC services;
- arbitrary TCP/UDP ports.

## Mapper implementation rules

The Remote Gate mapping helper should be implemented as a small auditable native component rather than a long-running shell relay loop.

It must:

- treat runtime/network values as data only;
- avoid `eval` and `sh -c` on runtime values;
- bound session counts and memory;
- expire idle sessions;
- validate addresses and ports;
- avoid logging tokens, credentials, private keys or complete sensitive command lines;
- expose only sanitized status;
- survive WAN reconnect and mapping changes without crashing the Agent;
- run with the minimum practical privileges.

The mapper must remain transport/service agnostic above its UDP relay layer. It must not implement WireGuard cryptography or parse application secrets.

## Compatibility and regression rule

Do not break already validated behavior while adding Mapped Access:

- IPv4 / IPv6 / Dual Access Gate;
- Multi-WAN;
- WAN return routing;
- WireGuard Internet Exit;
- NAT44/NAT66;
- fw3 xtables wait handling;
- fw4 nftables behavior;
- endpoint manual-selection memory;
- stale UI Error handling;
- Internet Exit default following the Access Endpoint WAN until manually overridden.

Every new 0.3.17 change must add focused automated coverage and preserve the existing CI contract.
