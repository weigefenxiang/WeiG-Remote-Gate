import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "server/app/static/js/app.js").read_text(encoding="utf-8")
GATE = (ROOT / "server/app/static/js/gate-controls.js").read_text(encoding="utf-8")


class AccessCapabilityContractTests(unittest.TestCase):
    def test_private_cgnat_is_not_a_user_access_endpoint(self):
        self.assertIn("['direct', 'mapped', 'egress_probe'].includes(item.reachability)", APP)
        self.assertIn("['direct','mapped','egress_probe'].includes(item.reachability)", GATE)
        self.assertNotIn("Private/CGNAT · Try", APP)
        self.assertNotIn("Private/CGNAT · Try", GATE)

    def test_family_controls_follow_gate_capabilities(self):
        self.assertIn("if (family === 'ipv6') return gateCapability('ipv6');", GATE)
        self.assertIn("if (family === 'dual') return gateCapability('ipv4') && gateCapability('ipv6');", GATE)
        self.assertIn("button.disabled = !selectable", GATE)
        self.assertIn("button.disabled||transactionLocked()||!familySelectable", GATE)

    def test_unavailable_manual_family_falls_back(self):
        self.assertIn("state.familyManual && familySelectable(state.family)", GATE)
        self.assertIn("if (familySelectable('ipv4')) return 'ipv4';", GATE)


if __name__ == "__main__":
    unittest.main()
