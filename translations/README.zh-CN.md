# WeiG-Remote-Gate

**Language:** [English](../README.md) · [简体中文](README.zh-CN.md)

**面向 OpenWrt / LEDE / ImmortalWrt 的安全远程访问网关。**

WeiG-Remote-Gate 是一个由 Cloudflare 前置的 Multi-WAN 状态与短生命周期私有远程访问控制面。家庭 WAN **不运行** HTTP/HTTPS 管理服务；OpenWrt 系路由器只通过出站 HTTPS 上报 Inventory / Status 并拉取命令。

项目按**运行时能力**而不是发行版名称做判断。OpenWrt、LEDE、ImmortalWrt 的品牌/版本字符串只是元数据，实际 Capability 才是权威。

## 产品模型

用户可见的 Access Method 固定为：

```text
Direct
Mapped
Relay   （未来）
```

- **Direct**：公网 IPv4 或 Global IPv6 直接到达路由器本机已注册服务；
- **Mapped**：Remote Gate 自己维护 NAT Mapping，用 Access Gate 保护专用本机入口，再把已授权流量转交给本机已注册服务；
- **Relay**：未来预留的中继 Transport。

NATMap **不是**依赖、软件包要求、Provider 名称或产品概念。Mapped Access 由 Remote Gate 自己实现。

当前 Mapped 范围刻意保持很小：**IPv4 + UDP + WireGuard**。通用 TCP Proxy、Browser 任意指定端口转发、HTTP/SSH/qBittorrent Mapping、TURN、用户 Callback 都不在当前范围。

## 系统性架构规则

本项目最重要的不变量是：**网络事实、Capability、用户计划、Runtime Authority 不能混成一层。**

```text
Network facts / capability
        |
        +--> AccessPlan ------> Access Gate ------> registered service
        |
        `--> InternetExitPlan -------------------> temporary WG egress
```

因此：

- `Private/CGNAT` 只是网络事实，**不是可选择的公网 Access Endpoint**；
- Mapping 存在不等于 Gate 已授权；
- Access Endpoint 不等于 Internet Exit；
- 默认/推荐 Plan 不等于 Runtime Authority；
- 当前 HTTP Request Source 只是 Observation，不是无条件授权来源；
- WAN/device/Mapping/Route/Service Identity 一旦过期或不明确，必须 fail closed，不能猜测或静默迁移。

跨层硬规则以 [`docs/SYSTEMIC-INVARIANTS.md`](../docs/SYSTEMIC-INVARIANTS.md) 为统一入口；同时阅读 [`docs/PROJECT-RULES.md`](../docs/PROJECT-RULES.md)、[`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)、[`docs/SECURITY-MODEL.md`](../docs/SECURITY-MODEL.md) 与 [`docs/CURRENT-DEVICE-VALIDATION.md`](../docs/CURRENT-DEVICE-VALIDATION.md)。

## Access Endpoint 模型

Server 不假设只有一个 WAN，也不会硬编码 `WAN` / `WAN2`。

当前用户可选择的 Access Candidate 包括：

- Public IPv4 `Direct`；
- IPv6 Gate Capability 可用时的 Global IPv6 `Direct`；
- IPv4 UDP `Mapped`；
- 每 WAN 实测得到的 IPv4 `NAT egress · Try`，作为实验性 fallback；
- 未来实现的 `Relay`。

Private / RFC1918 / CGNAT Interface Address 可以继续保留在 Inventory 中做诊断或判断出站能力，但不会作为公网 Access Endpoint 暴露给用户。

自动推荐顺序按 Capability，而不是 WAN 名称：

```text
IPv4: Public Direct -> Mapped -> observed NAT egress Try
IPv6: 优先使用首选 IPv4 WAN 上的 Global IPv6；
      没有时再选最佳 Global IPv6 Direct
Dual: 同 WAN Public IPv4 Direct + Global IPv6
      -> 同 WAN Mapped IPv4 + Global IPv6
      -> 跨 WAN 的最佳有效 IPv4 + IPv6
```

Dual 可以 Split WAN；WAN/WAN2 从来不是产品规则。

## Access Gate 与 Service Registry

Browser 不能凭空创建 `192.168.x.x:port` 转发。服务必须先由 OpenWrt 本机发现/注册并独立校验，才能成为 Remote Gate 的目标。

当前 Service Adapter 是 WireGuard。WireGuard Listen Port 是运行时数据，必须从真实服务发现，**不能把 51820 写死成策略**。

Mapped Access 明确区分三个端口：

