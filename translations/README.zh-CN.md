# WeiG-Remote-Gate

**Language:** [English](../README.md) · [简体中文](README.zh-CN.md)

**面向 OpenWrt / ImmortalWrt 的安全远程访问网关。**

WeiG-Remote-Gate 是一个通过 Cloudflare 前置的 Multi-WAN 状态与临时私有远程访问控制面。家庭 WAN **不会**运行 HTTP/HTTPS 管理服务；OpenWrt 只通过出站 HTTPS 上报 Inventory / Status，并拉取短生命周期命令。

## 安全边界与流量归属

**Access Gate** 只接管受保护 WAN Endpoint 上、发往路由器本机的两类流量：

```text
ICMP / ICMPv6 Echo Request   -> 默认关闭
WireGuard UDP 监听端口       -> 默认关闭
```

Access Gate 只工作在路由器的 **INPUT** 路径，不会安装通用 `FORWARD` 过滤规则，也不会管理无关 TCP/UDP 端口。因此 qBittorrent、DHT / PeX、UPnP / NAT-PMP、DNAT / 手工端口转发，以及转发到 NAS / PC 的服务继续由原 Firewall Policy 处理。

提供两种 Access Scope：

- **仅 WireGuard** —— 推荐，Ping 继续关闭；
- **WireGuard + Ping** —— 同时允许该授权来源发送 Echo Request。

IPv6 Access Gate 只控制 Echo Request 与选定的路由器本机 WireGuard UDP Port。NDP、Router Advertisement、Packet Too Big 和其他 ICMPv6 控制流量继续交给原 Firewall Policy。

可选的 **Internet Exit** 与 Access Gate 分离。只有用户明确选择 Internet Exit 时，Remote Gate 才会临时安装把选定 WireGuard Client Subnet 送往选定 WAN 所需的 PBR、FORWARD 与 NAT44 / NAT66 状态。它不会接管无关转发流量，也不会把 Egress Policy 持久化到 UCI。

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
   +-- fw3 / fw4 Gate Firewall Backend
   +-- IPv4 / IPv6 WAN Inventory
   +-- WireGuard 自动发现
   +-- Multi-WAN Control Path 选择
   `-- 可选 Runtime WireGuard Internet Exit
```

Cloudflare 域名属于**控制面**。WireGuard 属于**数据面**，必须直接访问选定的家庭 Endpoint。不要把 Cloudflare Tunnel 域名作为 WireGuard UDP Endpoint。

## Firewall 兼容性

| 平台 | Remote Gate Backend |
| --- | --- |
| firewall3 / `fw3` | `iptables` + `ipset` timeout |
| firewall4 / `fw4` | `nftables` timeout sets |

Gate Guard 会在普通 `ESTABLISHED,RELATED` 快捷放行之前执行。原有 UCI 规则（例如 `Allow-Ping`）不会被删除；只有 Remote Gate Access Gate 接管的流量由更靠前的 Guard 决定，卸载后恢复原 Firewall 行为。

已知目标包括 ImmortalWrt / OpenWrt 21.02 类 fw3 系统，以及现代 fw4 系统。无法识别的 Backend 在安装阶段 fail closed。

在 fw3 / iptables 系统上，Runtime Internet Exit 会等待 xtables lock，而不是把短暂的并发 Firewall 更新立即当成失败。

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
3. 选择 IPv4、IPv6 或 Dual、Access Endpoint、WireGuard Interface、Access Scope、Duration，以及可选 Internet Exit。
4. VPS 在 Server 端重新解析 Session Source 与 Endpoint，并排队短生命周期命令事务。
5. OpenWrt 通过出站 HTTPS 拉取命令。
6. Gate Firewall 再次确认 WAN Device 与 WireGuard Port 仍属于受保护 Policy，然后只授权选定 Source Tuple。
7. 如果选择 Internet Exit，Runtime Egress Helper 会独立校验 WireGuard Subnet 与选定 WAN Route，再安装受限的 PBR / FORWARD / NAT 状态。
8. OpenWrt 分别上报 Gate 与 Internet Exit 状态；Gate 已授权不会被当成 Egress 已成功。
9. TTL 到期或点击 **Close access now** 后，清理相应临时状态。

