# Architecture

WeiG-Remote-Gate separates the public control plane from the home WAN data plane.

```text
Browser
  -> Cloudflare HTTPS
  -> VPS localhost service
  <- OpenWrt outbound HTTPS report / agent pull / ack
  -> OpenWrt firewall4/nftables timeout sets
  -> WireGuard
```

## Control plane

The Python service binds to `127.0.0.1:29444` only.

It stores:
- WAN inventory and last report
- agent-reported WireGuard status
- one pending Gate command
- recent security activity
- hashed web sessions

It never stores a WireGuard private key.

## OpenWrt agent

The agent:
- reports WAN inventory every 5 minutes only when network inventory changes
- posts WireGuard/firewall status
- polls for a single pending command
- executes `activate` or `close`
- acknowledges the command once

The agent is outbound-only.

## firewall4 integration

WeiG-Remote-Gate uses firewall4 automatic nft includes:

```text
/usr/share/nftables.d/table-pre/
  90-weig-remote-gate-sets.nft

/usr/share/nftables.d/chain-pre/input_wan/
  90-weig-remote-gate.nft
```

The first file defines timeout-capable sets. The second inserts the temporary ICMP and WireGuard UDP accepts at the beginning of `input_wan`, before the normal WAN drop/reject path.

v0.1 supports one active authorization at a time. Activating a new client flushes the previous temporary set members before inserting the new source IPv4, WAN device and UDP port.

## Why there is no WAN HTTP probe

A browser cannot emit raw ICMP Echo. Creating a browser-accessible probe on the public WAN would require a responding service such as HTTP/HTTPS/WebSocket, which violates this project's threat model. The dashboard therefore reports authorization state and real WireGuard handshake data instead of presenting a fake browser "ping".
