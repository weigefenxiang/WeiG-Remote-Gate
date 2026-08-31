# Cloudflare Tunnel

Recommended path:

```text
remote.example.com
  -> Cloudflare
  -> cloudflared
  -> http://127.0.0.1:29444
```

The application expects the Cloudflare-facing deployment path to preserve `CF-Connecting-IP`.

Important:
- keep the application on loopback;
- do not point the tunnel at a home WAN HTTP service;
- protect the hostname with appropriate Cloudflare account and access controls in addition to the application's own login;
- use HTTPS between the browser and Cloudflare.

The OpenWrt agent also reaches the public hostname over outbound HTTPS.

## Verified dual-stack client source observers

A browser may reach the control page over IPv6 even though the same phone also has a usable carrier IPv4 path. Remote Gate must learn that IPv4 address without trusting a browser-supplied `source_ip`.

For a control hostname such as:

```text
remote.example.com
```

create two additional Cloudflare-proxied hostnames routed through the **same Cloudflare Tunnel** to the same loopback service:

```text
v4.remote.example.com -> http://127.0.0.1:29444
v6.remote.example.com -> http://127.0.0.1:29444
```

Configure the DNS records so that:

- `v4.remote.example.com` has the Cloudflare proxied-record setting `ipv4_only=true`;
- `v6.remote.example.com` has the Cloudflare proxied-record setting `ipv6_only=true`.

Cloudflare documents these per-record settings for proxied DNS records. They make the v4 observer publish only A records and the v6 observer publish only AAAA records.

The observer hostnames are derived automatically from the configured public hostname. No VPS config migration is required.

### Trust flow

```text
authenticated browser on remote.example.com
  -> GET /api/v1/client-source/challenge?family=ipv4
  -> short-lived signed one-time token
  -> script request to v4.remote.example.com
  -> Cloudflare observes the request source
  -> VPS reads CF-Connecting-IP
  -> token is checked against the live login session
  -> verified IPv4 source stored for that session
```

IPv6 follows the same path through `v6.remote.example.com`.

The browser never sends an IP address in the observer request. The legacy `/api/v1/client-source/probe` address-submission endpoint is fail-closed and returns HTTP 410.

Observer tokens:
- are HMAC-signed by the VPS session secret;
- are tied to the authenticated session hash and one IP family;
- expire after 90 seconds;
- are one-time-use;
- are accepted only on the matching v4/v6 observer hostname;
- require the referenced login session to still be active.

If either observer DNS/tunnel hostname is missing or misconfigured, that family simply remains unavailable for Gate activation. Remote Gate does not fall back to trusting an address reported by JavaScript.

## Cloudflare Tunnel routing

All three public hostnames can point at the same local service:

```text
remote.example.com
v4.remote.example.com
v6.remote.example.com
        |
        v
http://127.0.0.1:29444
```

Only the main hostname exposes the login/dashboard/control API. Observer hostnames accept only the one-time source-observation endpoint; other paths return 404.
