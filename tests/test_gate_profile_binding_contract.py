import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"
APP = ROOT / "server/app/static/js/app.js"
QUEUE = ROOT / "server/app/gate.py"
SERVER = ROOT / "server/remote-gate.py"
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
        self.assertIn("sourceAuthorized(fw, item) && activeProfileMatchesSelection(fw, item)", source)

    def test_mapped_profile_never_uses_external_port_as_ingress_authority(self):
        source = GATE.read_text(encoding="utf-8")
        body = source.split("function endpointIngressPort(item)", 1)[1].split("function selectedEndpointForFamily", 1)[0]
        self.assertIn("const candidates = method === 'mapped'", body)
        self.assertIn("? [item?.ingress_port, item?.local_port]", body)
        self.assertIn(": [item?.ingress_port, item?.service_port, item?.local_port, item?.external_port]", body)

    def test_active_runtime_is_global_and_dual_partial_is_close_only(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("function expectedRuntimeFamilies(family)", source)
        self.assertIn("function activeRuntimeFamilies(fw)", source)
        self.assertIn("function hasActiveRuntime(fw)", source)
        self.assertIn("function partialDualRuntime(fw, family)", source)
        self.assertIn("function conflictingActiveRuntime(fw, family)", source)
        self.assertIn("if (hasActiveRuntime(fw)) return false;", source)
        self.assertIn("closeRequired = hasActiveRuntime(fw)", source)
        self.assertIn("OPEN · PARTIAL ACCESS", source)
        self.assertIn("PARTIAL OPEN", source)
        self.assertIn("OPEN · OTHER ACCESS PATH", source)
        self.assertIn("if(agentFresh()&&hasActiveRuntime(fw)) closeAccess(); else activate();", source)
        self.assertNotIn("function conflictingActiveProfile", source)

    def test_access_profile_identity_stays_independent_from_internet_exit(self):
        source = GATE.read_text(encoding="utf-8")
        body = source.split("function selectedFamilyProfile(family)", 1)[1].split("function firewallFamilyProfile", 1)[0]
        self.assertIn("device:String(endpoint.device || '')", body)
        self.assertIn("ingressPort:endpointIngressPort(endpoint)", body)
        self.assertIn("scope:String(context?.state?.scope || 'wg')", body)
        self.assertNotIn("egress", body.lower())

    def test_failed_dashboard_refresh_revokes_cached_browser_authority(self):
        app = APP.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("dashboardAvailable: false", app)
        self.assertIn("state.dashboardAvailable = true", app)
        self.assertIn("state.dashboardAvailable = false", app)
        self.assertIn("RemoteGateGateControls?.render(state.data)", app)
        self.assertIn("context?.state?.dashboardAvailable && currentData?.agent?.fresh", gate)
        self.assertIn("const fw = fresh ? (currentData?.agent?.firewall || {}) : {};", gate)
        self.assertNotIn("Date.now()", gate.split("function agentFresh", 1)[1].split("function staleCloseRecommended", 1)[0])

    def test_server_queue_enforces_close_before_replacement_activate(self):
        source = QUEUE.read_text(encoding="utf-8")
        self.assertIn("def _gate_runtime_active(store: JsonStore) -> bool:", source)
        self.assertIn("def _require_gate_closed_for_activate(store: JsonStore) -> None:", source)
        self.assertIn('raise GateError("gate_close_required")', source)
        self.assertEqual(source.count("_require_gate_closed_for_activate(store)"), 2)

    def test_close_required_conflict_refreshes_browser_runtime_authority(self):
        server = SERVER.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("code = str(exc)", server)
        self.assertIn('409 if code in {"command_pending", "gate_close_required"} else 400', server)
        self.assertIn("function requestError(code)", gate)
        self.assertIn("gate_close_required", gate)
        self.assertIn("已有远程访问仍在运行", gate)
        self.assertIn("Remote access is already active", gate)
        submit = gate.split("async function submit(path, body, action)", 1)[1].split("function activate()", 1)[0]
        self.assertIn("let errorCode='';", submit)
        self.assertIn("errorCode=String(payload?.error||`HTTP ${response.status}`);", submit)
        self.assertIn("throw new Error(requestError(errorCode));", submit)
        self.assertIn("clearTransaction();", submit)
        self.assertIn("if(errorCode==='gate_close_required') window.RemoteGateApp?.refresh?.();", submit)

    def test_browser_regression_covers_profile_source_family_partial_and_refresh_conflicts(self):
        source = BROWSER.read_text(encoding="utf-8")
        self.assertIn("listen_port: 41194", source)
        self.assertIn("selectOption('WG_ALT')", source)
        self.assertIn("[data-scope=\"wg_ping\"]", source)
        self.assertIn("[data-family=\"ipv6\"]", source)
        self.assertIn("198.51.100.44", source)
        self.assertIn("OPEN · PARTIAL ACCESS", source)
        self.assertIn("PARTIAL OPEN", source)
        self.assertIn("STATUS UNKNOWN", source)
        self.assertIn("failDashboard", source)
        self.assertIn("activatePosts() === 0", source)

    def test_browser_execution_remains_release_only(self):
        core = CORE_CI.read_text(encoding="utf-8")
        release = RELEASE_CI.read_text(encoding="utf-8")
        self.assertIn("node --check tests/browser_gate_profile_binding.mjs", core)
        self.assertNotIn("node tests/browser_gate_profile_binding.mjs", core)
        self.assertIn("node tests/browser_gate_profile_binding.mjs", release)
        self.assertIn("if: github.ref == 'refs/heads/main'", release)


if __name__ == "__main__":
    unittest.main()
