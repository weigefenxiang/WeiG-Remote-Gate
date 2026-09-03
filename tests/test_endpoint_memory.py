import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = (ROOT / "server/app/static/js/gate-controls.js").read_text(encoding="utf-8")
PLAN = (ROOT / "server/app/static/js/plan-preferences.js").read_text(encoding="utf-8")
BROWSER_PLAN = (ROOT / "tests/browser_plan_preferences.mjs").read_text(encoding="utf-8")
BROWSER_SERVICE = (ROOT / "tests/browser_plan_service_identity.mjs").read_text(encoding="utf-8")
BROWSER_MATRIX = (ROOT / ".github/workflows/browser-matrix.yml").read_text(encoding="utf-8")


class EndpointMemoryTests(unittest.TestCase):
    def test_legacy_dual_pair_persistence_is_absent_from_current_owners(self):
        source = PLAN + "\n" + GATE
        for stale in (
            "endpoints.dual",
            "endpointSelections.dual",
            "endpointManualSelections.dual",
            "syncDualEndpointSelect",
            "dualEndpointPairs",
            "selectedDualPair",
            "method4",
            "method6",
            "pair.wan4",
            "pair.wan6",
        ):
            self.assertNotIn(stale, source)

    def test_scalar_restore_fallback_and_invalidation_are_browser_owned(self):
        for behavior in (
            "manual endpoint selection published duplicate preference events",
            "WAN fallback did not refresh the persisted endpoint identity",
            "same-WAN method-aware fallback did not refresh the Mapped endpoint id",
            "invalid manual endpoint preference was not cleared",
            "Dual scalar IPv4 fallback did not refresh the endpoint id",
            "Dual scalar IPv6 preference was rewritten by IPv4 churn",
            "topology churn posted Activate",
            "Dual scalar method churn posted Activate",
        ):
            self.assertIn(behavior, BROWSER_PLAN)

    def test_service_bound_manual_hint_invalidation_is_browser_owned(self):
        for behavior in (
            "WG_HOME manual endpoint preference migrated across an explicit switch to WG_ALT",
            "WG_ALT manual endpoint preference lost its service binding",
            "stale WG_ALT manual endpoint preference survived service disappearance",
            "WireGuard service selection/churn posted Activate",
        ):
            self.assertIn(behavior, BROWSER_SERVICE)

    def test_browser_matrix_executes_endpoint_memory_owners(self):
        self.assertIn("node tests/browser_plan_preferences.mjs", BROWSER_MATRIX)
        self.assertIn("node tests/browser_plan_service_identity.mjs", BROWSER_MATRIX)


if __name__ == "__main__":
    unittest.main()