## 可选 IPv6 Gate

IPv6 是可选 Data-plane Capability。Fresh Install 默认 `GATE_IPV6=auto`；Legacy Upgrade 为保持保守行为，会加入 `GATE_IPV6=disabled`，直到管理员主动启用并验证。IPv4 Operation 不依赖 IPv6 Support。

出站 Control Transport 与 IPv6 Gate 分离。即使 IPv6 Data-plane Gate 被关闭，Agent 仍可使用健康的 IPv4 / IPv6 Multi-WAN Path 执行 report / pull / ack。

## 可选 WireGuard Internet Exit

Internet Exit 只存在于 Runtime，并且与 Access Endpoint 是两个独立选择。首次进入某个 IP Family 时，Internet Exit 默认跟随当前 Access Endpoint WAN；如果用户手动改过 Exit，则该 Family 会保留用户自己的独立选择。

支持 IPv4、IPv6 与 Dual。Dual 安装是事务性的：两种 Family 都成功才写入 active 状态；任一 Family 失败都会回滚已经安装的部分。

IPv6 场景下，像 `default from <delegated-prefix> via <link-local-gateway>` 这样的 Source-specific WAN Default 不会被原样复制到 WireGuard PBR Table。Egress Helper 会从中提取 Gateway / Device，并为 WireGuard ULA 建立不带 `from` 限制的临时 Default Route。

Internet Exit 不创建持久 UCI Policy。Disable、Close、TTL Expiry、失败回滚或 Reboot 后 Internet Exit 都恢复为 Off。

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

第一次从较老的 v0.2.x 升级时，不要依赖旧版固定 File List 的 Updater，应下载当前 `main` 的 Updater：

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

旧安装第一次升级时可能需要单独下载当前 `openwrt/update.sh`。v0.3+ 会正式安装并保留 Updater、Uninstaller 与 Read-only Audit Utility。升级会备份 Application / Config / State 与 Firewall / Network Snapshot，保留现有 WireGuard Configuration，替换前检查 Shell Syntax，只重建 Remote Gate 自己拥有的状态；Internet Exit 仍然只使用 Runtime 临时状态，不写成持久 UCI Egress Policy。验证失败时回退到旧安装。

## 安全卸载

VPS 与 OpenWrt 都提供带 Dry-run 的单命令 Uninstaller。它们会先建立本机 Backup，只移除 Remote Gate 自己拥有的 Resource，并执行 Residual Check。OpenWrt **不会**盲目恢复旧整份 Firewall Snapshot，也不会默认删除 WireGuard。Cloudflare Tunnel Resource 不会自动删除。

## 当前版本与分支流程

软件版本见 [`VERSION`](../VERSION)，**版本号不写进 Git 分支名**。

仓库固定流程：

```text
dev  -> 开发、修复、CI
main -> 已验证稳定状态
```

所有日常开发只提交到固定 `dev`。Core + Chromium Regression CI 全绿并完成 Diff 审计后，再把已验证的 `dev` 推进 `main`。正常开发不再创建 `dev/*` 或版本分支。

## 验证状态

### 已完成真实硬件验证

fw3 IPv4 Access Gate Path 已经在真实 ImmortalWrt 21.02 类 Router 上完成端到端验证，环境包含 iptables legacy + ipset、PPPoE Public WAN、Cloudflare Control Plane 和路由器本机 WireGuard Listener。已验证 CLOSED Blocking、Source-specific Activate、真实 WireGuard Traffic、TTL Expiry、过期后新 Handshake 失败，以及 Access Gate INPUT-only Boundary 保持不变。

Runtime WireGuard Internet Exit 也已经在真实设备上用 Dual Client Configuration 验证到以下层级：

