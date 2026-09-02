import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_CSS = ROOT / "server/app/static/css/base.css"
COMPONENTS_CSS = ROOT / "server/app/static/css/components.css"
PICKER = ROOT / "server/app/static/js/endpoint-picker.js"
GATE = ROOT / "server/app/static/js/gate-controls.js"
BROWSER_MATRIX = ROOT / ".github/workflows/browser-matrix.yml"


class VisibilityContractTests(unittest.TestCase):
    def test_hidden_attribute_is_stronger_than_component_display_rules(self):
        base = BASE_CSS.read_text(encoding="utf-8")
        components = COMPONENTS_CSS.read_text(encoding="utf-8")
        self.assertIn("[hidden] { display: none !important; }", base)
        self.assertIn(".field { display: grid; gap: 6px; }", components)

    def test_wireguard_visibility_has_one_presentation_owner(self):
        picker = PICKER.read_text(encoding="utf-8")
        body = picker.split("function syncWireGuardSelectorVisibility()", 1)[1].split("function sync(selectId", 1)[0]
        self.assertIn("serviceCount <= 1", body)
        self.assertIn("field.hidden = redundant", body)
        self.assertIn("select.tabIndex = redundant ? -1 : 0", body)
        self.assertNotIn("MutationObserver", body)

    def test_internet_exit_uses_the_same_hidden_attribute_contract(self):
        gate = GATE.read_text(encoding="utf-8")
        body = gate.split("function syncEgressControl()", 1)[1].split("function selectedEgressPlan()", 1)[0]
        self.assertIn("wrapper.hidden = !(", body)
        self.assertIn("preference.mode === 'dual'", body)
        self.assertNotIn("style.display", body)

    def test_windows_browser_fixture_and_regressions_share_one_step_lifetime(self):
        workflow = BROWSER_MATRIX.read_text(encoding="utf-8")
        self.assertIn("Windows browser matrix with fixture", workflow)
        windows = workflow.split("- name: Windows browser matrix with fixture", 1)[1].split("- name: Browser layout regression", 1)[0]
        self.assertIn("Start-Process python", windows)
        self.assertIn("Invoke-WebRequest", windows)
        self.assertIn("node tests/browser_layout.mjs", windows)
        self.assertIn("node tests/browser_mixed_egress.mjs", windows)
        self.assertIn("finally", windows)
        self.assertIn("Stop-Process", windows)
        self.assertNotIn("RUNNER_TRACKING_ID", workflow)
        self.assertNotIn("Verify fixture survives Windows step boundary", workflow)


if __name__ == "__main__":
    unittest.main()
