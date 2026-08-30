# OpenWrt / ImmortalWrt installation

## Supported firewall generations

WeiG-Remote-Gate auto-detects one of:

### firewall3

Required:

```text
fw3
iptables
ipset
iptables set match (xt_set / kmod-ipt-ipset)
```

Typical examples include OpenWrt/ImmortalWrt 21.02-era firmware.

### firewall4

Required:

```text
fw4
nft
firewall4 automatic nft includes
```

Modern OpenWrt/ImmortalWrt normally uses this backend.

Common requirements:

```text
curl
ubus
jsonfilter
uci
ip
awk/sed/grep/sort
```

`wg` from wireguard-tools is needed for WireGuard discovery. If no WireGuard interface is currently listening, Remote Gate still protects ICMP on public WANs and automatically begins protecting WireGuard when an interface appears.

## Install

```sh
wget -O /tmp/remote-gate-install.sh \
  https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main/openwrt/install.sh

sh /tmp/remote-gate-install.sh
```

The installer asks for:

- public dashboard hostname;
- VPS-generated `WRITE_TOKEN`.

It prints the detected firewall backend before making the Gate active.

## Traffic boundary

Remote Gate owns only:

```text
public WAN -> router INPUT -> ICMP echo
public WAN -> router INPUT -> discovered WireGuard UDP ports
```

It does **not** modify `FORWARD`. qBittorrent/BT, UPnP, NAT-PMP and DNAT/port-forward traffic therefore stays on the original firewall path.

## Validation: firewall3

```sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
iptables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v4
```

Expected first custom INPUT rule:

```text
-A INPUT -j WEIG_REMOTE_GATE
```

The dedicated chain must contain only ICMP echo and UDP rules for protected WireGuard ports, followed by RETURN.

## Validation: firewall4

```sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
fw4 check
fw4 print | grep -n 'WeiG Remote Gate'
nft list set inet fw4 weig_remote_gate_protected_ifname
nft list set inet fw4 weig_remote_gate_protected_udp_port
```

The Remote Gate rules must render before fw4's `Handle inbound flows` conntrack rule.

## Existing Allow-Ping rule

Remote Gate does not delete the user's UCI `Allow-Ping` rule. Its earlier INPUT guard blocks unauthorized echo requests before that rule is reached. Uninstalling Remote Gate restores the original behavior.

## Firewall reload

A persistent firewall include runs the lightweight `restore` action after firewall rebuilds. It restores protected WAN/WireGuard policy and restores an active authorization only for the remaining TTL.
