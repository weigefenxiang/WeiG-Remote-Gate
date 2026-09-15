# Adaptive Agent Cadence

This note defines the control-plane cadence contract for WeiG Remote Gate. It does not change AccessPlan, InternetExitPlan, firewall authority, Mapping authority or Gate authorization semantics.

## Goals

The OpenWrt Agent must remain responsive to an explicit browser control action without continuously running the full inventory/status/report path when nobody is using the console.

The default cadence is:

- idle heavy report: 1800 seconds (30 minutes);
- interactive heavy report: 5 seconds while a short operator-activity lease is current;
- pending-command execution/convergence: 5 seconds;
- browser operator-activity lease: 120 seconds;
- VPS Agent status authority window: 7200 seconds (2 hours);
- Mapped UDP keepalive: 60 seconds;
- mapper diagnostic summary: 1800 seconds (30 minutes).

These are deployment defaults, not architectural constants. The bounded configuration values remain the source of the active cadence.

## Lightweight cadence check versus Agent work

`remote-gate-report.sh loop` owns scheduling. The service performs the lightweight authenticated `/api/v1/agent/cadence` check on the short command/interactive interval. That check only answers whether the next cycle is `idle`, `interactive` or `command`.

It does not replace `/api/v1/agent/pull`, execute a command, authorize a source, select an Access Endpoint or select an Internet Exit WAN. A `command` hint causes the existing Agent `once` path to perform its normal inventory/status publication, command pull, validation and OpenWrt-side execution.

When the hint is `idle`, the scheduler skips repeated heavy Agent work until the idle report interval elapses. This keeps explicit Activate/Close convergence responsive without turning the full Agent into a permanent five-second poller.

If the VPS does not expose the cadence endpoint during a rolling upgrade, the OpenWrt scheduler falls back to the historical responsive Agent cycle rather than becoming unable to receive commands.

## Operator activity

A valid authenticated console page load may seed the short activity lease. After that, only real browser interaction signals such as pointer, keyboard or control-change activity extend it. The dashboard's ordinary five-second refresh does not renew the lease.

The activity endpoint is a cadence hint only. It is not authorization evidence and must not become a source of truth for Gate state, client-source identity, endpoint eligibility or egress state.

A long Gate TTL, including the maximum 12-hour authorization, does not by itself keep the system in five-second interactive mode.

## Agent status freshness

The production VPS applies the configured Agent status authority window to the existing fail-closed freshness projection. The default is two hours so a 30-minute idle report cadence does not falsely mark a healthy idle router unavailable.

Freshness is still an authority boundary: once the configured window expires, cached WireGuard, firewall, egress, Mapping and transport runtime claims lose authority exactly as before. Increasing the window does not convert browser or VPS cache into runtime authority.

## Mapper keepalive and diagnostics

Mapped Access keeps its native UDP Mapping process independent from the Agent reporting cadence. The default mapper STUN keepalive becomes 60 seconds, within the native mapper's existing supported range.

Diagnostic state is stored under the project-owned `/tmp/remote-gate` runtime tree and therefore remains RAM-backed on normal OpenWrt systems. The scheduler observes mapper status files, records endpoint changes, and writes concise `mapping-change` events plus periodic summaries to OpenWrt `logd`.

The summary may report the current endpoint, last successful STUN age, stale indication and mapping-change count. These logs are diagnostics only; they never authorize a Mapping or replace the mapper process/status ownership checks used by the runtime.

Managed mapper processes are restarted only when the configured mapper runtime tuple (`keepalive`, `idle_timeout`, `max_sessions`) changes, or when another existing lifecycle path already requires a restart. Merely restarting the Remote Gate service with unchanged mapper runtime settings must not create needless mapper churn.

## Migration

Fresh installs no longer create the historical five-minute cron report entry. The adaptive scheduler removes that exact legacy entry when found.

Updates remove the old `AGENT_INTERVAL` configuration key. A legacy value of at least 60 seconds is preserved as the new idle interval; historical short polling values such as 10 seconds migrate to the 30-minute idle default. The short command/interactive checks remain separately configurable.

All cadence behavior is subordinate to the existing safety rules: OpenWrt remains runtime authority, Mapping existence is not Gate authorization, Access and Internet Exit remain independent plans, and no cadence transition may auto-Activate or migrate an active authorization.
