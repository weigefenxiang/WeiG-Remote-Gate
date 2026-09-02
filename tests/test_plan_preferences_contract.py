import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = ROOT / "server/app/static/js/plan-preferences.js"
TEMPLATE = ROOT / "server/app/templates/dashboard.html"
GATE_CONTROLS = ROOT / "server/app/static/js/gate-controls.js"
CORE_CI = ROOT / ".github/workflows/v030-ci.yml"
BROWSER_CI = ROOT / ".github/workflows/browser-release.yml"
BROWSER_TEST = ROOT / "tests/browser_plan_preferences.mjs"


class PlanPreferenceContractTests(unittest.TestCase):
    def test_preference_adapter_loads_between_gate_policy_and_app_binding(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        gate = template.index("/static/js/gate-controls.js")
        preferences = template.index("/static/js/plan-preferences.js")
        app = template.index("/static/js/app.js")
        self.assertLess(gate, preferences)
        self.assertLess(preferences, app)

    def test_adapter_persists_only_non_authoritative_endpoint_intent(self):
        source = PREFERENCES.read_text(encoding="utf-8")
        self.assertIn("remote-gate:plan-preferences:v1", source)
        self.assertIn("endpointSelections", source)
        self.assertIn("endpointManualSelections", source)
        self.assertIn("remote-gate-endpoint-selection", source)
        self.assertIn("onWireGuardChange", source)
        self.assertIn("Browser storage is a convenience only; runtime authority never depends on it.", source)
        for forbidden in ("source_ip", "client_sources", "csrf", "expires_in", "/api/v1/gate/activate", "fetch("):
            self.assertNotIn(forbidden, source)

    def test_adapter_reuses_gate_controls_instead_of_implementing_endpoint_policy(self):
        source = PREFERENCES.read_text(encoding="utf-8")
        gate = GATE_CONTROLS.read_text(encoding="utf-8")
        self.assertIn("controls.bind", source)
        self.assertIn("controls.render", source)
        self.assertNotIn("endpointScore", source)
        self.assertNotIn("dualEndpointPairs", source)
        self.assertNotIn("reachability", source)
        self.assertIn("function endpointScore(item)", gate)
        self.assertIn("function restoreEndpointSelection", gate)

    def test_browser_regression_covers_reload_churn_invalidation_and_zero_auto_activate(self):
        source = BROWSER_TEST.read_text(encoding="utf-8")
        self.assertIn("page.reload", source)
        self.assertIn("topology = 'changed'", source)
        self.assertIn("topology = 'removed'", source)
        self.assertIn("activatePosts === 0", source)
        self.assertIn("ep-wan-v6-new", source)
        self.assertIn("ep-wan2-v6", source)

    def test_ci_contract_keeps_browser_regression_syntax_checked_and_release_only(self):
        core = CORE_CI.read_text(encoding="utf-8")
        release = BROWSER_CI.read_text(encoding="utf-8")
        self.assertIn("node --check tests/browser_plan_preferences.mjs", core)
        self.assertIn("node tests/browser_plan_preferences.mjs", release)
        self.assertIn("if: github.ref == 'refs/heads/main'", release)
        self.assertNotIn("playwright", core.lower())


if __name__ == "__main__":
    unittest.main()