```text
external_port  公网 Direct/Mapping Endpoint Port
ingress_port   Remote Gate 在路由器本机拥有并由 Access Gate 保护的入口
service_port   本机已验证服务的真实 Listen Port
```

Direct 场景它们可以相同；Mapped 场景可以不同。

Mapped 生命周期：

```text
CLOSED
Internet -> mapped endpoint -> ingress_port -> DROP

ACTIVE
approved source -> mapped endpoint -> ingress_port -> mapper -> registered service

TTL / Close
mapping 可以继续存在 -> ingress_port -> DROP
```

因此 Mapper/STUN Control 可以在 Gate CLOSED 时继续运行；**Mapping 存在绝不能被解释为授权已经打开。**

## Client Source Authority

IPv4 与 IPv6 是同一已认证 Browser Session 下的独立 Source Record。

Source Evidence 可以来自 Cloudflare HTTP Observation，也可以来自某个缺失 Family 的短生命周期 Carrier Candidate Probe。普通 Activate 请求不会把任意 Raw IP 当作授权权威；VPS 会从当前 Session Source Store 解析所选 Family。

Router 自己的 Direct Address、Mapped External Address 和 Internet Exit Address 都不能覆盖真实 Remote Client Source。Gate ACTIVE 后，已授权 Source 会被 pin，避免 Browser 经过 WireGuard Internet Exit 返回控制面后，把 Router Egress 误写成新的客户端来源。

## Internet Exit

Internet Exit 只存在于 Runtime，并且**与 Access Gate Family 独立**。

Canonical Mode：

```text
none
ipv4
ipv6
dual
```

默认推荐会跟随当前 Access Family（`IPv4 -> ipv4`、`IPv6 -> ipv6`、`Dual -> dual`），但用户可以显式选择其他受支持 Exit Mode。单协议族 Access Gate 并不会禁止另一个 WireGuard Internet Exit Family，只要对应 Tunnel Subnet 与 WAN Capability 有效。

IPv4 Egress 需要 WAN Up 且当前存在 IPv4 Default Route。WAN 本地 IPv4 可以是 Public、RFC1918 或 CGNAT；这个分类本身不会取消它作为出站 Internet Exit 的资格。

IPv6 Egress 需要 WAN Up、当前 IPv6 Default Route 和可用 Global IPv6。

Dual Egress 可以 same-WAN 或 split-WAN，并且必须原子执行：任何一个 Family 校验/安装失败，都回滚整个 Dual Runtime。选定 WAN/L3/Default Route 或 Remote Gate Policy-table Default 一旦失效，Egress 必须 fail closed 清除，不能静默掉到另一个 WAN。

Internet Exit 不写持久 UCI Policy；Disable、Close、TTL Expiry、失败回滚或 Reboot 后都恢复为 Off。

## Firewall 与平台兼容

| 检测到的 Firewall | Remote Gate Backend |
| --- | --- |
| `fw3` + `iptables` + `ipset` | `fw3-iptables` |
| `fw4` + `nft` | `fw4-nftables` |

Access Gate 只拥有 Remote Gate 已注册的 Router-local Ingress 与可选 Echo Request Scope。Internet Exit 只拥有其临时 WireGuard Subnet PBR/FORWARD/NAT44/NAT66 Path。qBittorrent/DHT/PeX、UPnP/NAT-PMP、用户 DNAT/SNAT、NAS/PC 服务以及无关端口继续由原 Firewall Policy 管理。

兼容性硬规则包括：

- BusyBox/POSIX `/bin/sh` Baseline；
- `rc.common`，有 procd 时优先使用，必要时使用 PID-owned fallback；
- `opkg` / `apk` 独立检测；
- Native Mapper 按精确 Package ABI 选择；
- Router 不要求现场 Compiler；
- 某个 Optional Capability 缺失时只降级该能力，不应拖垮无关 Direct/Gate 功能。

OpenWrt/ImmortalWrt 21.02 类 fw3 设备只是已完成硬件验证的 Sample，不是最低版本号。

## Dashboard 统一组件模型

Dashboard 遵循 [`DESIGN.md`](../DESIGN.md) 和 `awesome-design-md` 方法论。

Access Endpoint 与 Internet Exit 复用同一个结构化 Picker/Card Primitive：

```text
PathCard
  -> IPv4 或 IPv6：1 个 FamilyPathBlock
  -> Dual：2 个 FamilyPathBlock
```

Dual 固定由两个 Family Block/四行信息表达；same-WAN 与 split-WAN 使用同一 DOM，不再额外堆叠 `Split WAN` / `Split Exit` 文案。

长 IPv6、Endpoint、WAN Identity 只使用共享 `fit-text.js` NetworkIdentityText Engine。禁止再做 IPv6/WAN/Dual 专用缩放工具。

