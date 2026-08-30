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

The browser submits only:

- selected reported public WAN name;
- selected agent-reported WireGuard interface;
- one fixed TTL.

The source IPv4 is server-derived. The OpenWrt agent accepts an activation only when the selected WAN device is in the locally synchronized public-WAN protection set and the selected UDP port is a locally discovered WireGuard listen port.

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

Uninstall removes only Remote Gate's chain/set/include objects. It does not delete the user's Allow-Ping, qBittorrent, UPnP, DNAT or other UCI firewall configuration.
