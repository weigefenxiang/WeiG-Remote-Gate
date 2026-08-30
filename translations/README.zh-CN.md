# WeiG-Remote-Gate

**Language:** [English](../README.md) · [简体中文](README.zh-CN.md)

**面向 OpenWrt / ImmortalWrt 的安全远程访问网关。**

WeiG-Remote-Gate 是一个通过 Cloudflare 前置的 Multi-WAN 状态与临时私有远程访问控制面。家庭 WAN **不会**运行 HTTP/HTTPS 管理服务；OpenWrt 只通过出站 HTTPS 上报 Inventory / Status，并拉取短生命周期命令。

## 安全边界与流量归属

Remote Gate 只接管受保护 WAN Endpoint 上、发往路由器本机的两类流量：

```text
ICMP / ICMPv6 Echo Request   -> 默认关闭
WireGuard UDP 监听端口       -> 默认关闭
```

它只工作在路由器的 **INPUT** 路径，不会向 `FORWARD` 安装过滤规则，不接管 NAT，也不会管理无关 TCP/UDP 端口。因此 qBittorrent、DHT / PeX、UPnP / NAT-PMP、DNAT / 手工端口转发，以及转发到 NAS / PC 的服务继续由原 Firewall Policy 处理。

提供两种 Access Scope：

- **仅 WireGuard** —— 推荐，Ping 继续关闭；
- **WireGuard + Ping** —— 同时允许该授权来源发送 Echo Request。

IPv6 路径只控制 Echo Request 与选定的路由器本机 WireGuard UDP Port。NDP、Router Advertisement、Packet Too Big 和其他 ICMPv6 控制流量继续交给原 Firewall Policy。

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

Cloudflare 域名属于**控制面**。WireGuard 属于**数据面**，必须直接访问选定的家庭 Endpoint。不要把 Cloudflare Tunnel 域名作为 WireGuard UDP Endpoint。

## Firewall 兼容性

| 平台 | Remote Gate Backend |
| --- | --- |
| firewall3 / `fw3` | `iptables` + `ipset` timeout |
| firewall4 / `fw4` | `nftables` timeout sets |

Gate Guard 会在普通 `ESTABLISHED,RELATED` 快捷放行之前执行。原有 UCI 规则（例如 `Allow-Ping`）不会被删除；只有 Remote Gate 接管的流量由更靠前的 Guard 决定，卸载后恢复原 Firewall 行为。

已知目标包括 ImmortalWrt / OpenWrt 21.02 类 fw3 系统，以及现代 fw4 系统。无法识别的 Backend 在安装阶段 fail closed。

## Schema 2 Multi-WAN Endpoint 模型

Server 不再假定只有一个 Public IPv4 WAN。Endpoint 可以是：

- Public IPv4 `Direct`；
- 启用 IPv6 Gate Capability 时的 Global IPv6 `Direct`；
- 由受支持 Provider 提供的 NATMap / Mapped IPv4；
- 每条 WAN 实测得到的 IPv4 `NAT egress · Try`；
- 供手工实验使用的 Private / CGNAT IPv4 `Try`。

Direct / Mapped Path 会优先推荐。Private / CGNAT 地址不会被错误描述为“公网可达”；但仍允许选择，因为上游 Mapping、NATMap 或运营商特殊网络可能让该 Path 实际可用。

OpenWrt Agent 会持续推导受保护 IPv4 Device、符合条件的 IPv6 Device，以及发现到的 WireGuard Listen Port。如果临时 Authorization 对应的 WAN Device 或 WireGuard Port 离开当前 Policy，即使 TTL 尚未结束，也会立即撤销授权。

## 双栈 Client Source

IPv4 与 IPv6 是同一已认证 Browser Session 下的**独立记录**。学习到一个 Family 绝不会删除另一个 Family。

Source 优先级：

1. **Cloudflare Observation (`verified`)** —— 当前请求的 `CF-Connecting-IP`；
2. **Network Probe (`heuristic`)** —— 某个 Family 缺失时使用的短生命周期补充来源。

v0.3.1 会独立探测缺失 Family：

- IPv4：IPv4-only `api.ipify.org`，适合手机 Carrier NAT / CGNAT / NAT64 / 464XLAT 场景；
- IPv6：IPv6-only `api6.ipify.org`，适合 Dashboard 当前通过 IPv4 到达 Cloudflare、但设备本身同时具备可用 IPv6 的情况。

