# OpenWrt / LEDE / ImmortalWrt installation

WeiG-Remote-Gate uses **capability detection**, not a firmware-version allowlist. OpenWrt, LEDE, ImmortalWrt and compatible derivatives are accepted when they provide the required OpenWrt-family runtime interfaces.

## Core runtime requirements

Required for the control plane and agent:

```text
/bin/sh (BusyBox ash compatible)
rc.common + procd
curl
ubus
jsonfilter
uci
ip
awk
sed
grep
sort
```

`wg` from wireguard-tools is needed for WireGuard service discovery. If no WireGuard interface is currently listening, no WireGuard service endpoint is registered until one appears.

The installer does not require Python, Node.js, systemd or a compiler on the router.

## Package-manager generations

Package management is treated as platform metadata rather than a runtime firewall dependency:

```text
Older OpenWrt / LEDE / ImmortalWrt -> usually opkg
OpenWrt 25.12+                     -> apk
```

`remote-gate-platform.sh` reports the actual package manager and exact Package ABI. The mapper must not be selected from `uname -m` alone.

Check the platform before or after installation with:

```sh
/usr/lib/remote-gate/remote-gate-platform.sh summary
```

Typical fields include:

```text
Distribution
Release
Target
Package manager
Package ABI
Kernel machine
libc
Init
Firewall generation
Core runtime
```

## Supported firewall capabilities

WeiG-Remote-Gate auto-detects one of the following stacks.

### firewall3

Required:

```text
fw3
iptables
ipset
iptables set match (xt_set / kmod-ipt-ipset)
```

This path intentionally remains supported for older OpenWrt/LEDE/ImmortalWrt derivatives. It is not restricted to one named release.

### firewall4

Required:

```text
fw4
nft
firewall4 automatic nft includes
```

Modern OpenWrt/ImmortalWrt normally uses this backend.

The installer does not ask the user to migrate between fw3 and fw4.

## Optional capability degradation

Remote Gate avoids making one optional feature a requirement for the whole installation:

- no IPv6 firewall capability -> IPv6 Gate unavailable, IPv4 remains functional;
- no compatible native mapper -> Mapped Access unavailable, Direct remains functional;
- no suitable Internet Exit prerequisites -> Internet Exit unavailable, Access Gate remains functional;
- no WireGuard listener -> no WireGuard service is registered until one appears.

A missing **core** runtime requirement fails installation explicitly instead of creating an unsafe partial core.

## Install

```sh
wget -O /tmp/remote-gate-install.sh \
  https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main/openwrt/install.sh

sh /tmp/remote-gate-install.sh
```

The installer asks for:

- public dashboard hostname;
- VPS-generated `WRITE_TOKEN`.

It prints the detected distribution/release metadata, package manager, Package ABI, kernel machine and firewall backend.

## Native mapper ABI

The router is not expected to compile `remote-gate-mapper`.

The authoritative selector is the OpenWrt **Package ABI**, obtained in this order when available:

1. OpenWrt/ubus release architecture metadata;
2. `DISTRIB_ARCH`;
3. `apk --print-arch` on apk-based systems;
4. highest-priority real architecture from `opkg print-architecture`.

`uname -m` is diagnostic information only. It is too broad to safely distinguish many OpenWrt MIPS/ARM ABI variants.

Run:

```sh
/usr/lib/remote-gate/remote-gate-audit.sh
```

before choosing or reporting a mapper binary. If the exact ABI is unknown or no matching binary is published, Mapped Access stays unavailable rather than installing a guessed executable.

## Traffic boundary

Remote Gate owns only:

```text
protected WAN -> router INPUT -> optional ICMP echo
protected WAN -> router INPUT -> registered Direct UDP service ingress
protected WAN -> router INPUT -> exact Mapped device+ingress_port
protected WAN -> router INPUT -> exact mapper STUN control tuple
```

It does **not** become a generic FORWARD firewall. qBittorrent/BT, UPnP, NAT-PMP and ordinary DNAT/port-forward traffic remain on the original firewall path.

## Mapped Access startup order

Mapped Access preserves CLOSED protection before it attempts STUN discovery:

```text
resolve STUN peer
-> bind mapper ingress socket
-> publish prepared state
-> sync exact device+ingress DROP
-> sync exact STUN control allow
-> create go signal
-> perform STUN discovery
```

The exact STUN exception is limited to:

```text
WAN device + ingress_port + STUN IPv4 + STUN source port
```

All other unapproved Internet sources remain blocked by the mapped ingress Gate.

## Validation: firewall3

```sh
/usr/lib/remote-gate/remote-gate-platform.sh summary
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
iptables -S INPUT | sed -n '1,12p'
ipset list weig_remote_gate_auth_v4
```

Expected first custom INPUT rule:

```text
-A INPUT -j WEIG_REMOTE_GATE
```

The dedicated chain may contain verification/auth rules, exact Mapped STUN control allows, exact Mapped ingress drops and protected Direct/Ping rules, followed by RETURN.

## Validation: firewall4

```sh
/usr/lib/remote-gate/remote-gate-platform.sh summary
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
fw4 check
fw4 print | grep -n 'WeiG Remote Gate'
nft list set inet fw4 weig_remote_gate_protected_ifname_v4
nft list set inet fw4 weig_remote_gate_protected_udp_port
nft list set inet fw4 weig_remote_gate_mapped_ingress_v4
nft list set inet fw4 weig_remote_gate_mapped_control_v4
```

The Remote Gate rules must render before fw4's normal established/related shortcut.

## Existing Allow-Ping rule

Remote Gate does not delete the user's UCI `Allow-Ping` rule. Its earlier INPUT guard blocks unauthorized owned Echo Request traffic before that rule is reached. Uninstalling Remote Gate restores the original behavior.

## Firewall reload

A persistent firewall include runs the lightweight `restore` action after firewall rebuilds. It restores protected WAN/Direct/Mapped policy and restores active authorizations only for their remaining TTL.

## Compatibility expectations

The project deliberately avoids statements such as “only OpenWrt 21.02 is supported.” An older LEDE/OpenWrt derivative can be compatible when it carries the required capabilities, while a heavily modified newer firmware can still be incompatible if a required firewall/runtime primitive has been removed.

The practical compatibility rule is therefore:

```text
compatible capabilities -> run
missing optional capability -> degrade that feature
missing required safe core/firewall capability -> fail explicitly
unknown brand/version alone -> never reject
```
