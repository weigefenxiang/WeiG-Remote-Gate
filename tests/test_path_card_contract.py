import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "server/app/static/js/app.js").read_text(encoding="utf-8")
GATE = (ROOT / "server/app/static/js/gate-controls.js").read_text(encoding="utf-8")
PICKER = (ROOT / "server/app/static/js/endpoint-picker.js").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "server/app/static/js/theme-bootstrap.js").read_text(encoding="utf-8")
CSS = (ROOT / "server/app/static/css/interaction.css").read_text(encoding="utf-8")
DESIGN = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
BROWSER_LAYOUT = (ROOT / "tests/browser_layout.mjs").read_text(encoding="utf-8")


class PathCardContractTests(unittest.TestCase):
    def test_scalar_access_path_rows_are_behavior_owned(self):
        for stale in (
            "pair.wan4", "pair.wan6", "dualEndpointPairs", "selectedDualPair",
            "syncDualEndpointSelect", "Dual · Split WAN", "Dual · Split Exit",
        ):
            self.assertNotIn(stale, GATE)
        self.assertIn("selectedBlocks === 1", BROWSER_LAYOUT)
        self.assertIn("scalar.blocks === 1", BROWSER_LAYOUT)
        self.assertIn("pairIds.length === 0", BROWSER_LAYOUT)

    def test_access_endpoint_policy_has_one_current_owner(self):
        for role in ("'Public Direct'", "'Global Direct'", "'Mapped'", "'Try'", "'Relay'"):
            self.assertIn(role, GATE)
        for stale in ("function reachableEndpoints", "function endpointLabel", "function syncEndpointSelect", "NAT egress · Try"):
            self.assertNotIn(stale, APP)
        for stale in ("function rewriteMappedOptions", "function observeMappedPicker", "parts.indexOf('Mapped')"):
            self.assertNotIn(stale, BOOTSTRAP)

    def test_picker_consumes_structured_rows_without_policy_ownership(self):
        self.assertIn("dataset?.pathRows", PICKER)
        self.assertIn("dataset?.pathPrimary", PICKER)
        for stale in ("MutationObserver", "splitLabel", "NAT egress · Try"):
            self.assertNotIn(stale, PICKER)
        self.assertIn("scalar.blocks === 1", BROWSER_LAYOUT)

    def test_path_card_css_is_generic_not_dual_specific(self):
        self.assertIn(".path-family-block", CSS)
        self.assertIn(".path-family-head", CSS)
        self.assertIn(".path-family-value", CSS)
        self.assertIn(".path-family-spacer", CSS)
        self.assertIn(".path-card-recommended", CSS)
        self.assertNotIn(".dual-card", CSS)
        self.assertNotIn(".split-wan-card", CSS)

    def test_design_declares_shared_path_card(self):
        self.assertIn("PathCard", DESIGN)
        self.assertIn("FamilyPathBlock", DESIGN)
        self.assertIn("theme-bootstrap", DESIGN)
        self.assertIn("must not re-filter, re-rank, relabel or store a second Access/Exit plan", DESIGN)


if __name__ == "__main__":
    unittest.main()