Browser 只把 Probe 结果提交给受 Session + CSRF 保护的 Endpoint。之后若 Cloudflare 对同一 Family 获得直接 Observation，则会自动替换 heuristic 记录。普通 Activate 请求仍不会把任意 Raw Authorization IP 作为权威输入；VPS 会从 Session Source Store 解析所选 Family。

当 IPv4 / IPv6 都可用时，UI **默认推荐 IPv4**，但不是锁死。用户手动选择 IPv6 后，只要 IPv6 仍可用，后续刷新就会保留该手动选择，不会自动抢回 IPv4。

## v0.3.1 触感交互系统

Dashboard 遵循 [`DESIGN.md`](../DESIGN.md) 的统一设计系统。视觉改动以 `awesome-design-md` 的层级、间距、Elevation、Motion 与 Accessibility 思路做整体检查，而不是继续叠加零散阴影和临时 CSS。

### Canonical Wei.G 品牌图标

Header 常驻入口和 Favicon 都使用 `server/app/static/Wei.G.ico`。Header 中图标置于圆角触感 Chassis 中，包含克制的 Rim Light、Contact Shadow、Hover Lift 与 Pressed Compression；点击后仍打开 Utility Sheet。

### EndpointPicker

浏览器原生 Endpoint `<select>` 仍保留作为内部 State Bridge，但从可见 UI 中隐藏。`EndpointPicker` 提供：

- 关闭状态显示 WAN、Family / Provider 与 Address / Port；
- 带 Primary / Try / Selected 状态的触感 Endpoint Card；
- Desktop 使用靠近触发器的紧凑 Popover；
- Mobile 使用适配 Safe Area 的 Bottom Sheet；
- 支持 Escape / Backdrop Close、Focus Containment 与 ARIA Selected；
- 支持 `prefers-reduced-motion`。

### DurationControl

快捷项固定为：

```text
1m | 5m | 15m | 30m | Custom
```

**没有 1h 快捷项。**

`Custom` 打开触感 Duration Crown：

```text
最小  0.5h
最大  12h
步进  0.5h
```

每个 Custom Detent 可以播放很短的合成机械 Tick，并在支持的手机上提供可选轻震。Sound 与 Haptics 可在 Utility Sheet 中分别关闭，设置只保存在 Browser Local Storage。

Browser 不是 Duration 的最终权威。VPS 与 OpenWrt Firewall 都会独立校验 `1m / 5m / 15m / 30m`，以及最长 12h、每 0.5h 一档的 Custom TTL。

## Remote Gate 工作流程

1. 登录 Cloudflare 前置的 Dashboard。
2. VPS 记录当前 Cloudflare Observation；Browser Best-effort 补齐缺失的 IPv4 / IPv6 Family。
3. 选择 IPv4 或 IPv6、Endpoint、WireGuard Interface、Access Scope 与 Duration。
4. VPS 在 Server 端重新解析 Session Source 与 Endpoint，并排队一个短生命周期命令。
5. OpenWrt 通过出站 HTTPS 拉取命令。
6. Firewall 再次确认 WAN Device 与 WireGuard Port 仍属于受保护 Policy，然后只授权选定 Source Tuple。
7. OpenWrt ACK 一次性命令；未过期 Pending Command 不会被第二个 Activate / Close 静默覆盖。
8. TTL 到期或点击 **Close access now** 后，Gate 恢复关闭。

## 可选 IPv6 Gate

IPv6 是可选 Data-plane Capability。Fresh Install 默认 `GATE_IPV6=auto`；Legacy Upgrade 为保持保守行为，会加入 `GATE_IPV6=disabled`，直到管理员主动启用并验证。IPv4 Operation 不依赖 IPv6 Support。

出站 Control Transport 与 IPv6 Gate 分离。即使 IPv6 Data-plane Gate 被关闭，Agent 仍可使用健康的 IPv4 / IPv6 Multi-WAN Path 执行 report / pull / ack。

## NATMap 状态

Remote Gate 能理解 Mapped Endpoint Record，但不会安装或强制依赖 NATMap。21.02 Compatibility Path 在没有 NATMap 时可正常工作。Read-only Audit 可以读取已有 `/var/run/natmap/*.json` Runtime Status，但不会打印 NATMap Configuration 或 Remote Gate Secret。

## Adaptive Workspace