## 控制面 / 数据面流程

1. 登录 Cloudflare 前置 Dashboard。
2. VPS 保存当前已认证 HTTP Source Evidence；Browser 可 Best-effort 用 Carrier Candidate 补齐缺失 Family。
3. Dashboard 自动提出 AccessPlan 与 InternetExitPlan，用户可以分别 Override。
4. 只有显式点击 `Activate` 才会创建短生命周期 Command Transaction。
5. OpenWrt 通过出站 HTTPS Pull Command。
6. OpenWrt 用当前本机 Runtime 再次验证 WAN/device、Service/Ingress Identity 和 TTL。
7. Access Gate 只给解析出的 Remote Source 开放选定 Registered Ingress。
8. Mapped Activate 时会再次解析**当前** Mapping，不继承旧 Mapping 的授权。
9. 选择 Internet Exit 时，由独立 Egress Helper 校验并安装临时 Family-scoped Route/NAT Plan。
10. TTL 或 **Close access now** 清理 Gate Authorization 与临时 Internet Exit；Mapping 可以继续保持 CLOSED/受保护。

Cloudflare Hostname 是**控制面**；Direct/Mapped/Relay Endpoint 是**数据面**。不要把 Cloudflare Tunnel Hostname 当 WireGuard UDP Endpoint。

## 仓库流程与验证分层

```text
dev  -> 开发、修复、Routine CI
main -> 已验证稳定状态
```

日常开发只使用固定 `dev`，不创建 `dev/*`、`feature/*`、版本或临时开发分支；Commit Message 只写英文，禁止 Force Update Ref。

`dev` 上的 Routine `v0.3.x CI` 保持轻量：Python Contract/Compile、Shell Syntax、Native Mapper Host Build/Check 和 JavaScript Syntax。完整 Linux + Windows Chromium **Release Browser Validation** 属于单独的 `main`-only / Manual Release Layer。

验证层级不能互相冒充：

```text
contract/static test
browser regression
CI
runtime simulation
real hardware
```

只有用户从真实设备提供的结果才能记录为 Hardware PASS。

## 当前真实硬件验证边界

当前 fw3 / iptables-legacy / ipset Baseline 已完成：

- IPv4 Mapped Gate CLOSED -> 显式 Activate -> 外部新 WireGuard Handshake -> Close/CLOSED 生命周期；
- WireGuard Internet Exit ACTIVE 时的 Client Source Feedback-loop 防护；
- PPPoE Reconnect -> 旧 Mapping 消失 -> 有界 Settle -> 新 Mapping 自动建立 -> Gate 仍 CLOSED -> 再次显式 Activate -> 新 Handshake 成功；
- 当前真实设备 IPv4 Client / Access Endpoint / Internet Exit / WAN Dashboard 数据与默认选择反馈正常。

仍需单独 Hardware Validation：

- 手动 Endpoint Selection 在 Refresh/Topology Change 后的持久性；
- 显式启用后的 IPv6 Gate；
- same-WAN Dual Data Plane；
- split-WAN Dual + per-family Internet Exit Data Plane；
- 真实 fw4/nftables 设备上的 Mapped Access。

不能从 CI 或 Simulation 推导这些 Pending 项已经 PASS。权威矩阵见 [`docs/CURRENT-DEVICE-VALIDATION.md`](../docs/CURRENT-DEVICE-VALIDATION.md)。

## 更新、卸载与诊断

VPS 本机 Updater：

```sh
/usr/local/lib/remote-gate/update.sh
```

OpenWrt Updater 与 Read-only Diagnostic 安装在 `/usr/lib/remote-gate/`。升级保留用户配置/凭据，备份 Remote Gate 自有状态，替换前做验证，失败则 Rollback。Mapper Binary 缺失/ABI 不支持时只让 Mapped 变为 unavailable，不能破坏无关 Remote Gate 功能。

常用只读检查：

```sh
/usr/lib/remote-gate/remote-gate-platform.sh summary
/usr/lib/remote-gate/remote-gate-audit.sh
/usr/lib/remote-gate/remote-gate-firewall.sh detect
/usr/lib/remote-gate/remote-gate-firewall.sh status-json
/usr/lib/remote-gate/remote-gate-mapping.sh status-json
/usr/lib/remote-gate/remote-gate-wireguard-egress.sh status-json
```

Uninstall 只移除 Remote Gate 自己拥有的 Resource，不会盲目恢复旧整份 Firewall Snapshot，也不会默认删除 WireGuard。

## License

GPL-3.0-only.
