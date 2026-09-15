# Client Profiles

Status: software-complete scope for the `dev` line; real-router validation remains separate from CI evidence.

## Purpose

Client Profiles create and revoke **WeiG Remote Gate-owned WireGuard peers** without taking ownership of the user's WireGuard interface, existing peers, firewall zones, keys, routes, or unrelated services. Creating a Client Profile is configuration work only: it does **not** authorize WAN input and it does **not** activate the Access Gate.

The subsystem must continue to obey `docs/SYSTEMIC-INVARIANTS.md`, `docs/PROJECT-RULES.md`, `docs/ARCHITECTURE.md`, and `docs/SECURITY-MODEL.md`. Where this document is more specific, it narrows Client Profile behavior; it does not weaken the project-wide invariants.

## Authority and command flow

The browser may choose a currently advertised WireGuard endpoint, a profile name, a route preset (`home` or `full`), and a client keepalive value. The VPS resolves that endpoint from current normalized inventory/endpoints and queues a `profile_create` or `profile_revoke` command on the **same serialized Agent command queue** used by Gate control. There is no second state-changing command consumer and no inbound HTTP/HTTPS listener on OpenWrt.

OpenWrt remains runtime authority. Before applying a profile, it re-checks the registered WireGuard service identity and current listen port. Mapped IPv4 endpoints are refreshed from the current mapper state immediately before client configuration is generated. The exported endpoint is still a snapshot: later NAT mapping churn does not silently rewrite a configuration already delivered to a client.

## Ownership

Managed peers are persisted as UCI sections named `rgp_<profile-id>` with all of the following ownership evidence:

- section type `wireguard_<interface>`;
- description `remote-gate:<profile-id>`;
- the expected public key from Remote Gate metadata.

Revoke and uninstall must verify all ownership evidence before deleting the UCI peer. Any mismatch fails closed and leaves ambiguous user configuration untouched. The WireGuard interface itself is never deleted automatically by Client Profiles.

## Address allocation

The default IPv4 client pool is inferred from the selected WireGuard interface's first IPv4 prefix. An administrator may override it with `WG_PROFILE_IPV4_POOL`. Supported managed pools are `/20` through `/30`.

Allocation excludes the network address, broadcast address, all current addresses on the selected WireGuard interface, all current WireGuard IPv4 AllowedIPs (including broader CIDRs), and all existing Remote Gate-managed client addresses. Exhaustion is an error; the allocator never reuses a known-active address.

## Private-key lifecycle

The client private key is generated on OpenWrt. It is never written to Remote Gate persistent metadata, activity logs, `agent-status.json`, the VPS JSON store, or project backups.

The only intentional secret path is:

`OpenWrt wg genkey -> mode-0600 /tmp profile result -> authenticated Agent HTTPS -> VPS process memory -> authenticated download/copy/QR or one-time share URL -> client`

The OpenWrt `/tmp` result remains only until the VPS accepts the result and the Agent receives a successful command ACK, after which it is deleted. The VPS export object and one-time share tokens live only in process memory and expire (300 seconds by default, configurable from 60 to 1800 seconds). Restarting the VPS service intentionally destroys any unexported private key.

A recoverable export is bound to the authenticated browser session that requested creation. Closing or refreshing the page does not itself destroy that in-memory export: while the same authenticated session remains valid and the export TTL has not expired, **Recent results** may reopen it. Client IP is never used as export identity because NAT sharing and address churn make IP equality unsuitable as authorization. A new login session does not inherit another session's in-memory export.

Existing profiles therefore cannot be re-exported after the one-time secret window. To obtain a new private key, create a new profile and revoke the old one. Persistent history never changes that boundary.

## Non-secret history

The VPS may persist a bounded Client Profile history containing only non-secret creation metadata such as profile ID/name, WireGuard interface, managed client address, route mode, endpoint family/address/port, access method, keepalive and creation time. It must never contain the client private key, rendered configuration, WireGuard QR payload, one-time share token or share URL.

**Managed clients**, **Recent results**, and **History** are distinct views:

- Managed clients comes from fresh OpenWrt Agent status and describes peers that currently exist.
- Recent results is session-scoped process memory and describes exports that can still be opened before their TTL expires.
- History is persistent non-secret audit context and never implies that an old private key remains recoverable.

## Export formats

- **WireGuard**: standard `.conf`, suitable for official WireGuard clients. QR embeds the configuration directly and therefore contains the private key.
- **FlClash / Mihomo**: complete Clash-compatible YAML containing a WireGuard proxy and a small routing policy derived from the selected `home`/`full` preset.
- **NetProxy 8.1.0**: Clash-YAML node import. NetProxy 8.1.0 documents `netproxyctl node import <clash.yaml>`; Remote Gate does not claim authority over NetProxy's own routing, DNS, eBPF, or service policy.
- **sing-box**: modern WireGuard `endpoints` JSON. It is a transport fragment/config input, not an assertion that Remote Gate owns the rest of the user's sing-box policy.

For non-WireGuard QR export, the QR contains a short-lived one-time HTTPS URL rather than embedding a large configuration. The URL is consumed on first successful fetch. QR generation uses the optional VPS `qrencode` utility; Download and Copy remain available if `qrencode` is absent.

## Route presets

`home` exports the discovered/overridden home networks plus the WireGuard client network. `full` exports `0.0.0.0/0`. The managed client address is currently IPv4 even when the selected public endpoint transport is IPv6. This is intentional: endpoint transport family and tunnel payload/address family are separate concerns.

Neither preset changes the independent Internet Exit Plan. A Client Profile can exist while the Gate is closed and while optional WireGuard Internet egress is off.

## Browser behavior

The WireGuard card exposes **Manage clients**. Desktop uses a modal surface; narrow screens use a bottom sheet. The browser does not put profile secrets or export command IDs in Local Storage or Session Storage. Download/Copy/QR are explicit user actions during the export window. The dialog shows existing managed peers from fresh Agent status and can queue ownership-checked revocation.

**Recent results** is fetched from the authenticated VPS session and can reopen only still-live in-memory exports owned by that session. The adjacent History view is non-secret and may survive page refresh, browser restart and later login sessions.

QR display uses a viewport-level viewer mounted outside the scrolling Client Profiles sheet. On phones it fills the dynamic viewport, respects safe-area insets, and scales the complete QR image with its quiet zone inside the available width/height rather than clipping it inside the bottom sheet. WireGuard QR continues to carry the private key; non-WireGuard QR continues to carry only a one-time HTTPS URL.

## Validation boundary

CI can validate server rendering, queue serialization, shell syntax/contracts, browser layout/interaction, installer wiring, and secret non-persistence contracts. CI cannot prove a real router's UCI/WireGuard behavior, Android app import success, carrier NAT stability, or a live WireGuard handshake. Those remain hardware/device validation items in `docs/CURRENT-DEVICE-VALIDATION.md`.
