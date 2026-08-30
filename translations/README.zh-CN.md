# WeiG-Remote-Gate

**Language:** [English](../README.md) · [简体中文](README.zh-CN.md)

**面向 OpenWrt / ImmortalWrt 的安全远程访问网关。**

WeiG-Remote-Gate 是一个通过 Cloudflare 暴露控制面的 Multi-WAN 状态与临时私有远程访问方案。家庭 WAN **不会**运行 HTTP/HTTPS 管理服务；OpenWrt 只通过出站 HTTPS 上报 Inventory / Status 并拉取短生命周期命令。

## 安全目标

Remote Gate 只接管受保护 WAN Endpoint 上、发往路由器本机的两类流量：

```text
ICMP / ICMPv6 Echo Request   -> 默认关闭
WireGuard UDP 监听端口       -> 默认关闭
```

用户登录并激活后，VPS 只会选择同一已认证 Browser Session 最近通过可信 Cloudflare 请求路径观察到的来源地址。Browser 不能自行提交任意授权 IP。

临时授权严格限定为：

```text
(IP Family + 精确来源 IP + WAN device + WireGuard UDP port)
```

提供两种 Access Scope：

- **仅 WireGuard** —— 推荐，Ping 继续保持关闭；
- **WireGuard + Ping** —— 同时允许该授权来源发送 Echo Request。

授权会在 1、5、15 或 30 分钟后自动过期，也可以主动 Close。

## 不会一刀切封锁 WAN

Remote Gate 有意只工作在路由器的 **INPUT** 路径，不会向 `FORWARD` 安装过滤规则，不接管 NAT，也不会管理无关 TCP/UDP 端口。

因此以下服务继续由原 Firewall policy 处理：

- qBittorrent / BitTorrent TCP 与 UDP；
- DHT / PeX；
- UPnP / NAT-PMP；
- DNAT 与手工端口转发；
- 转发到 NAS / PC 的服务；
- 路由器本机其他无关端口。

qBittorrent 端口转发通常走 PREROUTING/DNAT + FORWARD，不会进入 Remote Gate 的 INPUT 防护链。

## Firewall 兼容性

OpenWrt 安装器会自动检测当前 Firewall 实现：

| 平台 | Remote Gate Backend |
| --- | --- |
| firewall3 / `fw3` | `iptables` + `ipset` timeout |
| firewall4 / `fw4` | `nftables` timeout sets |

不支持的系统会在安装阶段 fail closed。用户不需要为了本项目主动迁移 Firewall 代际。

已知目标类别：

- ImmortalWrt / OpenWrt 21.02 类系统 -> fw3 Backend；
- 现代 OpenWrt / ImmortalWrt -> fw4 Backend。

### 规则优先级

Gate 防护规则会在普通 `ESTABLISHED,RELATED` 快捷放行之前执行，避免临时 WireGuard 授权过期后仍因旧 conntrack 状态继续存活。

- fw3：IPv4 `WEIG_REMOTE_GATE` 插入 `INPUT` 第 1 条；只有存在 IPv6 protected-device policy 时才挂载 IPv6 Guard。
- fw4：使用 `chain-pre/input`，位于 fw4 入站 conntrack 状态规则之前。

原有 UCI 规则（例如 `Allow-Ping`）**不会被删除**。Remote Gate 安装期间，只对自己接管的流量由更靠前的 Gate 规则决定结果；卸载后恢复原 Firewall 行为。

IPv6 路径只控制 Echo Request 与选定的路由器本机 WireGuard UDP port。Neighbor Discovery、Router Advertisement、Packet Too Big 以及其他 ICMPv6 控制流量继续交给原 Firewall policy。

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
   | 出站 HTTPS inventory / status / pull / ack
   |
OpenWrt
   |
   +-- fw3 / fw4 Firewall Backend
   +-- IPv4 / IPv6 WAN Inventory
   +-- WireGuard 自动发现
   +-- Multi-WAN Control Path 选择
   `-- 可选 Runtime Capability 发现
```

Cloudflare 域名属于**控制面**。WireGuard 属于**数据面**，必须直接访问选定的家庭 Endpoint。不要把 WireGuard UDP Endpoint 指向 Cloudflare Tunnel 域名。

## v0.3 Endpoint 与 Source 模型

v0.3 使用 Schema 2 Endpoint model，不再假定只有一个 IPv4 WAN。

Native Endpoint 可以是：

- 活动 WAN 上可直接到达的 Public IPv4；
- 活动 WAN 上可直接到达的 Global IPv6，前提是本机 Firewall Backend 报告 IPv6 Gate capability。

