import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = (ROOT / "server/app/static/js/gate-controls.js").read_text(encoding="utf-8")
PICKER = (ROOT / "server/app/static/js/endpoint-picker.js").read_text(encoding="utf-8")
CSS = (ROOT / "server/app/static/css/interaction.css").read_text(encoding="utf-8")
DESIGN = (ROOT / "DESIGN.md").read_text(encoding="utf-8")


class PathCardContractTests(unittest.TestCase):
    def test_gate_serializes_shared_path_rows(self):
        self.assertIn("option.dataset.pathRows = JSON.stringify(rows || [])", GATE)
        self.assertIn("pathRow('ipv4', pair.wan4", GATE)
        self.assertIn("pathRow('ipv6', pair.wan6", GATE)
        self.assertNotIn("Dual · Split WAN", GATE)
        self.assertNotIn("Dual · Split Exit", GATE)

    def test_picker_renders_one_or_two_family_blocks(self):
        self.assertIn("function pathRows(option)", PICKER)
        self.assertIn("rows.length > 2", PICKER)
        self.assertIn("class=\"path-family-block\"", PICKER)
        self.assertIn("data-fit-profile=\"identity\"", PICKER)
        self.assertIn("data-fit-profile=\"compact\"", PICKER)

    def test_path_card_css_is_generic_not_dual_specific(self):
        self.assertIn(".path-family-block", CSS)
        self.assertIn(".path-family-head", CSS)
        self.assertIn(".path-family-value", CSS)
        self.assertNotIn(".dual-card", CSS)
        self.assertNotIn(".split-wan-card", CSS)

    def test_design_declares_shared_path_card(self):
        self.assertIn("PathCard", DESIGN)
        self.assertIn("FamilyPathBlock", DESIGN)


if __name__ == "__main__":
    unittest.main()
