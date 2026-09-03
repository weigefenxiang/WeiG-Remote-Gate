import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"
PICKER = ROOT / "server/app/static/js/endpoint-picker.js"
APP = ROOT / "server/app/static/js/app.js"
INTERACTION = ROOT / "server/app/static/css/interaction.css"


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

    def test_exit_policy_never_reuses_access_pair_or_port_identity(self):
        gate = GATE.read_text(encoding="utf-8")
        egress = gate.split("function wanSupportsEgress", 1)[1].split("function sourceFor", 1)[0]
        self.assertIn("function egressCandidates", egress)
        self.assertIn("function preferredSharedEgressWan", egress)
        self.assertIn("pathRow(family, item.wan.name, '', item.address)", egress)
        self.assertNotIn("dualEndpointPairs", gate)
        self.assertNotIn("external_port", egress)
        self.assertNotIn("ingress_port", egress)
        self.assertNotIn("service_port", egress)

    def test_access_and_exit_share_one_generic_responsive_family_grid(self):
        css = INTERACTION.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn(".family-selectors {", css)
        self.assertIn("repeat(auto-fit,minmax(min(300px,100%),1fr))", css)
        self.assertIn(".family-selectors > .field", css)
        self.assertIn("family-selectors access-family-selectors", gate)
        self.assertIn("family-selectors egress-family-selectors", gate)
        self.assertNotIn(".access-ipv6-select-picker-trigger", css)
        self.assertNotIn(".egress-ipv4-select-picker-trigger", css)
        self.assertNotIn(".egress-ipv6-select-picker-trigger", css)
        self.assertIn("wrapper.hidden = !(", gate)
        self.assertIn("preference.mode === 'dual'", gate)

    def test_exit_has_one_visible_heading_and_no_redundant_family_labels(self):
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("label.textContent = zh() ? '上网出口' : 'Internet Exit'", gate)
        self.assertIn("select.setAttribute('aria-label', family === 'ipv6' ? 'IPv6 Internet Exit' : 'IPv4 Internet Exit')", gate)
        self.assertNotIn("familyLabel.textContent", gate)
        self.assertNotIn("'IPv4 WAN'", gate)
        self.assertNotIn("'IPv6 WAN'", gate)

    def test_shared_picker_preserves_scalar_consumer_semantics_and_old_pair_path_is_gone(self):
        picker = PICKER.read_text(encoding="utf-8")
        css = INTERACTION.read_text(encoding="utf-8")
        self.assertIn("function isEgressSelect(selectId)", picker)
        self.assertIn("function isAccessSelect(selectId)", picker)
        self.assertIn("rows.length !== 1", picker)
        self.assertIn("Object.entries(label.dataset).forEach", picker)
        self.assertIn("wrapper.dataset[key] = value", picker)
        self.assertNotIn("MutationObserver", picker)
        self.assertNotIn("renderLanOption", picker)
        self.assertNotIn("__lan__", picker)
        self.assertNotIn(".path-family-block + .path-family-block", css)
        self.assertNotIn(".path-family-block-trigger + .path-family-block-trigger", css)

    def test_ready_family_state_is_quiet(self):
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("note.hidden = !reason", gate)
        self.assertNotIn("gate.familyReady", gate)


if __name__ == "__main__":
    unittest.main()
