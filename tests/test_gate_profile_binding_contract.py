import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"
BROWSER = ROOT / "tests/browser_gate_profile_binding.mjs"
CORE_CI = ROOT / ".github/workflows/v030-ci.yml"
RELEASE_CI = ROOT / ".github/workflows/browser-release.yml"


class GateProfileBindingContractTests(unittest.TestCase):
    def test_gate_open_requires_current_access_profile_identity(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("function selectedFamilyProfile(family)", source)
        self.assertIn("function firewallFamilyProfile(fw, family)", source)
        self.assertIn("function activeProfileMatchesSelection(fw, family)", source)
        self.assertIn("runtime.device === selected.device", source)
        self.assertIn("runtime.ingressPort === selected.ingressPort", source)
        self.assertIn("runtime.scope === selected.scope", source)
        self.assertIn("sourceAuthorized(fw, family) && activeProfileMatchesSelection(fw, family)", source)

    def test_mapped_profile_never_uses_external_port_as_ingress_authority(self):
        source = GATE.read_text(encoding="utf-8")
        body = source.split("function endpointIngressPort(item)", 1)[1].split("function selectedEndpointForFamily", 1)[0]
        self.assertIn("const candidates = method === 'mapped'", body)
        self.assertIn("? [item?.ingress_port, item?.local_port]", body)
        self.assertIn(": [item?.ingress_port, item?.service_port, item?.local_port, item?.external_port]", body)

    def test_conflicting_profile_is_close_only_not_replacement_activate(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("function conflictingActiveProfile(fw, family)", source)
        self.assertIn("if (activeFamilyState(fw, state.family) || conflictingActiveProfile(fw, state.family)) return false;", source)
        self.assertIn("profileConflict = conflictingActiveProfile(fw, state.family)", source)
        self.assertIn("closeRequired = active || profileConflict", source)
        self.assertIn("OPEN · OTHER ACCESS PATH", source)
        self.assertIn("setLockedControls(locked, action, closeRequired, activatable, currentData)", source)
        self.assertIn("if(activeFamilyState(fw,context.state.family)||conflictingActiveProfile(fw,context.state.family)) closeAccess(); else activate();", source)

    def test_browser_regression_covers_scope_and_wireguard_profile_conflicts(self):
        source = BROWSER.read_text(encoding="utf-8")
        self.assertIn("ingress_port: 51820", source)
        self.assertIn("listen_port: 41194", source)
        self.assertIn("selectOption('WG_ALT')", source)
        self.assertIn("[data-scope=\"wg_ping\"]", source)
        self.assertIn("OPEN · OTHER ACCESS PATH", source)
        self.assertIn("OPEN ELSEWHERE", source)
        self.assertIn("Close access now", source)
        self.assertIn("activatePosts === 0", source)

    def test_browser_execution_remains_release_only(self):
        core = CORE_CI.read_text(encoding="utf-8")
        release = RELEASE_CI.read_text(encoding="utf-8")
        self.assertIn("node --check tests/browser_gate_profile_binding.mjs", core)
        self.assertNotIn("node tests/browser_gate_profile_binding.mjs", core)
        self.assertIn("node tests/browser_gate_profile_binding.mjs", release)
        self.assertIn("if: github.ref == 'refs/heads/main'", release)


if __name__ == "__main__":
    unittest.main()
