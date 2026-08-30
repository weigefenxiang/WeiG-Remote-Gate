# WeiG-Remote-Gate

**Secure Remote Access Gateway for OpenWrt.**

WeiG-Remote-Gate evolves the WAN inventory and private IPv4 vault ideas from WeiG-WAN2-Vault into a Cloudflare-fronted remote access control plane.

The home WAN remains closed by default:

```text
TCP 80/443/22  -> existing firewall policy (normally DROP on WAN)
ICMP echo      -> DROP unless temporarily authorized
WireGuard UDP  -> DROP unless temporarily authorized
```

The dashboard never exposes an HTTP/HTTPS probe on the home public IPv4. The browser reaches the VPS through Cloudflare, while OpenWrt only makes outbound HTTPS requests to report status, pull one-time commands and acknowledge execution.

## Architecture

```text
Browser
   |
   | HTTPS
   v
Cloudflare
   |
   v
VPS / WeiG-Remote-Gate
127.0.0.1:29444 only
   ^
   |
   | outbound HTTPS report / pull / ack
   |
OpenWrt
   |
   +-- firewall4 / nftables timeout sets
   +-- WireGuard status
   +-- Multi-WAN inventory
```

## Remote Gate flow

1. Sign in to the Cloudflare-fronted dashboard.
2. The server derives the current client IP from `CF-Connecting-IP`.
3. Choose a reported **public** WAN and a reported WireGuard interface.
4. Click **Activate**.
5. The VPS queues a short-lived one-time command. The browser cannot submit an arbitrary authorization IP.
6. The OpenWrt agent pulls the command over outbound HTTPS.
7. OpenWrt temporarily adds the client IPv4, WAN device and WireGuard UDP port to nftables timeout sets.
8. Only that temporary combination is accepted in the WAN input path for ICMP echo and WireGuard UDP.
9. The authorization expires automatically. The UI can also queue an immediate close command.

## UI

The UI follows `DESIGN.md` and supports:
- Auto / Light / Dark appearance
- live operating-system theme changes in Auto mode
- no dark-mode flash
- modular CSS and JavaScript
- responsive desktop/mobile layouts
- restrained 3D depth and semantic motion

## Current stage

`0.1.x` is the first modular foundation. It includes:
- a localhost-only Python control plane
- login/session/CSRF foundations
- Multi-WAN update and inventory APIs
- Remote Gate command queue
- agent pull/ack/status APIs
- dashboard and design system
- OpenWrt report/agent/firewall scripts

Before production use, validate the nftables include paths and rule rendering on the exact OpenWrt/firewall4 version used by the router.

## Security invariants

- Server refuses non-loopback bind addresses.
- WAN-side HTTP/HTTPS service is not part of the design.
- Gate source IP is server-derived, not browser-supplied.
- Only reported public WANs can be selected.
- Only agent-reported WireGuard interfaces can be selected.
- Commands have IDs, expiry and single-use acknowledgement state.
- Secrets are stored outside the repository.

See `SECURITY.md` and `docs/SECURITY-MODEL.md`.

## License

GPL-3.0-only.
