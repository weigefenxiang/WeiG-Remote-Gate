# WeiG-Remote-Gate

**Language:** [English](../README.md) · [简体中文](README.zh-CN.md)

**面向 OpenWrt / ImmortalWrt 的安全远程访问网关。**

WeiG-Remote-Gate 是一个通过 Cloudflare 前置的 Multi-WAN 状态与临时私有远程访问控制面。家庭 WAN **不会**运行 HTTP/HTTPS 管理服务；OpenWrt 只通过出站 HTTPS 上报 Inventory / Status，并拉取短生命周期命令。

v0.3.17 开始，Remote Gate 自己提供通用 **Mapped Access** 架构，不依赖 NATMap。公网如何进入家庭网络与进入后交给哪个服务被明确拆开：Access Method 负责 `Direct / Mapped / Relay`，Service Registry 负责本机可被 Remote Gate 使用的服务。v0.3.17 首先实现 IPv4/UDP Mapped Access + WireGuard Adapter；后续协议只能通过新的 Service Adapter 扩展，不能让 Browser 任意指定内网端口。

## 安全边界与流量归属

**Access Gate** 只接管受保护 WAN Endpoint 上、发往路由器本机且由 Remote Gate 明确注册的流量：

```text
ICMP / ICMPv6 Echo Request       -> 默认关闭
Direct WireGuard UDP Listener    -> 默认关闭
Mapped UDP Ingress               -> 默认关闭
```

Mapped Ingress 使用精确的 `WAN device + ingress_port` 配对保护，不会把某个随机映射端口扩展成所有 WAN 的全局端口规则。

Access Gate 只工作在路由器的 **INPUT** 路径，不会安装通用 `FORWARD` 过滤规则，也不会管理无关 TCP/UDP 端口。因此 qBittorrent、DHT / PeX、UPnP / NAT-PMP、DNAT / 手工端口转发，以及转发到 NAS / PC 的服务继续由原 Firewall Policy 处理。

提供两种 Access Scope：

- **仅 WireGuard** —— 推荐，Ping 继续关闭；
- **WireGuard + Ping** —— 同时允许该授权来源发送 Echo Request。

v0.3.17 的 Service Registry 只登记经过本机验证的 WireGuard UDP Listener。Browser / VPS 只能选择 `service_id`，不能提交任意 `target_ip` 或 `target_port`。以后增加 Shadowsocks、ShadowsocksR 或其他协议时，也必须先由对应 OpenWrt Adapter 注册和校验。

IPv6 Access Gate 只控制 Echo Request 与选定的路由器本机 WireGuard UDP Port。NDP、Router Advertisement、Packet Too Big 和其他 ICMPv6 控制流量继续交给原 Firewall Policy。

可选的 **Internet Exit** 与 Access Gate 分离。只有用户明确选择 Internet Exit 时，Remote Gate 才会临时安装把选定 WireGuard Client Subnet 送往选定 WAN 所需的 PBR、FORWARD 与 NAT44 / NAT66 状态。它不会接管无关转发流量，也不会把 Egress Policy 持久化到 UCI。

## v0.3.17 架构

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
OpenWrt Agent
   |
   +-- Multi-WAN Inventory / Control Path
   +-- Access Endpoint
   |    +-- Direct
   |    +-- Mapped
   |    `-- Relay                 <- future
   |
   +-- Access Gate
   |    +-- CLOSED / Activate / TTL / Source ACL
   |    `-- fw3 / fw4 INPUT Backend
   |
   +-- Service Registry
   |    +-- WireGuard             <- v0.3.17
   |    +-- Shadowsocks           <- future Adapter
   |    +-- ShadowsocksR          <- future Adapter
   |    `-- Other registered service
   |
   +-- Mapping Engine
   |    `-- IPv4 / UDP            <- v0.3.17
   |
   `-- Optional runtime WireGuard Internet Exit
```

Cloudflare 域名属于**控制面**。WireGuard 等注册服务属于**数据面**，必须访问选定的家庭 Access Endpoint。不要把 Cloudflare Tunnel 域名作为 WireGuard UDP Endpoint。

### 三端口模型

Mapped Access 不把公网端口、本机入口端口和真实服务端口混为一个字段：

```text
Internet
   |
external_address:external_port
   |
ISP / CGNAT mapping
   |
WAN device:ingress_port
   |
Access Gate
   |
remote-gate-mapper
   |
127.0.0.1:service_port
   |
Registered Service
```

- `external_port`：Internet Client 实际连接的公网映射端口；
- `ingress_port`：Remote Gate Mapper 在选定 WAN 上拥有的本机 UDP Socket；
- `service_port`：Service Registry 验证过的真实服务端口，例如 WireGuard Listen Port。