- WireGuard IPv4 Subnet `10.77.0.0/24`；
- WireGuard IPv6 ULA Subnet `fd77:77:77::/64`；
- IPv4 / IPv6 各自存在高优先级 Policy Rule 与临时 Egress Table；
- WAN2 IPv4 Default 正确指向选定 PPPoE Device；
- WAN2 Source-specific IPv6 Default 已被转换为适用于 WireGuard ULA 的无 `from` 限制临时 Default；
- NAT44 / NAT66 MASQUERADE 都观察到真实 Client Traffic 的 Packet / Byte Counter 增长；
- IPv4 可以同时访问 LAN 和 Internet，并确认公网出口为选定 WAN2；
- Runtime `status-json` 正确报告 `active=true`、`mode=dual`，TTL 后能够清理。

NAT66 Counter 已证明 IPv6 Client Packet 经过配置的 Egress NAT Path；但在没有从 Client 侧单独确认公网 IPv6 Reachability 前，文档不会把“完整 IPv6 Internet 端到端”写成 Hardware-validated。

### 已实现并通过自动 CI

当前自动覆盖包括：

- Schema 2 IPv4 / IPv6 Endpoint Build 与排序；
- Public / Private / CGNAT / NAT-egress Try Path；
- IPv4 / IPv6 Session Source 独立保存和 Probe Replace Rule；
- IPv4-first 推荐，同时保留用户手动 IPv6 选择；
- `WireGuard only` / `WireGuard + Ping` Scope；
- VPS + OpenWrt 两端最长 12h 的 Custom TTL 校验；
- fw3 / fw4 Gate Contract 与 IPv6 Echo-only Policy；
- Runtime IPv4 / IPv6 / Dual Egress Selection 与 Rollback Contract；
- 从 Interface Address 识别 WireGuard ULA；
- Source-specific IPv6 WAN Default 处理；
- fw3 Egress xtables-lock 等待；
- Gate / Internet Exit 独立状态与旧失败状态过期；
- Android / Mobile Layout Overlap Regression；
- EndpointPicker、DurationControl 与相关 Chromium Interaction Regression。

完整 Client-side IPv6 Internet、移动运营商 Probe、Private / CGNAT WAN Path 与 fw4/nftables Hardware Behavior 在标记为完整 Hardware-validated 前仍需要对应真实环境验证。

## 生产环境验证

先运行 Read-only Audit、Gate State 与 Egress State：

```sh
/usr/lib/remote-gate/remote-gate-audit.sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
/usr/lib/remote-gate/remote-gate-wireguard-egress.sh status-json
```

fw3 IPv4 Gate：

```sh
iptables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v4
iptables -S WEIG_REMOTE_GATE
```

fw3 IPv6 Gate（启用时）：

```sh
ip6tables -S INPUT | sed -n '1,8p'
ipset list weig_remote_gate_auth_v6
ip6tables -S WEIG_REMOTE_GATE_V6
```

Runtime Internet Exit：

```sh
ip -4 rule show
ip -6 rule show
iptables -t nat -vnL WEIG_WG_EGRESS_NAT 2>/dev/null
ip6tables -t nat -vnL WEIG_WG_EGRESS_NAT6 2>/dev/null
```

每个 Gate Family 都应确认：TTL 内只有被授权的外部来源可以访问选定 WireGuard Endpoint；TTL 结束后重新发起的新 Handshake 必须失败。同时单独确认 qBittorrent 的监听 / 转发 Port 与升级前一样可达。

Internet Exit 需要另外确认：选定 WireGuard Subnet 只通过所选 WAN 出口，Close / TTL 后临时 PBR、Route Table、FORWARD 与 NAT 状态全部清理。

IPv6-first 手机场景需要同时确认 IPv4 / IPv6 Source 都能独立保留，选择 IPv4 后不会丢失 IPv6；若手动切到 IPv6，则后续 Dashboard Refresh 不应自动切回 IPv4。

Private / CGNAT 家庭 WAN 场景中，Gate Activation 成功只代表 Router Firewall 已接受该 Source；真正从 Internet 入站仍取决于上游 Port Mapping、NATMap 或运营商网络行为。

## License

GPL-3.0-only.
