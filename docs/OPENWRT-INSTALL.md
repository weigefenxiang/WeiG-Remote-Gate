# OpenWrt installation

Requirements:
- firewall4 / `fw4`
- `nft`
- `curl`
- `ubus`
- `jsonfilter`
- standard BusyBox tools
- `wg` from wireguard-tools for WireGuard status and Gate selection

Install:

```sh
sh openwrt/install.sh
```

The installer asks for:
- public dashboard hostname
- VPS-generated `WRITE_TOKEN`

Default network discovery mode is `auto`.

Installed runtime files:

```text
/etc/remote-gate.conf
/usr/lib/remote-gate/remote-gate-report.sh
/usr/lib/remote-gate/remote-gate-agent.sh
/usr/lib/remote-gate/remote-gate-firewall.sh
/etc/init.d/remote-gate-agent
```

The WAN report runs every five minutes, but only submits WAN update data when interface IP/device state changes. The agent loop defaults to 10 seconds for command/status exchange.

## Firewall validation

After installation:

```sh
fw4 check
fw4 print | grep -n 'WeiG Remote Gate'
nft list set inet fw4 weig_remote_gate_ipv4
```

The sets should be empty until a Gate activation is authorized.