VPS 会按**已认证 Browser Session**分别保存最近观察到的 IPv4 与 IPv6 来源。选择 IPv4 必须有仍有效的可信 IPv4 observation；选择 IPv6 必须有仍有效的可信 IPv6 observation。Browser 本地仅用于显示的旧 IP 永远不会被拿来做授权。

OpenWrt Control Agent 可以在 Multi-WAN 的健康 IPv4 / IPv6 default-route candidate 之间选择出站 HTTPS 控制路径。这个控制路径与用户选择的 WireGuard 数据面 Endpoint 相互独立。

### NATMap 状态

Schema 与 Server Endpoint builder 已理解 mapped IPv4 Endpoint provider，但 Remote Gate **不会安装或依赖 NATMap**。当前面向 21.02 的兼容路径不会在没有受支持 discovery 实现的情况下主动宣称存在 mapped endpoint。

Read-only Audit 可以读取已有 `/var/run/natmap/*.json` Runtime Status，但不会打印 NATMap 配置内容，也不会读取或输出 Remote Gate Secret。没有 NATMap 是正常状态，不影响 Native IPv4 / IPv6 使用。

## Remote Gate 工作流程

1. 登录 Cloudflare 前置的 Dashboard。
2. Server 从可信 Cloudflare 请求路径观察当前来源，并与该已认证 Session 绑定。
3. 选择 IPv4 或 IPv6、可用 Access Endpoint、WireGuard Interface、Access Scope 与 TTL。
4. VPS 在 Server 端重新解析 Endpoint，并生成短生命周期一次性命令。Browser 不会提供可信 Authorization IP、WAN device 或 WireGuard port。
5. OpenWrt Agent 通过出站 HTTPS 拉取命令。
6. Firewall Backend 再次确认 WAN device 与 WireGuard port 当前确实属于受保护 Policy，然后只授权精确来源 tuple。
7. Agent ACK 命令；存在未过期 Pending Command 时，第二个 Activate / Close 不会静默覆盖前一个命令。
8. TTL 到期或点击 **Close now** 后，Gate 恢复关闭状态。

## 持续保护与 Firewall reload

Agent 会持续同步活动 WAN device，以及已配置/正在监听的 WireGuard UDP port。即使 WireGuard Interface 暂时未起来，已配置 listen port 仍可保持 fail closed。

项目会注册 Firewall Include，因此 Firewall reload/restart 后会自动恢复 Gate 防护。只有尚未过期的 Authorization 会按剩余 TTL 恢复，过期状态不会重新开放。

当 `GATE_IPV6=disabled`，或当前没有任何 IPv6 protected device 时，fw3 会移除闲置 IPv6 INPUT jump，而不是一直挂着空 Guard Chain。

## OpenWrt / ImmortalWrt 21.02 的 WireGuard 注意事项

在部分 21.02 类系统中，新建 `proto='wireguard'` 的 UCI Interface 后如果只执行：

```sh
/etc/init.d/network reload
```

Interface 可能停留在 `proto: none` / `NO_DEVICE` 状态，即使 `/lib/netifd/proto/wireguard.sh` 已存在。此时可能需要完整重启一次 Network：

```sh
/etc/init.d/network restart
```

该操作会短暂重连 WAN，因此不要在没有恢复路径的情况下远程执行。之后可验证：

```sh
ifstatus <wireguard-interface>
wg show interfaces
wg show all listen-port
```

## Adaptive Dashboard Workspace

Dashboard 源码以 English 为基准，同时支持自动简体中文和手动语言切换。

当前 UI 包括：

- Auto / Light / Dark Appearance；Mobile 常用入口只保留紧凑 Theme button，低频设置进入 Utility Sheet；
- Desktop 使用自适应 Main Canvas + Utility Rail，System 与 Activity 放在同一侧栏，不再浪费整行；
- Desktop Arrange mode 与 Browser-local Layout Preference；
- Mobile 固定 Card 顺序并关闭拖拉，避免影响 Touch Scroll；
- IPv4 / IPv6 Client Source 分开显示；
- IPv6 完整保持单行，并根据宽度动态缩小字体；
- Endpoint、Family、Scope 与 TTL 均由实际 Capability 驱动；
- Activity 默认一条事件一行，可展开查看细节；
- CLOSED Gate Orb 与 Activate Button 共用同一套 Eligibility 与 Action Path。

Browser 本地 UI Preference 不属于安全授权依据。

