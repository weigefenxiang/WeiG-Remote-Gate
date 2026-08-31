# WeiG qB WebUI Integration Boundary

This document records the ownership boundary between **WeiG-Remote-Gate** and **WeiG-qB-WebUI**.

Repositories:

- Remote access / router Gate: `weigefenxiang/WeiG-Remote-Gate`
- qBittorrent Alternate WebUI: `weigefenxiang/WeiG-qB-WebUI`

## 1. They are separate products

```text
Remote administration path

Browser
  ↓ HTTPS
Cloudflare
  ↓
WeiG-Remote-Gate control plane
  ↕ outbound HTTPS
OpenWrt agent
  ↓
router-local INPUT Gate for Ping / WireGuard


qBittorrent application path

Browser
  ↓ HTTPS / deployment-specific reverse proxy
WeiG-qB-WebUI
  ↓ qB WebAPI
qBittorrent
```

The two projects may be deployed on infrastructure owned by the same user, but they do not share feature ownership.

## 2. Remote Gate owns

- authenticated Gate control-plane requests;
- browser source observation / carrier-probe source records;
- Multi-WAN endpoint inventory;
- temporary source-specific Ping / WireGuard authorization;
- fw3/fw4 INPUT firewall objects owned by Remote Gate;
- OpenWrt agent pull / ACK transport.

Remote Gate does **not** own qBittorrent WebAPI version compatibility, qB settings, qB logs, Torrent UI state or qB feature emulation.

## 3. WeiG qB WebUI owns

- qBittorrent Alternate WebUI presentation;
- qB WebAPI compatibility from the supported 4.x floor through modern 5.x;
- old/new API semantic bridges;
- qB Logs, Search, RSS, Settings, Torrent detail and transfer UI;
- safe JS enhancements when an older qB backend exposes enough data;
- capability gating when an older backend cannot provide the required data/write API.

The qB WebUI compatibility matrix belongs in the qB WebUI repository and must not be duplicated here.

## 4. Firewall boundary remains unchanged

Remote Gate is deliberately INPUT-only. A normally forwarded qBittorrent TCP/UDP service follows the router's existing NAT/FORWARD policy and must not be captured by Remote Gate rules.

```text
router-local Ping / WireGuard UDP → Remote Gate INPUT ownership
forwarded qBittorrent traffic     → existing NAT/FORWARD ownership
```

This separation is a security invariant, not only a documentation convention.

## 5. Deployment rule

If WeiG qB WebUI is published through a Cloudflare hostname or another reverse proxy, that application endpoint remains a separate service. Do not reinterpret the Remote Gate control-plane hostname as a generic application proxy, and do not point the WireGuard UDP data-plane endpoint at a Cloudflare Tunnel hostname.

## 6. Cross-project documentation rule

When a change affects both projects:

1. document qB version/API/UI behavior in `WeiG-qB-WebUI`;
2. document only the network/security ownership boundary in `WeiG-Remote-Gate`;
3. avoid copying qB capability tables into Remote Gate docs;
4. preserve the INPUT-only firewall invariant.
