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
        self.assertIn("context.state.endpointSelections[family] = {value, wan: endpointWanForSelection(family, value)}", source)
        self.assertIn("rememberEndpointSelection(state.family)", source)
        self.assertIn("restoreEndpointSelection(state.family)", source)
        self.assertIn("const preferred = preferredSelection(family)", source)
        self.assertIn("select.dataset.selectionSource = confirmed ? source : ''", source)
        self.assertIn("const source = endpointSelectionIsManual(family) ? 'manual' : 'auto'", source)

    def test_dynamic_endpoint_id_preserves_same_wan_intent_then_returns_to_auto(self):
        source = GATE.read_text(encoding="utf-8")
        restore = source.split("function restoreEndpointSelection", 1)[1].split("function syncDualEndpointSelect", 1)[0]
        self.assertIn("if (saved.wan)", restore)
        self.assertIn("endpointWanForSelection(family, option.value) === saved.wan", restore)
        self.assertIn("context.state.endpointManualSelections[family] = false", restore)
        self.assertIn("delete context.state.endpointSelections[family]", restore)
        self.assertIn("const preferred = preferredSelection(family)", restore)

    def test_each_ip_family_keeps_its_internet_exit_choice(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("egressSelections: {}", source)
        self.assertIn("get egressWan()", source)
        self.assertIn("return this.egressSelections[this.family] || '__lan__'", source)
        self.assertIn("set egressWan(value)", source)
        self.assertIn("this.egressSelections[this.family] = String(value || '__lan__')", source)

    def test_internet_exit_defaults_to_access_wan_until_user_overrides_it(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("function selectedAccessWan()", source)
        self.assertIn("function egressSelectionIsManual", source)
        self.assertIn("const accessWan = selectedAccessWan()", source)
        self.assertIn("!egressSelectionIsManual(family) && hasOption(accessWan)", source)
        self.assertIn("state.egressManualSelections[state.family]=true", source)
        self.assertIn("state.egressManualSelections={}", source)


if __name__ == "__main__":
    unittest.main()
