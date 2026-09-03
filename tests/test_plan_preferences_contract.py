import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = ROOT / "server/app/static/js/plan-preferences.js"
TEMPLATE = ROOT / "server/app/templates/dashboard.html"
CORE_CI = ROOT / ".github/workflows/v030-ci.yml"
RELEASE_CI = ROOT / ".github/workflows/browser-release.yml"
BROWSER_MATRIX_CI = ROOT / ".github/workflows/browser-matrix.yml"


class PlanPreferenceContractTests(unittest.TestCase):
    def test_preference_adapter_loads_between_gate_policy_and_app_binding(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        gate = template.index("/static/js/gate-controls.js")
        preferences = template.index("/static/js/plan-preferences.js")
        app = template.index("/static/js/app.js")
        self.assertLess(gate, preferences)
        self.assertLess(preferences, app)

    def test_adapter_is_non_authoritative_and_does_not_own_endpoint_policy(self):
        source = PREFERENCES.read_text(encoding="utf-8")
        self.assertIn("remote-gate:plan-preferences:v1", source)
        self.assertIn("remote-gate-endpoint-selection", source)
        self.assertIn("Browser storage is a convenience only; runtime authority never depends on it.", source)
        for forbidden in (
            "source_ip",
            "client_sources",
            "csrf",
            "expires_in",
            "/api/v1/gate/activate",
            "fetch(",
            "endpointScore",
            "reachability",
            "dualEndpointPairs",
            "selectedDualPair",
            "method4",
            "method6",
            "wan4",
            "wan6",
            "endpoints.dual",
        ):
            self.assertNotIn(forbidden, source)

    def test_browser_behavior_owners_are_executed_by_the_shared_matrix(self):
        core = CORE_CI.read_text(encoding="utf-8")
        release = RELEASE_CI.read_text(encoding="utf-8")
        matrix = BROWSER_MATRIX_CI.read_text(encoding="utf-8")

        self.assertIn("node --check tests/browser_plan_preferences.mjs", core)
        self.assertIn("node --check tests/browser_plan_service_identity.mjs", core)
        self.assertNotIn("node tests/browser_plan_preferences.mjs", core)
        self.assertNotIn("node tests/browser_plan_service_identity.mjs", core)

        self.assertIn("node tests/browser_plan_preferences.mjs", matrix)
        self.assertIn("node tests/browser_plan_service_identity.mjs", matrix)
        self.assertIn("uses: ./.github/workflows/browser-matrix.yml", release)
        self.assertIn("if: github.ref == 'refs/heads/main'", release)


if __name__ == "__main__":
    unittest.main()
