import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = (ROOT / "server/app/static/js/gate-controls.js").read_text(encoding="utf-8")
APP = (ROOT / "server/app/static/js/app.js").read_text(encoding="utf-8")
PICKER = (ROOT / "server/app/static/js/endpoint-picker.js").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "server/app/static/js/theme-bootstrap.js").read_text(encoding="utf-8")
BROWSER_LAYOUT = (ROOT / "tests/browser_layout.mjs").read_text(encoding="utf-8")
BROWSER_PLAN = (ROOT / "tests/browser_plan_preferences.mjs").read_text(encoding="utf-8")
BROWSER_SPLIT = (ROOT / "tests/browser_split_dual.mjs").read_text(encoding="utf-8")
BROWSER_MATRIX = (ROOT / ".github/workflows/browser-matrix.yml").read_text(encoding="utf-8")


class EndpointSelectionContractTests(unittest.TestCase):
    def test_automatic_scalar_selection_behavior_is_browser_owned(self):
        for behavior in (
            "best public IPv4 endpoint was not selected automatically",
            "automatic IPv6 endpoint did not enable Activate",
            "Access WAN change rewrote independent IPv6 Internet Exit",
            "Dual scalar endpoint_ids are incorrect",
        ):
            self.assertIn(behavior, BROWSER_LAYOUT)
        self.assertIn("two independent Access selectors", BROWSER_SPLIT)

    def test_manual_override_restore_and_method_fallback_are_browser_owned(self):
        for behavior in (
            "manual endpoint selection published duplicate preference events",
            "same-WAN method-aware fallback did not refresh the Mapped endpoint id",
            "same-WAN method-aware fallback silently changed Access method",
            "invalid manual endpoint preference was not cleared",
            "same-WAN method churn posted Activate",
        ):
            self.assertIn(behavior, BROWSER_PLAN)

    def test_legacy_dual_pair_and_secondary_policy_owners_are_absent(self):
        current = GATE + "\n" + APP + "\n" + PICKER + "\n" + BOOTSTRAP
        for stale in (
            "syncDualEndpointSelect",
            "dualEndpointPairs",
            "selectedDualPair",
            "pair.wan4",
            "pair.wan6",
            "endpointSelectionRecord('dual'",
            "option.dataset.ipv4EndpointId",
            "option.dataset.ipv6EndpointId",
        ):
            self.assertNotIn(stale, current)
        for stale_owner in (
            "function reachableEndpoints",
            "function rewriteMappedOptions",
            "function observeMappedPicker",
        ):
            self.assertNotIn(stale_owner, APP + "\n" + BOOTSTRAP)

    def test_browser_matrix_executes_selection_behavior_owners(self):
        self.assertIn("node tests/browser_layout.mjs", BROWSER_MATRIX)
        self.assertIn("node tests/browser_plan_preferences.mjs", BROWSER_MATRIX)
        self.assertIn("node tests/browser_split_dual.mjs", BROWSER_MATRIX)


if __name__ == "__main__":
    unittest.main()
