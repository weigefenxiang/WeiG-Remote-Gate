import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"
PICKER = ROOT / "server/app/static/js/endpoint-picker.js"
APP = ROOT / "server/app/static/js/app.js"


class InternetExitOwnerContractTests(unittest.TestCase):
    def test_internet_exit_has_one_mode_first_owner(self):
        gate = GATE.read_text(encoding="utf-8")
        app = APP.read_text(encoding="utf-8")
        self.assertIn("const egressState = {byAccessFamily:{}}", gate)
        self.assertIn("egress-mode-segment", gate)
        self.assertIn("egress-ipv4-select", gate)
        self.assertIn("egress-ipv6-select", gate)
        self.assertIn("function preferredSharedEgressWan()", gate)
        self.assertIn("function preferredEgressWans()", gate)
        self.assertIn("function selectedEgressPlan()", gate)
        self.assertNotIn("function egressPlans()", gate)
        self.assertNotIn("dual.slice(0, 64)", gate)
        self.assertNotIn("egressSelections", app)
        self.assertNotIn("get egressWan()", app)
        self.assertNotIn("set egressWan(value)", app)

    def test_shared_picker_preserves_consumer_semantics_and_old_exit_path_is_gone(self):
        picker = PICKER.read_text(encoding="utf-8")
        self.assertIn("function isEgressSelect(selectId)", picker)
        self.assertIn("Object.entries(label.dataset).forEach", picker)
        self.assertIn("wrapper.dataset[key] = value", picker)
        self.assertNotIn("MutationObserver", picker)
        self.assertNotIn("renderLanOption", picker)
        self.assertNotIn("__lan__", picker)

    def test_ready_family_state_is_quiet(self):
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("note.hidden = !reason", gate)
        self.assertNotIn("gate.familyReady", gate)


if __name__ == "__main__":
    unittest.main()
