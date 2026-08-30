# WeiG-Remote-Gate

**Language:** [English](../README.md) · [简体中文](README.zh-CN.md)

**面向 OpenWrt / ImmortalWrt 的安全远程访问网关。**

WeiG-Remote-Gate 是一个通过 Cloudflare 暴露控制面的 Multi-WAN 状态与临时私有远程访问方案。家庭 WAN **不会**运行 HTTP/HTTPS 管理服务；OpenWrt 只通过出站 HTTPS 上报状态并拉取一次性命令。

## 安全目标

Remote Gate 只接管活动公网 WAN 上、发往路由器本机的两类流量：

```text
ICMP echo-request     -> 默认关闭
WireGuard UDP 端口    -> 默认关闭
```

用户在控制面完成登录并点击激活后，只有由服务器从可信 Cloudflare 请求路径推导出的当前客户端公网 IPv4，才会被临时允许：

```text
Ping 选中的公网 WAN IPv4
访问选中的 WireGuard UDP 监听端口
```

授权会在 1、5、15 或 30 分钟后自动过期。

## 不会一刀切封锁 WAN

Remote Gate 有意只工作在路由器的 **INPUT** 路径，不会向 `FORWARD` 安装过滤规则，也不会管理无关的 TCP/UDP 端口。

因此以下现有服务继续由原防火墙策略处理：

- qBittorrent / BitTorrent TCP 与 UDP
- DHT / PeX
- UPnP / NAT-PMP
- DNAT 与手工端口转发
- 转发到 NAS / PC 的服务
- 路由器本机其他无关端口

qBittorrent 的端口转发通常走 PREROUTING/DNAT + FORWARD，不会进入 Remote Gate 的 INPUT 防护链。

## 防火墙兼容性

OpenWrt 安装器会自动检测当前防火墙实现：

| 平台 | Remote Gate 后端 |
| --- | --- |
| firewall3 / `fw3` | `iptables` + `ipset` timeout |
| firewall4 / `fw4` | `nftables` timeout set |

用户不需要为了本项目主动迁移防火墙代际。不支持的系统会在安装阶段 fail closed。

已知目标示例：

- ImmortalWrt 21.02 / OpenWrt 21.02 类系统 -> fw3 后端
- 现代 OpenWrt / ImmortalWrt -> fw4 后端

## 规则优先级

Gate 防护规则会在普通 `ESTABLISHED,RELATED` 快捷放行之前执行。这样临时 WireGuard 授权一旦过期，后续匹配数据包会立即被阻断，而不会因为旧 conntrack 状态继续存活。

- fw3：`WEIG_REMOTE_GATE` 插入 `INPUT` 第 1 条。
- fw4：使用 `chain-pre/input`，位于 fw4 入站 conntrack 状态规则之前。

原有 UCI 规则（例如 `Allow-Ping`）**不会被删除**。Remote Gate 安装期间，由更靠前的 Gate 防护规则决定结果；卸载 Remote Gate 后恢复原防火墙行为。

## 架构

```text
Browser
   |
   | HTTPS
   v
Cloudflare
   |
   v
VPS / WeiG-Remote-Gate
仅监听 127.0.0.1:29444
   ^
   |
   | 出站 HTTPS report / status / pull / ack
   |
OpenWrt
   |
   +-- 自动检测防火墙后端
   |     +-- fw3 -> iptables + ipset
   |     `-- fw4 -> nftables
   +-- WireGuard 自动发现
   +-- 公网 WAN 自动发现
   `-- Multi-WAN 清单
```

Cloudflare 域名属于**控制面**。WireGuard 属于**数据面**，必须直接访问选定家庭 WAN 的公网 IPv4。不要把 WireGuard UDP Endpoint 指向 Cloudflare Tunnel 域名。

## Remote Gate 工作流程

1. 登录 Cloudflare 前置的控制面。
2. 服务器从可信 Cloudflare 请求路径推导客户端地址。
3. 选择已上报的公网 WAN、WireGuard 接口与 TTL。
4. VPS 生成短生命周期的一次性命令；浏览器不能自行提交任意授权 IP。
5. OpenWrt Agent 通过出站 HTTPS 拉取命令。
6. 防火墙后端只授权选中的 `(来源 IPv4, WAN 设备, WireGuard 端口)` 三元组。
7. 只有该来源能够临时访问 ICMP echo 与选定 WireGuard UDP 端口。
8. TTL 到期或点击 **Close now** 后，Gate 恢复关闭状态。

