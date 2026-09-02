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
        source = APP.read_text(encoding="utf-8")
        self.assertIn("egressSelections: {}", source)
        self.assertIn("get egressWan()", source)
        self.assertIn("return this.egressSelections[this.family] || '__lan__'", source)
        self.assertIn("set egressWan(value)", source)
        self.assertIn("this.egressSelections[this.family] = String(value || '__lan__')", source)

    def test_internet_exit_default_mode_follows_access_until_user_overrides_plan(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("function selectedAccessWans()", source)
        self.assertIn("function preferredEgressMode()", source)
        self.assertIn("function defaultEgressValue(plans = egressPlans())", source)
        self.assertIn("function egressPlans()", source)
        self.assertIn("function egressSelectionIsManual", source)
        self.assertIn("const defaultValue = defaultEgressValue(plans)", source)
        self.assertIn("egressSelectionIsManual(family) && hasOption(remembered)", source)
        self.assertIn("state.egressWan=egressSelect().value||'__lan__'", source)
        self.assertIn("state.egressManualSelections[state.family]=true", source)
        self.assertIn("state.egressManualSelections={}", source)
        self.assertIn("mode:'dual'", source)
        self.assertNotIn("Dual · Split Exit", source)


if __name__ == "__main__":
    unittest.main()
