# Security Policy

WeiG-Remote-Gate controls temporary WAN firewall access. Treat configuration files, authentication data, agent tokens and WireGuard private keys as secrets.

## Security invariants

- The VPS application must bind only to loopback.
- The public site should be exposed through Cloudflare Tunnel or a hardened reverse proxy.
- The home WAN must not expose a management HTTP/HTTPS listener for this project.
- `CF-Connecting-IP` is accepted only on requests that already arrive through the trusted Cloudflare-facing deployment path.
- The browser cannot specify the source IP to authorize.
- Gate commands expire and are acknowledged once.
- OpenWrt applies temporary membership to nftables sets with timeouts.
- No WireGuard private key is uploaded to the server.

## Reporting vulnerabilities

Do not open a public issue containing tokens, passwords, real WAN IP history, session cookies, private keys or complete production configuration. Remove secrets from logs and reproduction steps.
