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
- keep the application on loopback
- do not point the tunnel at a home WAN HTTP service
- protect the hostname with appropriate Cloudflare account and access controls in addition to the application's own login
- use HTTPS between the browser and Cloudflare

The OpenWrt agent also reaches the public hostname over outbound HTTPS.
