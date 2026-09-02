import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = (ROOT / "server/app/static/js/gate-controls.js").read_text(encoding="utf-8")
BROWSER = (ROOT / "tests/browser_egress_manual.mjs").read_text(encoding="utf-8")


class ManualEgressUiContractTests(unittest.TestCase):
    def test_manual_exit_has_family_scoped_remembered_state(self):
        self.assertIn("function rememberEgressSelection", GATE)
        self.assertIn("state.egressSelections[family] = value", GATE)
        self.assertIn("state.egressManualSelections[family] = true", GATE)
        self.assertIn("state.egressWan = value", GATE)
        self.assertIn("if(!state.egressSelections||typeof state.egressSelections!=='object')state.egressSelections={};", GATE)

    def test_exit_change_records_intent_before_render(self):
        handler = "egressSelect()?.addEventListener('change',()=>{if(transactionLocked())return;rememberEgressSelection(state.family);render();});"
        self.assertIn(handler, GATE)

    def test_invalid_remembered_exit_is_fully_discarded(self):
        self.assertIn("state.egressManualSelections[family] = false;", GATE)
        self.assertIn("delete state.egressSelections[family];", GATE)

    def test_browser_regression_covers_retention_family_restore_and_invalidation(self):
        self.assertIn("manual IPv4 Internet Exit was overwritten by its own render", BROWSER)
        self.assertIn("manual IPv4 Internet Exit was not restored after family switching", BROWSER)
        self.assertIn("invalid manual Internet Exit did not fail back to a current plan", BROWSER)
        self.assertIn("invalidated manual Internet Exit reappeared after topology recovery", BROWSER)
        self.assertIn("activatePosts === 0", BROWSER)


if __name__ == "__main__":
    unittest.main()
