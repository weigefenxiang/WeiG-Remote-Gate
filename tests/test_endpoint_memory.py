import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "server/app/static/js/app.js"
GATE = ROOT / "server/app/static/js/gate-controls.js"


class EndpointMemoryTests(unittest.TestCase):
    def test_each_ip_family_keeps_only_explicit_endpoint_choice(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("state.endpointSelections={}", source)
        self.assertIn("state.endpointManualSelections={}", source)
        self.assertIn("function endpointSelectionIsManual", source)
        self.assertIn("function rememberEndpointSelection", source)
        self.assertIn("function restoreEndpointSelection", source)
        self.assertIn("context.state.endpointSelections[family] = {value, wan: endpointWanForSelection(family, value)}", source)
        self.assertIn("rememberEndpointSelection(state.family)", source)
        self.assertIn("restoreEndpointSelection(state.family)", source)
        self.assertIn("endpointWanForSelection", source)
        self.assertIn("select.value = ''", source)
        self.assertIn("selectionConfirmed", source)

    def test_dynamic_endpoint_id_can_fall_back_to_same_wan(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("if (saved.wan)", source)
        self.assertIn("endpointWanForSelection(family, option.value) === saved.wan", source)
        self.assertIn("saved?.wan", source)
        self.assertIn("pairs.find((item) => item.wan === priorWan)", source)

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