- Desktop：Main Canvas + Utility Rail；Activity / System 保持可读，不通过缩小字体塞成小工具卡；
- Mobile / Tablet：固定独立顺序 `Gate -> Client -> WireGuard -> WAN -> Activity -> System`，Desktop Drag / Span State 不会造成 Mobile Card Overlap；
- IPv6 始终保持完整单行，并根据可用宽度动态 Fit；
- Activity 默认单行 Summary，可展开查看 Details；
- CLOSED Gate Orb 与 Activate Button 共用同一 Eligibility / Action Path；
- Auto / Light / Dark、Language、Interaction Feedback 与 Sign out 都使用统一 Utility Control。

## 安全更新

### VPS

第一次从较老的 v0.2.x 升级时，不要依赖旧版固定 File List 的 Updater，应下载目标版本的 Updater：

```bash
curl -fsSL \
  https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main/server/update.sh \
  -o /tmp/remote-gate-update.sh

bash -n /tmp/remote-gate-update.sh
bash /tmp/remote-gate-update.sh
```

从 v0.3 开始，本机 Updater 固定保留在：

```bash
/usr/local/lib/remote-gate/update.sh
```

Updater 会保留 Hostname、登录凭据、`WRITE_TOKEN`、Session / State，在 `/var/backups/weig-remote-gate/` 创建 Rollback Backup，重启仅监听 localhost 的 Service，检查 `/healthz` 和 Agent API，失败时恢复旧 Application。

### OpenWrt

旧安装第一次升级时可能需要单独下载当前 `openwrt/update.sh`。v0.3+ 会正式安装并保留 Updater、Uninstaller 与 Read-only Audit Utility。升级会备份 Application / Config / State 与 Firewall / Network Snapshot，保留现有 WireGuard Configuration，替换前检查 Shell Syntax，只重建 Remote Gate 自己拥有的 INPUT Object；验证失败时回退到旧安装。

## 安全卸载

VPS 与 OpenWrt 都提供带 Dry-run 的单命令 Uninstaller。它们会先建立本机 Backup，只移除 Remote Gate 自己拥有的 Resource，并执行 Residual Check。OpenWrt **不会**盲目恢复旧整份 Firewall Snapshot，也不会默认删除 WireGuard。Cloudflare Tunnel Resource 不会自动删除。

## 当前版本

见 [`VERSION`](../VERSION)。Development Commit 使用 `-dev` 后缀。当前仓库发布流程是：在版本分支开发，要求 Core + Chromium Regression CI 全绿，审计最终 Diff，再决定是否进入 `main`；测试阶段可以直接停留在版本分支，不要求提前推 `main`。

## 验证状态

### 已完成真实硬件验证

fw3 IPv4 Path 已经在真实 ImmortalWrt 21.02 类 Router 上完成端到端验证，环境包含 iptables legacy + ipset、PPPoE Public WAN、Cloudflare Control Plane 和路由器本机 WireGuard Listener。已验证 CLOSED Blocking、Source-specific Activate、真实 WireGuard Traffic、TTL Expiry、过期后新 Handshake 失败，以及 INPUT-only Boundary 保持不变。

### 已实现并通过自动 CI

当前自动覆盖包括：

- Schema 2 IPv4 / IPv6 Endpoint Build 与排序；
- Public / Private / CGNAT / NAT-egress Try Path；
- IPv4 / IPv6 Session Source 独立保存和 Probe Replace Rule；
- IPv4-first 推荐，同时保留用户手动 IPv6 选择；
- `WireGuard only` / `WireGuard + Ping` Scope；
- VPS + OpenWrt 两端最长 12h 的 Custom TTL 校验；
- fw3 / fw4 Contract 与 IPv6 Echo-only Policy；
- Android / Mobile Layout Overlap Regression；
- EndpointPicker、DurationControl 与相关 Chromium Interaction Regression。

IPv6 Gate、移动运营商 Probe、Private / CGNAT WAN Path 和 fw4/nftables Backend 在标记为 Hardware-validated 前仍需要对应真实环境验证。

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

每个测试 Family 都应确认：TTL 内只有被授权的外部来源可以访问选定 WireGuard Endpoint；TTL 结束后重新发起的新 Handshake 必须失败。同时单独确认 qBittorrent 的监听 / 转发 Port 与升级前一样可达。

IPv6-first 手机场景需要同时确认 IPv4 / IPv6 Source 都能独立保留，选择 IPv4 后不会丢失 IPv6；若手动切到 IPv6，则后续 Dashboard Refresh 不应自动切回 IPv4。

Private / CGNAT 家庭 WAN 场景中，Gate Activation 成功只代表 Router Firewall 已接受该 Source；真正从 Internet 入站仍取决于上游 Port Mapping、NATMap 或运营商网络行为。

## License

GPL-3.0-only.