Mapper 启动后先进入 `prepared` 状态。只有 Agent 已把 `device + ingress_port` 注册到 Access Gate 并完成 Firewall Sync 后，才创建 Go Signal 允许 Mapper 执行 STUN Discovery。这样不会出现“公网 Mapping 已建立但 Gate 还没 CLOSED 保护”的时间窗口。

## Firewall 兼容性

| 平台 | Remote Gate Backend |
| --- | --- |
| firewall3 / `fw3` | `iptables` + `ipset` timeout |
| firewall4 / `fw4` | `nftables` timeout sets |

Gate Guard 会在普通 `ESTABLISHED,RELATED` 快捷放行之前执行。原有 UCI 规则（例如 `Allow-Ping`）不会被删除；只有 Remote Gate Access Gate 接管的流量由更靠前的 Guard 决定，卸载后恢复原 Firewall 行为。

fw3 对 Mapped Access 使用精确的 `-i <WAN device> -p udp --dport <ingress_port>` Guard；fw4 使用 `ifname . inet_service` 二元集合。Mapped Port 不进入 Direct WireGuard 的全局 Port Set，因此 Multi-WAN 下不会形成错误的 WAN × Port 笛卡尔积。

已知目标包括 ImmortalWrt / OpenWrt 21.02 类 fw3 系统，以及现代 fw4 系统。无法识别的 Backend 在安装阶段 fail closed。

在 fw3 / iptables 系统上，Runtime Internet Exit 会等待 xtables lock，而不是把短暂的并发 Firewall 更新立即当成失败。

## Schema 3 Access Endpoint 模型

v0.3.17 的权威 Inventory 使用 Schema 3：

```text
wans[]
services[]
mappings[]
capabilities{}
```

Server 不再假定只有一个 Public IPv4 WAN。Access Endpoint 可以是：

- Public IPv4 `Direct`；
- 启用 IPv6 Gate Capability 时的 Global IPv6 `Direct`；
- Remote Gate 自有 Mapping Engine 产生的 IPv4 `Mapped`；
- 每条 WAN 实测得到的 IPv4 `NAT egress · Try`；
- 供手工实验使用的 Private / CGNAT IPv4 `Try`；
- `Relay` 作为未来 Access Method 预留，不在 v0.3.17 实现。

Schema 3 的 `mapping.service_id` 必须匹配同一 Inventory 中经过验证的 `services[]`，并且 Mapping 的 `wan + device` 必须匹配当前活动 WAN。VPS 会在存储边界再次清洗这些记录，OpenWrt 执行 Activate 时还会再次通过本机 Service Registry 与 Mapping Runtime 独立验证。

旧 Schema 2 仍只作为滚动升级兼容输入存在；它不是 v0.3.17 的新架构，也不会让 NATMap 成为当前依赖或 Provider。

Direct / Mapped Path 会优先推荐。Private / CGNAT 地址不会被错误描述为“公网可达”。没有可用 Mapper Binary 时，Mapped Access 只报告 `unavailable`；Direct、IPv6 Gate、Control Plane 和现有 WireGuard Gate 不会因此失败。

## 双栈 Client Source

IPv4 与 IPv6 是同一已认证 Browser Session 下的**独立记录**。学习到一个 Family 绝不会删除另一个 Family。

Source 优先级：

1. **Cloudflare Observation (`verified`)** —— 当前请求的 `CF-Connecting-IP`；
2. **Network Probe (`heuristic`)** —— 某个 Family 缺失时使用的短生命周期补充来源。

IPv4 / IPv6 缺失 Family 会独立探测：

- IPv4：IPv4-only `api.ipify.org`，适合手机 Carrier NAT / CGNAT / NAT64 / 464XLAT 场景；
- IPv6：IPv6-only `api6.ipify.org`，适合 Dashboard 当前通过 IPv4 到达 Cloudflare、但设备本身同时具备可用 IPv6 的情况。

Browser 只把 Probe 结果提交给受 Session + CSRF 保护的 Endpoint。之后若 Cloudflare 对同一 Family 获得直接 Observation，则会自动替换 heuristic 记录。普通 Activate 请求仍不会把任意 Raw Authorization IP 作为权威输入；VPS 会从 Session Source Store 解析所选 Family。

当 IPv4 / IPv6 都可用时，UI **默认推荐 IPv4**，但不是锁死。用户手动选择 IPv6 后，只要 IPv6 仍可用，后续刷新就会保留该手动选择，不会自动抢回 IPv4。

## 触感交互系统

Dashboard 遵循 [`DESIGN.md`](../DESIGN.md) 的统一设计系统。视觉改动以 `awesome-design-md` 的层级、间距、Elevation、Motion 与 Accessibility 思路做整体检查，而不是继续叠加零散阴影和临时 CSS。

### EndpointPicker

