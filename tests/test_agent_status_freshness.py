import unittest
from pathlib import Path

from server.app.client_sources import (
    AGENT_STATUS_FRESH_SECONDS,
    agent_status_is_fresh,
    fail_closed_agent_status,
)

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server/remote-gate.py"
MAIN = ROOT / "server/app/main.py"
APP = ROOT / "server/app/static/js/app.js"
GATE_CONTROLS = ROOT / "server/app/static/js/gate-controls.js"
AGENT = ROOT / "openwrt/remote-gate-agent.sh"


class AgentStatusFreshnessTests(unittest.TestCase):
    def sample(self, reported_at=1000):
        return {
            "schema": 3,
            "reported_at": reported_at,
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820}],
            "firewall": {
                "backend": "fw3-iptables",
                "ready": True,
                "ipv6_capable": True,
                "active": True,
                "family": "ipv4",
                "scope": "wg",
                "expires_in": 300,
                "source_ip": "1.1.1.1",
                "device": "pppoe-WAN",
                "wg_port": 51820,
                "ingress_port": 54321,
                "families": {
                    "ipv4": {
                        "active": True,
                        "authorized_sources": ["1.1.1.1"],
                        "authorizations": [{"source_ip": "1.1.1.1", "expires_in": 300}],
                    }
                },
                "protected_devices_v4": 1,
                "protected_devices_v6": 0,
                "protected_ports": 1,
            },
            "egress": {
                "active": True,
                "state": "active",
                "mode": "ipv4",
                "wan": "WAN2",
                "wan_v4": "WAN2",
                "wg": "WG_HOME",
                "expires_in": 300,
            },
            "mapping": {"available": True, "state": "active", "active_mappings": 1},
            "transport": {
                "active_family": "ipv4",
                "active_device": "pppoe-WAN2",
                "healthy": True,
                "last_ok_at": 1000,
            },
        }

    def test_fresh_report_remains_authoritative(self):
        status = self.sample()
        self.assertTrue(agent_status_is_fresh(status, now=1000 + AGENT_STATUS_FRESH_SECONDS))
        view = fail_closed_agent_status(status, now=1000 + AGENT_STATUS_FRESH_SECONDS)
        self.assertTrue(view["fresh"])
        self.assertTrue(view["inventory_synced"])
        self.assertTrue(view["may_have_active_runtime"])
        self.assertTrue(view["firewall"]["active"])
        self.assertTrue(view["egress"]["active"])
        self.assertEqual(view["wireguard"][0]["name"], "WG_HOME")
        self.assertTrue(view["transport"]["healthy"])

    def test_stale_report_loses_all_runtime_authority_but_keeps_close_hint(self):
        status = self.sample()
        view = fail_closed_agent_status(status, now=1001 + AGENT_STATUS_FRESH_SECONDS)
        self.assertFalse(view["fresh"])
        self.assertTrue(view["inventory_synced"])
        self.assertTrue(view["may_have_active_runtime"])
        self.assertEqual(view["reported_at"], 1000)
        self.assertEqual(view["firewall"]["backend"], "fw3-iptables")
        self.assertFalse(view["firewall"]["ready"])
        self.assertFalse(view["firewall"]["active"])
        self.assertFalse(view["firewall"]["families"]["ipv4"]["active"])
        self.assertEqual(view["firewall"]["families"]["ipv4"]["authorized_sources"], [])
        self.assertEqual(view["wireguard"], [])
        self.assertFalse(view["egress"]["active"])
        self.assertEqual(view["egress"]["state"], "inactive")
        self.assertFalse(view["mapping"]["available"])
        self.assertEqual(view["mapping"]["state"], "unavailable")
        self.assertFalse(view["transport"]["healthy"])
        self.assertEqual(view["transport"]["active_family"], "")
        self.assertEqual(view["transport"]["active_device"], "")

    def test_stale_inactive_report_does_not_offer_close_hint(self):
        status = self.sample()
        status["firewall"]["active"] = False
        status["firewall"]["families"]["ipv4"]["active"] = False
        status["egress"]["active"] = False
        status["egress"]["state"] = "inactive"
        view = fail_closed_agent_status(status, now=1001 + AGENT_STATUS_FRESH_SECONDS)
        self.assertFalse(view["fresh"])
        self.assertFalse(view["may_have_active_runtime"])

    def test_inventory_unsynced_report_is_never_authoritative(self):
        status = self.sample()
        status["inventory_synced"] = False
        self.assertFalse(agent_status_is_fresh(status, now=1000))
        view = fail_closed_agent_status(status, now=1000)
        self.assertFalse(view["fresh"])
        self.assertFalse(view["inventory_synced"])
        self.assertTrue(view["may_have_active_runtime"])
        self.assertFalse(view["firewall"]["active"])
        self.assertEqual(view["wireguard"], [])
        self.assertEqual(view["egress"]["detail"], "inventory_unsynced")
        self.assertEqual(view["mapping"]["detail"], "inventory_unsynced")

    def test_future_report_outside_skew_window_is_not_authoritative(self):
        status = self.sample(reported_at=2000)
        self.assertFalse(agent_status_is_fresh(status, now=1000))
        self.assertFalse(fail_closed_agent_status(status, now=1000)["fresh"])

    def test_dashboard_projects_agent_without_mutating_raw_report(self):
        base = MAIN.read_text(encoding="utf-8")
        dashboard = base.split('if path == "/api/v1/dashboard":', 1)[1].split('if path == "/api/v1/agent/pull":', 1)[0]
        self.assertIn('raw_agent = STORE.read("agent-status.json", {})', dashboard)
        self.assertIn("agent = fail_closed_agent_status(raw_agent)", dashboard)
        self.assertIn('gate["agent"] = agent', dashboard)
        self.assertIn('"agent": agent', dashboard)

        production = SERVER.read_text(encoding="utf-8")
        self.assertNotIn("_sanitize_stored_agent_status", production)
        production_get = production.split("def do_GET(self) -> None:", 1)[1].split("def _candidate_post(self) -> None:", 1)[0]
        self.assertNotIn('STORE.write("agent-status.json"', production_get)
        self.assertNotIn("fail_closed_agent_status", production_get)

    def test_system_status_consumes_server_freshness_without_browser_threshold(self):
        source = APP.read_text(encoding="utf-8")
        render_system = source.split("function renderSystem(data) {", 1)[1].split("function render(data) {", 1)[0]
        self.assertIn("const fresh = Boolean(data?.agent?.fresh);", render_system)
        self.assertNotIn("const reportedAt", render_system)
        self.assertNotIn("Date.now()", render_system)
        self.assertNotIn("< 45", render_system)

    def test_stale_gate_ui_disables_activate_but_keeps_safe_close(self):
        source = GATE_CONTROLS.read_text(encoding="utf-8")
        self.assertIn("function agentFresh(currentData = data())", source)
        self.assertIn("function staleCloseRecommended(currentData = data())", source)
        self.assertIn("Boolean(currentData?.agent?.may_have_active_runtime)", source)

        can_activate = source.split("function canActivate() {", 1)[1].split("function ensureDualButton() {", 1)[0]
        self.assertIn("!agentFresh()", can_activate)

        controls = source.split("function setLockedControls(", 1)[1].split("function render(currentData", 1)[0]
        self.assertIn("staleCloseRecommended(currentData)", controls)
        self.assertIn("(active || safeClose)", controls)

        render = source.split("function render(currentData = data()) {", 1)[1].split("async function submit(", 1)[0]
        self.assertIn("else if (!fresh)", render)
        stale_branch = render.split("else if (!fresh)", 1)[1].split("else if (recentTerminalFailure(last))", 1)[0]
        self.assertIn("STATUS UNKNOWN", stale_branch)
        self.assertIn("staleCloseRecommended", source)
        self.assertNotIn("mode='open'", stale_branch)
        self.assertNotIn("title=t('gate.open')", stale_branch)

    def test_activate_requires_fresh_agent_but_close_remains_deliverable(self):
        source = SERVER.read_text(encoding="utf-8")
        activate = source.split("def _activate_post(self) -> None:", 1)[1].split("def _inventory_post(self) -> None:", 1)[0]
        self.assertIn('agent_status_is_fresh(STORE.read("agent-status.json", {}))', activate)
        self.assertIn('self._json(503, {"error": "agent_unavailable"})', activate)
        self.assertLess(
            activate.index('agent_status_is_fresh(STORE.read("agent-status.json", {}))'),
            activate.index("observe_source(STORE, session.token, current_source)"),
        )

        production_post = source.split("def do_POST(self) -> None:", 1)[1].split("def run() -> None:", 1)[0]
        self.assertNotIn('if path == "/api/v1/gate/close":', production_post)
        self.assertIn("super().do_POST()", production_post)

        base = MAIN.read_text(encoding="utf-8")
        close_route = base.split('if path == "/api/v1/gate/close":', 1)[1].split('if path == "/api/v1/update":', 1)[0]
        self.assertIn("queue_close(STORE, source_ip=source)", close_route)
        self.assertNotIn("agent_status_is_fresh", close_route)

    def test_status_api_persists_boolean_inventory_sync_authority(self):
        source = SERVER.read_text(encoding="utf-8")
        status_post = source.split("def _agent_status_post(self) -> None:", 1)[1].split("def do_POST(self) -> None:", 1)[0]
        self.assertIn('data.get("inventory_synced", True)', status_post)
        self.assertIn("isinstance(inventory_synced_raw, bool)", status_post)
        self.assertIn('"inventory_synced": inventory_synced', status_post)

    def test_agent_only_pulls_after_inventory_sync_and_reports_fail_closed_state(self):
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn('payload="{\\"schema\\":3,\\"inventory_synced\\":${inventory_synced}', source)

        report_only = source.split("report_only() {", 1)[1].split("run_once() {", 1)[0]
        self.assertIn("if maybe_post_inventory; then", report_only)
        self.assertIn("post_status true", report_only)
        self.assertIn("post_status false", report_only)

        run_once = source.split("run_once() {", 1)[1].split('case "${1:-once}"', 1)[0]
        self.assertIn("if ! maybe_post_inventory; then", run_once)
        self.assertIn("post_status false", run_once)
        self.assertIn("inventory not synchronized; command pull skipped", run_once)
        failure = run_once.split("if ! maybe_post_inventory; then", 1)[1].split("fi", 1)[0]
        self.assertNotIn("pull_once", failure)

    def test_status_publish_failure_allows_close_but_not_activate_execution(self):
        source = AGENT.read_text(encoding="utf-8")
        post_status = source.split("post_status() {", 1)[1].split("sanitize_detail() {", 1)[0]
        self.assertIn('[ "$CONTROL_CODE" = "204" ]', post_status)
        self.assertIn("agent status update failed", post_status)
        self.assertIn("return 1", post_status)

        pull_once = source.split("pull_once() {", 1)[1].split("report_only() {", 1)[0]
        self.assertIn('mode="${1:-all}"', pull_once)
        self.assertIn("all|close-only", pull_once)
        guard = 'if [ "$mode" = "close-only" ] && [ "$action" != "close" ]; then'
        self.assertIn(guard, pull_once)
        self.assertLess(pull_once.index(guard), pull_once.index('case "$action" in'))
        guard_block = pull_once.split(guard, 1)[1].split("fi", 1)[0]
        self.assertIn("return 0", guard_block)
        self.assertNotIn("ack ", guard_block)

        run_once = source.split("run_once() {", 1)[1].split('case "${1:-once}"', 1)[0]
        self.assertIn("pull_mode=all", run_once)
        self.assertIn("if ! post_status true; then", run_once)
        self.assertIn("pull_mode=close-only", run_once)
        self.assertIn('pull_once "$pull_mode"', run_once)


if __name__ == "__main__":
    unittest.main()
