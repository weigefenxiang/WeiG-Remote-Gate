# Cloudflare Tunnel

WeiG Remote Gate keeps the VPS application on loopback and publishes only the normal control hostname through Cloudflare Tunnel.

## Required ingress

Use one public hostname, for example:

```text
notify.example.com -> http://127.0.0.1:29444
```

The Remote Gate process must remain bound to `127.0.0.1` (or `::1`). Do not expose TCP/29444 directly to the Internet.

## Client source discovery

Remote Gate does **not** require `v4.<hostname>`, `v6.<hostname>`, a DNS-only origin record, a second TLS listener, or Cloudflare per-record IPv4/IPv6 filtering.

The normal Cloudflare request source is stored as a **verified** source for that address family. If the browser is missing IPv4 or IPv6, the UI may query the corresponding public IP echo endpoint and submit the result only as a **candidate**:

- IPv4: `https://api.ipify.org?format=json`
- IPv6: `https://api6.ipify.org?format=json`

Candidate addresses do not directly authorize the firewall. OpenWrt opens a short WireGuard-only verification window and promotes only the source observed from fresh authenticated WireGuard peer activity. If the HTTP candidate and WireGuard UDP egress differ, a short discovery window lets WireGuard determine the actual endpoint.

## DNS privacy

There is no need to create a DNS-only A record pointing at the VPS for source discovery. Keeping the control hostname proxied through Cloudflare Tunnel avoids publishing the VPS origin IP through Remote Gate DNS configuration.

## Headers

The server trusts `CF-Connecting-IP` only on the normal Cloudflare control path. Browser-provided candidate data is tagged as candidate and must pass WireGuard verification before it becomes firewall authorization.

## Security boundary

Remote Gate controls only router-local `INPUT` for discovered WireGuard UDP ports and optional ICMP echo. It does not manage `FORWARD`, DNAT, UPnP, NAT-PMP, or unrelated application forwarding such as qBittorrent.