浏览器原生 Endpoint `<select>` 仍保留作为内部 State Bridge，但从可见 UI 中隐藏。`EndpointPicker` 对用户只暴露稳定的 Access Method 语义：

```text
Direct
Mapped
Relay
```

底层 Mapping Engine 的实现细节不会再作为 NATMap 或其他第三方 Provider 名称显示到主 UI。

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

Browser 不是 Duration 的最终权威。VPS 与 OpenWrt Firewall 都会独立校验 `1m / 5m / 15m / 30m`，以及最长 12h、每 0.5h 一档的 Custom TTL。

## Remote Gate 工作流程

1. 登录 Cloudflare 前置的 Dashboard。
2. VPS 记录当前 Cloudflare Observation；Browser Best-effort 补齐缺失的 IPv4 / IPv6 Family。
3. 选择 IPv4、IPv6 或 Dual、Access Endpoint、WireGuard Interface、Access Scope、Duration，以及可选 Internet Exit。
4. VPS 在 Server 端重新解析 Session Source、Access Endpoint 与注册 Service，并排队短生命周期命令事务。
5. OpenWrt 通过出站 HTTPS 拉取命令。
6. OpenWrt 再次确认 WAN Device、Access Method、Ingress Port、Service ID / Service Port 与当前本机 Runtime 一致。
7. Gate Firewall 只对选定 Source Tuple 开放选定的 Direct 或 Mapped Ingress。
8. 如果选择 Internet Exit，Runtime Egress Helper 会独立校验 WireGuard Subnet 与选定 WAN Route，再安装受限的 PBR / FORWARD / NAT 状态。
9. OpenWrt 分别上报 Gate、Mapping 与 Internet Exit 状态；其中任何一个成功都不会伪装成另一个组件成功。
10. TTL 到期或点击 **Close access now** 后，清理相应临时授权；Mapped Socket 可以继续维持 NAT Mapping，但未授权来源仍由 Access Gate DROP。

## Mapped Access

Remote Gate 不安装、不调用、也不要求 NATMap。v0.3.17 的 Mapping Engine 由项目自己的 `remote-gate-mapper` 与 `remote-gate-mapping.sh` 管理。

第一版 Native Mapper 的职责严格限制为：

- IPv4 / UDP Socket；
- 绑定指定 WAN Device；
- STUN Endpoint Discovery；
- NAT Mapping Keepalive；
- Mapping Change Detection；
- 按 Internet Source Tuple 维护短生命周期 UDP Relay Session；
- 把通过 Gate 的 UDP Payload 交给本机已注册 Service。

Mapper **不解析 WireGuard 协议**，也不接受 Browser 指定任意内网 Target。后续如果增加其他 UDP Service，只应增加 Service Adapter；如果将来增加 TCP Mapping，则应作为新的 Transport Backend 实现，而不是把 UDP 逻辑硬改成 TCP。

### Native Binary ABI

老 OpenWrt 设备不应依赖路由器现场安装 GCC。`remote-gate-mapper` 设计为预编译 Native Capability。Audit 会输出：

```text
Kernel machine
OpenWrt package ABI
opkg architectures
```

Native Binary 必须与实际 OpenWrt Package ABI 精确匹配；项目不会仅凭“可能是 MIPS / ARM”猜测并安装错误二进制。没有匹配 Binary 时，Mapped Access 保持不可用，其余 Remote Gate 功能继续正常。

## 可选 IPv6 Gate

IPv6 是可选 Data-plane Capability。Fresh Install 默认 `GATE_IPV6=auto`；Legacy Upgrade 为保持保守行为，会加入 `GATE_IPV6=disabled`，直到管理员主动启用并验证。IPv4 Operation 不依赖 IPv6 Support。

出站 Control Transport 与 IPv6 Gate 分离。即使 IPv6 Data-plane Gate 被关闭，Agent 仍可使用健康的 IPv4 / IPv6 Multi-WAN Path 执行 report / pull / ack。

## 可选 WireGuard Internet Exit

Internet Exit 只存在于 Runtime，并且与 Access Endpoint 是两个独立选择。首次进入某个 IP Family 时，Internet Exit 默认跟随当前 Access Endpoint WAN；如果用户手动改过 Exit，则该 Family 会保留用户自己的独立选择。

支持 IPv4、IPv6 与 Dual。Dual 安装是事务性的：两种 Family 都成功才写入 active 状态；任一 Family 失败都会回滚已经安装的部分。

IPv6 场景下，像 `default from <delegated-prefix> via <link-local-gateway>` 这样的 Source-specific WAN Default 不会被原样复制到 WireGuard PBR Table。Egress Helper 会从中提取 Gateway / Device，并为 WireGuard ULA 建立不带 `from` 限制的临时 Default Route。

