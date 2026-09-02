import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = ROOT / "server/app/static/js/plan-preferences.js"
TEMPLATE = ROOT / "server/app/templates/dashboard.html"
GATE_CONTROLS = ROOT / "server/app/static/js/gate-controls.js"
CORE_CI = ROOT / ".github/workflows/v030-ci.yml"
BROWSER_CI = ROOT / ".github/workflows/browser-release.yml"
BROWSER_MATRIX_CI = ROOT / ".github/workflows/browser-matrix.yml"
BROWSER_TEST = ROOT / "tests/browser_plan_preferences.mjs"
BROWSER_SERVICE_TEST = ROOT / "tests/browser_plan_service_identity.mjs"


class PlanPreferenceContractTests(unittest.TestCase):
    def test_preference_adapter_loads_between_gate_policy_and_app_binding(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        gate = template.index("/static/js/gate-controls.js")
        preferences = template.index("/static/js/plan-preferences.js")
        app = template.index("/static/js/app.js")
        self.assertLess(gate, preferences)
        self.assertLess(preferences, app)

    def test_adapter_persists_only_non_authoritative_endpoint_intent(self):
        source = PREFERENCES.read_text(encoding="utf-8")
        self.assertIn("remote-gate:plan-preferences:v1", source)
        self.assertIn("endpointSelections", source)
        self.assertIn("endpointManualSelections", source)
        self.assertIn("method: safeText(value.method, 32)", source)
        self.assertIn("method4: safeText(value.method4, 32)", source)
        self.assertIn("method6: safeText(value.method6, 32)", source)
        self.assertIn("remote-gate-endpoint-selection", source)
        self.assertIn("onWireGuardChange", source)
        self.assertIn("Browser storage is a convenience only; runtime authority never depends on it.", source)
        for forbidden in ("source_ip", "client_sources", "csrf", "expires_in", "/api/v1/gate/activate", "fetch("):
            self.assertNotIn(forbidden, source)

    def test_adapter_reuses_gate_controls_instead_of_implementing_endpoint_policy(self):
        source = PREFERENCES.read_text(encoding="utf-8")
        gate = GATE_CONTROLS.read_text(encoding="utf-8")
        self.assertIn("controls.bind", source)
        self.assertIn("controls.render", source)
        self.assertNotIn("endpointScore", source)
        self.assertNotIn("dualEndpointPairs", source)
        self.assertNotIn("reachability", source)
        self.assertIn("function endpointScore(item)", gate)
        self.assertIn("function endpointMethod(item)", gate)
        self.assertIn("function endpointSelectionRecord", gate)
        self.assertIn("function restoreEndpointSelection", gate)
        self.assertIn("if (!saved.method) return true", gate)
        self.assertIn("endpointMethodsForSelection(family, option.value).method === saved.method", gate)
        self.assertIn("const priorMethod4", gate)
        self.assertIn("const priorMethod6", gate)
        self.assertIn("endpointMethod(item.ipv4) === priorMethod4", gate)
        self.assertIn("endpointMethod(item.ipv6) === priorMethod6", gate)

    def test_runtime_manual_hint_is_bound_to_its_wireguard_service(self):
        source = PREFERENCES.read_text(encoding="utf-8")
        reconcile = source.split("function reconcileRuntimeWireguard()", 1)[1].split("function persistFamily", 1)[0]
        self.assertIn("const runtimeWireguards = {}", source)
        self.assertIn("runtimeWireguards[family] = item.wireguard", source)
        self.assertIn("runtimeWireguards[family] = wireguard", source)
        self.assertIn("boundWireguard === wireguard", reconcile)
        self.assertIn("delete state.endpointSelections[family]", reconcile)
        self.assertIn("state.endpointManualSelections[family] = false", reconcile)
        self.assertNotIn("endpointScore", reconcile)
        self.assertNotIn("preferredSelection", reconcile)
        self.assertNotIn("select.value", reconcile)
        render_wrapper = source.split("controls.render = (currentData) =>", 1)[1].split("window.addEventListener", 1)[0]
        self.assertLess(render_wrapper.index("reconcileRuntimeWireguard()"), render_wrapper.index("originalRender(currentData)"))

    def test_browser_regression_covers_reload_method_churn_invalidation_and_zero_auto_activate(self):
        source = BROWSER_TEST.read_text(encoding="utf-8")
        self.assertIn("page.reload", source)
        self.assertIn("topology = 'changed'", source)
        self.assertIn("topology = 'removed'", source)
        self.assertIn("topology = 'ambiguous'", source)
        self.assertIn("topology = 'ambiguous_changed'", source)
        self.assertIn("topology = 'dual_changed'", source)
        self.assertIn("ep-wan-v6-new", source)
        self.assertIn("ep-wan2-v6", source)
        self.assertIn("ep-wan2-v4-mapped-new", source)
        self.assertIn("ep-wan2-v4-mapped-next", source)
        self.assertIn("selection?.method === 'mapped'", source)
        self.assertIn("selection?.method4 === 'mapped'", source)
        self.assertIn("selection?.method6 === 'direct'", source)
        self.assertIn("activatePosts === 0", source)

    def test_browser_regression_covers_visible_multi_wireguard_choice_and_in_session_churn(self):
        source = BROWSER_SERVICE_TEST.read_text(encoding="utf-8")
        self.assertIn("WG_HOME", source)
        self.assertIn("WG_ALT", source)
        self.assertIn("topology = 'both'", source)
        self.assertIn("window.RemoteGateApp.refresh()", source)
        self.assertIn("#wg-select').isVisible()", source)
        self.assertIn("selectOption('WG_ALT')", source)
        self.assertIn("selectionSource === 'auto'", source)
        self.assertIn("!afterExplicitSwitch.endpoints?.ipv4", source)
        self.assertIn("!afterDisappear.endpoints?.ipv4", source)
        self.assertIn("activatePosts === 0", source)
        self.assertNotIn("page.reload", source.split("topology = 'both';", 1)[1])

    def test_ci_contract_keeps_browser_regressions_syntax_checked_and_in_shared_matrix(self):
        core = CORE_CI.read_text(encoding="utf-8")
        release = BROWSER_CI.read_text(encoding="utf-8")
        matrix = BROWSER_MATRIX_CI.read_text(encoding="utf-8")
        self.assertIn("node --check tests/browser_plan_preferences.mjs", core)
        self.assertIn("node --check tests/browser_plan_service_identity.mjs", core)
        self.assertIn("node tests/browser_plan_preferences.mjs", matrix)
        self.assertIn("node tests/browser_plan_service_identity.mjs", matrix)
        self.assertIn("uses: ./.github/workflows/browser-matrix.yml", release)
        self.assertIn("if: github.ref == 'refs/heads/main'", release)
        self.assertNotIn("playwright", core.lower())


if __name__ == "__main__":
    unittest.main()
