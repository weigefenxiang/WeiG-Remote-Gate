import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"


class EndpointMemoryTests(unittest.TestCase):
    def test_each_ip_family_keeps_its_endpoint_choice(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("state.endpointSelections={}", source)
        self.assertIn("function rememberEndpointSelection", source)
        self.assertIn("function restoreEndpointSelection", source)
        self.assertIn("context.state.endpointSelections[family] = {value, wan}", source)
        self.assertIn("rememberEndpointSelection(state.family)", source)
        self.assertIn("restoreEndpointSelection(state.family)", source)
        self.assertIn("endpointWanForSelection", source)
        self.assertIn("const fallback = options.find", source)

    def test_dynamic_endpoint_id_can_fall_back_to_same_wan(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("if (saved.wan)", source)
        self.assertIn("endpointWanForSelection(family, option.value) === saved.wan", source)
        self.assertIn("const priorWan = String(saved?.wan || '')", source)
        self.assertIn("pairs.find((item) => item.wan === priorWan)", source)


if __name__ == "__main__":
    unittest.main()