Internet Exit 不创建持久 UCI Policy。Disable、Close、TTL Expiry、失败回滚或 Reboot 后 Internet Exit 都恢复为 Off。

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

如果没有与当前 Package ABI 匹配的 Native Mapper，Updater 不会把整个升级判为失败；只会让 Mapped Access 保持 `unavailable`。

## 安全卸载

VPS 与 OpenWrt 都提供带 Dry-run 的单命令 Uninstaller。它们会先建立本机 Backup，只移除 Remote Gate 自己拥有的 Resource，并执行 Residual Check。OpenWrt **不会**盲目恢复旧整份 Firewall Snapshot，也不会默认删除 WireGuard。Mapper Runtime 在 Firewall 清理之前停止，只删除 Remote Gate 自己拥有的 PID / State。

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

fw3 IPv4 Direct Access Gate Path 已经在真实 ImmortalWrt 21.02 类 Router 上完成端到端验证，环境包含 iptables legacy + ipset、PPPoE Public WAN、Cloudflare Control Plane 和路由器本机 WireGuard Listener。已验证 CLOSED Blocking、Source-specific Activate、真实 WireGuard Traffic、TTL Expiry、过期后新 Handshake 失败，以及 Access Gate INPUT-only Boundary 保持不变。

Runtime WireGuard Internet Exit 也已经在真实设备上用 Dual Client Configuration 验证到以下层级：

- WireGuard IPv4 Subnet `10.77.0.0/24`；
- WireGuard IPv6 ULA Subnet `fd77:77:77::/64`；
- IPv4 / IPv6 各自存在高优先级 Policy Rule 与临时 Egress Table；
- WAN2 IPv4 Default 正确指向选定 PPPoE Device；
- WAN2 Source-specific IPv6 Default 已被转换为适用于 WireGuard ULA 的无 `from` 限制临时 Default；
- NAT44 / NAT66 MASQUERADE 都观察到真实 Client Traffic 的 Packet / Byte Counter 增长；
- IPv4 可以同时访问 LAN 和 Internet，并确认公网出口为选定 WAN2；
- Runtime `status-json` 正确报告 `active=true`、`mode=dual`，TTL 后能够清理。

这些已有验证**不能**自动视为 v0.3.17 Mapped Access 已完成硬件验证。Mapped Access 在实际 CGNAT / NAT 网络、匹配 Router ABI 的 Native Binary、真实外部 WireGuard Handshake、TTL / Close、WAN Reconnect 等场景验证前，仍属于开发能力。

### 已实现并通过自动 CI

当前自动覆盖包括：

- Schema 2 Rolling Compatibility；
- Schema 3 `wans + services + mappings` Validation；
- Direct / Mapped Endpoint Build 与排序；
- Mapped `external_port / ingress_port / service_port` 三端口契约；
- Mapping 必须引用活动 WAN/device 与已注册 Service；
- fw3 精确 `device + ingress_port` Mapped Guard；
- fw4 `ifname . inet_service` Mapped Tuple Set；
- Mapper `prepared -> firewall sync -> go -> STUN` 顺序契约；
- Native C Mapper 使用严格 Warning-as-error 编译；
- Public / Private / CGNAT / NAT-egress Try Path；
- IPv4 / IPv6 Session Source 独立保存和 Probe Replace Rule；
- `WireGuard only` / `WireGuard + Ping` Scope；
- VPS + OpenWrt 两端最长 12h 的 Custom TTL 校验；
- Runtime IPv4 / IPv6 / Dual Egress Selection 与 Rollback Contract；
- Android / Mobile Layout Overlap Regression；
- EndpointPicker、DurationControl 与 Chromium Interaction Regression。

完整 Client-side IPv6 Internet、v0.3.17 Mapped Access、Private / CGNAT WAN Path 与 fw4/nftables Hardware Behavior 在标记为完整 Hardware-validated 前仍需要对应真实环境验证。

## 生产 / 实机验证

先运行 Read-only Audit、Gate State、Mapping State 与 Egress State：

```sh
/usr/lib/remote-gate/remote-gate-audit.sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
/usr/lib/remote-gate/remote-gate-mapping.sh status-json
/usr/lib/remote-gate/remote-gate-wireguard-egress.sh status-json
```

Mapped Access 的真实网络验证顺序必须至少包含：

```text
CLOSED
-> Mapper prepared / active
-> 未授权来源不能建立新 WireGuard Handshake
-> Activate 当前外部 Source
-> 通过 external_address:external_port 建立真实 WireGuard Handshake
-> LAN 访问
-> 可选 Internet Exit
-> TTL
-> 新 Handshake 再次失败
-> Close
-> WAN reconnect / Mapping change
```

同时确认 qBittorrent、UPnP / NAT-PMP、既有 DNAT、LAN Forward 与其它无关端口行为和升级前一致。

## License

GPL-3.0-only.
