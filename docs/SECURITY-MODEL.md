# Security model

## Default state

The WAN hosts no WeiG-Remote-Gate HTTP/HTTPS service.

On every active public WAN, the firewall guard protects:

- ICMP echo-request;
- every locally discovered WireGuard UDP listen port.

Unauthorized matching traffic is dropped before the normal firewall established/related shortcut.

All other traffic falls through to the original firewall unchanged.

## qBittorrent / BT isolation

Remote Gate never installs rules in `FORWARD`. A typical qBittorrent inbound connection follows:

```text
WAN -> PREROUTING/DNAT or UPnP -> FORWARD -> LAN host
```

Remote Gate follows:

```text
WAN -> INPUT -> router-local ICMP/WireGuard
```

The two paths are intentionally separate.

## Gate activation

The browser submits only control intent:

- selected reported endpoint / WAN;
- selected agent-reported WireGuard interface;
- selected IPv4 or IPv6 family;
- access scope;
- TTL.

The browser never submits the authorization `source_ip`.

The request family observed directly by Cloudflare is recorded from `CF-Connecting-IP`. When the browser has a usable second family, Remote Gate uses a family-specific Cloudflare observer hostname (`v4.<public-host>` or `v6.<public-host>`) plus a signed one-time token. The observer request contains no address value; the VPS records only the `CF-Connecting-IP` that Cloudflare actually saw on that request.

Legacy browser-reported address probes are disabled and fail closed.

Observer tokens are:
- HMAC-signed with the VPS session secret;
- bound to the authenticated session hash and one address family;
- short-lived;
- one-time-use;
- valid only on the matching family-specific observer hostname;
- rejected after logout/session expiry.

The OpenWrt agent accepts an activation only when the selected WAN device is in the locally synchronized protection set and the selected UDP port is a locally discovered WireGuard listen port.

## Multi-WAN WireGuard return path

An authorized WireGuard initiation can arrive on a non-default WAN while the router's normal local-output route points elsewhere. During an active authorization, Remote Gate pins only router-local return traffic to the authorized client host address through the selected WAN policy table.

The pin is dynamic:
- no WAN name or WireGuard listen port is hard-coded;
- an existing per-WAN policy table is reused when available;
- otherwise a Remote Gate-owned destination-only table is used;
- Close, expiry, authorization replacement and service stop remove the managed rule;
- WAN interface updates resynchronize it.

This does not alter `FORWARD` or the router-wide default route.

## Backend parity

### fw3

- root `INPUT` jumps to `WEIG_REMOTE_GATE` at position 1;
- ipset contains the authorized source with timeout;
- tuple-specific ACCEPT rules precede generic protected ICMP/WireGuard DROP rules;
- final RETURN hands unrelated INPUT traffic back to fw3.

### fw4

- automatic nft includes define protected/auth sets;
- `chain-pre/input` rules run before inbound conntrack state acceptance;
- auth source uses a timeout element;
- unrelated traffic continues through normal fw4 rules.

## Firewall reload and reboot

Protected devices/ports and the authorization expiry timestamp are kept in local state. A firewall include restores the guard after a firewall rebuild. Expired authorization state is discarded instead of being reopened.

## Uninstall

Uninstall removes only Remote Gate's chain/set/include/managed-return-route objects. It does not delete the user's Allow-Ping, qBittorrent, UPnP, DNAT or other UCI firewall configuration.