## 持续保护与防火墙重载

Agent 会持续同步：

- 当前活动公网 WAN 的 `l3_device`；
- 已配置以及当前正在监听的 WireGuard UDP 端口。

即使 WireGuard 接口尚未完全启动，只要 UCI 已配置监听端口，Remote Gate 也会提前保护该端口，从而在接口启动失败或 netifd 异常时保持公网 UDP fail closed。

项目会注册 firewall include，因此 firewall reload/restart 后会自动恢复 Gate 防护。只有尚未过期的授权状态会按剩余 TTL 恢复，已过期状态不会重新开放。

## OpenWrt / ImmortalWrt 21.02 的 WireGuard 注意事项

在部分 21.02 类系统中，新建 `proto='wireguard'` 的 UCI 接口后如果只执行：

```sh
/etc/init.d/network reload
```

新接口可能停留在类似下面的状态：

```text
proto: none
NO_DEVICE
```

即使 `/lib/netifd/proto/wireguard.sh` 已经存在。此时可能需要完整重启一次 network，让 netifd 正确注册并启动新协议接口：

```sh
/etc/init.d/network restart
```

该操作会短暂重连 WAN，因此不要在没有安全恢复路径的情况下远程执行。之后可用下面命令确认：

```sh
ifstatus <wireguard-interface>
wg show interfaces
wg show all listen-port
```

即使 WireGuard 接口本身尚未起来，Remote Gate 仍可根据已配置的监听端口提前保护对应公网 UDP 端口。

## UI

控制面遵循 `DESIGN.md`，支持：

- Auto / Light / Dark 外观；
- Auto 模式实时跟随系统主题；
- 避免暗色模式闪烁；
- 模块化 CSS 与 JavaScript；
- 桌面与移动端响应式布局；
- 克制的立体层次与语义动效。

## 当前版本

见 [`VERSION`](../VERSION)。

## 实机验证

fw3 后端已经在真实 ImmortalWrt 21.02 类路由器上完成端到端验证，环境包含 `iptables` legacy + `ipset`、PPPoE 公网 WAN、Cloudflare Tunnel 控制面以及路由器本机 WireGuard UDP 监听。

已验证流程：

```text
CLOSED
  -> 公网 ICMP echo 被阻断
  -> 公网 WireGuard UDP 被阻断

ACTIVATE
  -> 只有控制面推导出的当前 IPv4 被加入 timeout 授权集
  -> 来源限定 ICMP ACCEPT 位于通用 DROP 之前
  -> 来源限定 WireGuard UDP ACCEPT 位于通用 DROP 之前
  -> WireGuard 成功握手并产生真实数据流量

TTL EXPIRED
  -> 授权集合自动清空
  -> 来源限定 ACCEPT 规则消失
  -> ICMP 与 WireGuard UDP 恢复 DROP
  -> 重新发起 WireGuard 握手失败
```

同一轮验证中，Remote Gate 防护链始终只工作在 INPUT，没有接管 qBittorrent / UPnP / DNAT / FORWARD 的原有行为。

fw4/nftables 后端已经按相同安全模型实现，面向现代 OpenWrt/ImmortalWrt；上述真实硬件验证明确对应 fw3 路径。

## 生产环境验证

安装后先确认后端与状态：

```sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
```

fw3：

```sh
iptables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v4
iptables -S WEIG_REMOTE_GATE
```

fw4：

```sh
fw4 check
fw4 print | grep -n 'WeiG Remote Gate'
nft list set inet fw4 weig_remote_gate_protected_ifname
```

建议使用两个不同的外部公网 IPv4 测试：TTL 内只有被授权地址可以访问 ICMP/WireGuard，另一地址必须继续被阻断。TTL 结束后关闭并重新开启 WireGuard 客户端，确认无法产生新的握手。同时单独确认 qBittorrent 的监听/转发端口仍与安装前一样可达。

## 许可证

GPL-3.0-only。