## 更新已有 VPS

### v0.2.x -> v0.3 首次升级

第一次从 v0.2.x 升到 v0.3 时，**不要直接依赖旧版已安装 updater**。旧 updater 的固定文件清单早于 Schema 2 新模块。应从目标 Release 下载新的 updater 作为 bootstrap：

```bash
curl -fsSL \
  https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main/server/update.sh \
  -o /tmp/remote-gate-update.sh

bash -n /tmp/remote-gate-update.sh
bash /tmp/remote-gate-update.sh
```

Updater 会保留原 hostname、登录凭据、`WRITE_TOKEN`、Session 与 State，在 `/var/backups/weig-remote-gate/` 创建 Rollback Backup，重启仅监听 localhost 的服务，检查 `/healthz` 与 Agent API；失败时自动恢复旧 Application。

从 v0.3 开始，Updater 会被正式安装并在后续升级中保留：

```bash
/usr/local/lib/remote-gate/update.sh
```

因此以后可以直接使用本机 updater。

## 更新已有 OpenWrt

旧版本可能还没有 `/usr/lib/remote-gate/update.sh`。第一次升级时，同样应从目标 Release 下载新的 OpenWrt updater 并运行临时副本。升级到 v0.3 后，Updater、Uninstaller 与 Read-only Audit 都会进入正式生命周期并在后续更新中保留。

OpenWrt updater 会备份 Application / Config / State，并保存 Firewall / Network Snapshot 供恢复；保留现有 WireGuard 配置；替换前检查 Shell Syntax；只重建 Remote Gate 自己拥有的 INPUT Object；确认 `ready=true` 后才启动 Agent。

## 当前版本

见 [`VERSION`](../VERSION)。在 VPS staging 与真实路由器最终验证完成前，Development Build 继续标记为 `0.3.0-dev`。

## 验证状态

### 已完成真实硬件验证

fw3 IPv4 路径已经在真实 ImmortalWrt 21.02 类路由器上完成端到端验证，环境包含 `iptables` legacy + `ipset`、PPPoE Public WAN、Cloudflare Tunnel Control Plane，以及路由器本机 WireGuard UDP listener。

已验证流程：

```text
CLOSED
  -> Public IPv4 ICMP Echo 被阻断
  -> Public WireGuard UDP 被阻断

ACTIVATE
  -> 只有 Dashboard 推导出的可信 IPv4 进入 Timeout Authorization
  -> 来源限定 ACCEPT 位于通用 DROP 之前
  -> WireGuard 成功 Handshake 并产生真实流量

TTL EXPIRED
  -> Authorization 自动消失
  -> ICMP 与 WireGuard UDP 恢复 DROP
  -> 无法建立新的 WireGuard Handshake
```

同一轮验证中，Gate 始终只工作在 INPUT，没有接管 qBittorrent / UPnP / DNAT / FORWARD 原有行为。

### 已实现并通过 CI，但仍待最终实机验证

v0.3 已实现对应 IPv6 Gate path，包括精确 IPv6 source authorization、仅控制 Echo Request 的 ICMPv6 规则、IPv6 WireGuard UDP protection、空 IPv6 policy jump 清理，以及 IPv4 / IPv6 Multi-WAN Control Transport。这些路径已有自动化测试、Syntax CI 与 Browser Regression 覆盖，但**尚未在 21.02 fw3 实机上宣布完成新的 IPv6 Data Plane 硬件验证**。

fw4/nftables Backend 也按照同一 Security Model 实现，但同样不属于上面已经完成的 fw3 实机验证范围。

## 生产环境验证

先运行 Read-only Audit 和 Firewall State：

```sh
/usr/lib/remote-gate/remote-gate-audit.sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
```

fw3 IPv4：

```sh
iptables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v4
iptables -S WEIG_REMOTE_GATE
```

fw3 IPv6（启用时）：

```sh
ip6tables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v6
ip6tables -S WEIG_REMOTE_GATE_V6
```

fw4：

```sh
fw4 check
fw4 print | grep -n 'WeiG Remote Gate'
nft list set inet fw4 weig_remote_gate_protected_ifname_v4
nft list set inet fw4 weig_remote_gate_protected_ifname_v6
```

每个测试 Family 都应确认：TTL 内只有被授权的外部来源可以访问选定 WireGuard Endpoint；TTL 结束后重新发起的新 Handshake 必须失败。同时单独确认 qBittorrent 的监听/转发 Port 与升级前一样可达。

## License

GPL-3.0-only。
