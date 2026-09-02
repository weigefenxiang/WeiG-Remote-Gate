import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "server/app/static/js/app.js"
GATE = ROOT / "server/app/static/js/gate-controls.js"


class EndpointMemoryTests(unittest.TestCase):
    def test_each_ip_family_uses_auto_default_until_user_overrides_it(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("state.endpointSelections={}", source)
        self.assertIn("state.endpointManualSelections={}", source)
        self.assertIn("function endpointSelectionIsManual", source)
        self.assertIn("function preferredSelection", source)
        self.assertIn("function rememberEndpointSelection", source)
        self.assertIn("function restoreEndpointSelection", source)
        self.assertIn("function syncEndpointSelect", source)
        self.assertIn("function endpointSelectionRecord", source)
        self.assertIn("const wans = endpointWansForSelection(family, value)", source)
        self.assertIn("wan4:wans.ipv4", source)
        self.assertIn("wan6:wans.ipv6", source)
        self.assertIn("method:methods.method", source)
        self.assertIn("method4:methods.method4", source)
        self.assertIn("method6:methods.method6", source)
        self.assertIn("rememberEndpointSelection(state.family)", source)
        self.assertIn("syncEndpointSelect(state.family)", source)
        self.assertIn("else if (['ipv4','ipv6'].includes(family)) restoreEndpointSelection(family);", source)
        self.assertIn("const preferred = preferredSelection(family)", source)
        self.assertIn("select.dataset.selectionSource = confirmed ? source : ''", source)
        self.assertIn("const source = endpointSelectionIsManual(family) ? 'manual' : 'auto'", source)

    def test_dynamic_endpoint_id_preserves_same_wan_and_access_method_intent(self):
        source = GATE.read_text(encoding="utf-8")
        restore = source.split("function restoreEndpointSelection", 1)[1].split("function syncDualEndpointSelect", 1)[0]
        dual = source.split("function syncDualEndpointSelect", 1)[1].split("function syncEndpointSelect", 1)[0]
        self.assertIn("saved.wan ? options.find", restore)
        self.assertIn("endpointWanForSelection(family, option.value) !== saved.wan", restore)
        self.assertIn("if (!saved.method) return true", restore)
        self.assertIn("endpointMethodsForSelection(family, option.value).method === saved.method", restore)
        self.assertIn("context.state.endpointSelections[family] = endpointSelectionRecord(family, fallback.value)", restore)
        self.assertIn("context.state.endpointManualSelections[family] = false", restore)
        self.assertIn("delete context.state.endpointSelections[family]", restore)
        self.assertIn("const preferred = preferredSelection(family)", restore)
        self.assertIn("const priorMethod4", dual)
        self.assertIn("const priorMethod6", dual)
        self.assertIn("endpointMethod(item.ipv4) === priorMethod4", dual)
        self.assertIn("endpointMethod(item.ipv6) === priorMethod6", dual)
        self.assertIn("endpointSelectionRecord('dual', pair.id)", dual)

    def test_each_access_family_keeps_its_internet_exit_plan_choice(self):
        gate = GATE.read_text(encoding="utf-8")
        app = APP.read_text(encoding="utf-8")
        self.assertIn("const egressState = {byAccessFamily:{}}", gate)
        self.assertIn("function egressPreference(accessFamily = context?.state?.family)", gate)
        self.assertIn("egressState.byAccessFamily[key]", gate)
        self.assertIn("manualMode:false", gate)
        self.assertIn("manualIpv4:false", gate)
        self.assertIn("manualIpv6:false", gate)
        self.assertNotIn("egressSelections", app)
        self.assertNotIn("get egressWan()", app)
        self.assertNotIn("set egressWan(value)", app)

    def test_internet_exit_default_mode_follows_access_until_user_overrides_plan(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("function preferredEgressMode()", source)
        self.assertIn("function preferredSharedEgressWan()", source)
        self.assertIn("function preferredEgressWans()", source)
        self.assertIn("function normalizeEgressPreference", source)
        self.assertIn("function defaultEgressPlan", source)
        self.assertIn("preference.manualMode = true", source)
        self.assertIn("preference[family==='ipv4'?'manualIpv4':'manualIpv6']=true", source)
        self.assertIn("egressModeRoot()?.addEventListener('click'", source)
        self.assertIn("egressWanSelect(family)?.addEventListener('change'", source)
        self.assertNotIn("function egressPlans()", source)
        self.assertNotIn("function defaultEgressValue", source)
        self.assertNotIn("const access = selectedAccessWans()", source)
        self.assertNotIn("Dual · Split Exit", source)


if __name__ == "__main__":
    unittest.main()
