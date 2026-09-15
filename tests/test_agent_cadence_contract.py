from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = (ROOT / "server" / "app" / "config.py").read_text(encoding="utf-8")
SERVER = (ROOT / "server" / "remote-gate.py").read_text(encoding="utf-8")
APP = (ROOT / "server" / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
REPORT = (ROOT / "openwrt" / "remote-gate-report.sh").read_text(encoding="utf-8")
INSTALL = (ROOT / "openwrt" / "install.sh").read_text(encoding="utf-8")
UPDATE = (ROOT / "openwrt" / "update.sh").read_text(encoding="utf-8")
INIT = (ROOT / "openwrt" / "remote-gate-agent.init").read_text(encoding="utf-8")


class AgentCadenceContractTests(unittest.TestCase):
    def test_vps_status_authority_and_operator_lease_are_configurable(self):
        self.assertIn('agent_status_fresh_seconds: int', CONFIG)
        self.assertIn('agent_web_activity_ttl: int', CONFIG)
        self.assertIn('"agent_status_fresh_seconds", 7200, 60, 86400', CONFIG)
        self.assertIn('"agent_web_activity_ttl", 120, 30, 3600', CONFIG)
        self.assertIn(
            'client_sources_module.AGENT_STATUS_FRESH_SECONDS = SETTINGS.agent_status_fresh_seconds',
            SERVER,
        )

    def test_cadence_endpoint_is_a_hint_not_the_command_pull_endpoint(self):
        get_block = SERVER.split('def do_GET(self) -> None:', 1)[1].split('def _candidate_post', 1)[0]
        self.assertIn('if path == "/api/v1/agent/cadence":', get_block)
        self.assertIn('pending = pull_command(STORE)', get_block)
        self.assertIn('mode = "command"', get_block)
        self.assertIn('mode = "interactive" if active_until else "idle"', get_block)
        self.assertNotIn('if path == "/api/v1/agent/pull":', get_block)

    def test_only_real_browser_interactions_extend_operator_activity(self):
        self.assertIn("async function signalOperatorActivity()", APP)
        self.assertIn("'/api/v1/operator/activity'", APP)
        self.assertIn("document.addEventListener('pointerdown', signalOperatorActivity", APP)
        self.assertIn("document.addEventListener('keydown', signalOperatorActivity", APP)
        self.assertIn("document.addEventListener('change', signalOperatorActivity", APP)
        refresh = APP.split("async function refresh()", 1)[1].split("function friendlyError", 1)[0]
        self.assertNotIn("signalOperatorActivity", refresh)

    def test_openwrt_separates_lightweight_checks_from_heavy_idle_reports(self):
        self.assertIn('AGENT_IDLE_INTERVAL="${AGENT_IDLE_INTERVAL:-1800}"', REPORT)
        self.assertIn('AGENT_INTERACTIVE_INTERVAL="${AGENT_INTERACTIVE_INTERVAL:-5}"', REPORT)
        self.assertIn('AGENT_COMMAND_INTERVAL="${AGENT_COMMAND_INTERVAL:-5}"', REPORT)
        self.assertIn('mode="$(cadence_mode', REPORT)
        scheduler = REPORT.split('scheduler_loop() {', 1)[1].split('case "${1:-report}"', 1)[0]
        self.assertIn('command)\n                "$AGENT" once', scheduler)
        self.assertIn('interactive)\n                if [ "$last_agent_run"', scheduler)
        self.assertIn('idle)\n                if [ "$last_agent_run"', scheduler)
        self.assertIn('next="$AGENT_COMMAND_INTERVAL"', scheduler)
        self.assertIn('procd_set_param command "$SCHEDULER_BIN" loop', INIT)

    def test_legacy_five_minute_cron_and_agent_interval_are_retired(self):
        self.assertNotIn('grep -Fqx "$CRON_LINE"', INSTALL)
        self.assertNotIn("AGENT_INTERVAL='10'", INSTALL)
        self.assertIn("LEGACY_CRON_LINE=", REPORT)
        self.assertIn("cleanup_legacy_cron", REPORT)
        self.assertIn("grep -Ev '^(AGENT_INTERVAL|NATMAP_DISCOVERY)='", UPDATE)

    def test_mapper_keepalive_and_ram_diagnostics_have_bounded_defaults(self):
        for source in (INSTALL, UPDATE, REPORT):
            self.assertIn("MAPPER_KEEPALIVE", source)
        self.assertIn("MAPPER_KEEPALIVE='60'", INSTALL)
        self.assertIn("append_default MAPPER_KEEPALIVE 60", UPDATE)
        self.assertIn("MAPPER_DIAGNOSTIC_SUMMARY_INTERVAL", REPORT)
        self.assertIn("mapping-change", REPORT)
        self.assertIn("summary key=", REPORT)
        self.assertIn('DIAG_DIR="$RUNTIME_DIR/mapper-diagnostics"', REPORT)
        self.assertIn("maybe_restart_mapper_for_config", REPORT)


if __name__ == "__main__":
    unittest.main()
