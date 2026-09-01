import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"
PICKER = ROOT / "server/app/static/js/endpoint-picker.js"
THEME = ROOT / "server/app/static/js/theme-bootstrap.js"
ENDPOINTS = ROOT / "server/app/endpoints.py"


class EndpointSelectionContractTests(unittest.TestCase):
    def test_public_endpoint_waits_for_explicit_wan_selection(self):
        gate = GATE.read_text(encoding="utf-8")
        theme = THEME.read_text(encoding="utf-8")
        self.assertIn("endpointManualSelections", gate)
        self.assertIn("endpointSelectionIsManual(state.family)", gate)
        self.assertIn("select.dataset.selectionConfirmed = confirmed ? '1' : '0'", gate)
        self.assertIn("select.dataset.selectionConfirmed !== '1'", theme)
        self.assertIn("selectedEndpointRecord", theme)
        self.assertIn("remote-gate-endpoint-selection", theme)

    def test_picker_opens_before_an_endpoint_is_selected(self):
        picker = PICKER.read_text(encoding="utf-8")
        self.assertIn("请选择 WAN Endpoint", picker)
        self.assertIn("Choose WAN endpoint", picker)
        self.assertIn("if (!select || select.disabled || !trigger) return;", picker)
        self.assertNotIn("select.disabled || !select.value || !trigger", picker)
        self.assertIn("trigger.disabled = Boolean(select.disabled)", picker)

    def test_ipv6_tab_is_selectable_even_before_it_is_ready(self):
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("return ['ipv4','ipv6','dual'].includes(family);", gate)
        self.assertIn("button.disabled = false", gate)
        self.assertIn("function gateCapability", gate)
        self.assertIn("gateCapability('ipv6')", gate)
        self.assertIn("familyAvailable(state.family)", gate)

    def test_ipv6_wireguard_is_direct_only(self):
        theme = THEME.read_text(encoding="utf-8")
        endpoints = ENDPOINTS.read_text(encoding="utf-8")
        self.assertIn("selected.family === 'ipv6'", theme)
        self.assertIn("selected.access_method === 'mapped'", theme)
        self.assertIn("return null;", theme)
        self.assertIn('or family != "ipv4"', endpoints)
        self.assertIn('"family": "ipv6"', endpoints)
        self.assertIn('"access_method": "direct"', endpoints)

    def test_ipv6_direct_endpoint_uses_bracketed_wireguard_syntax(self):
        theme = THEME.read_text(encoding="utf-8")
        self.assertIn("item.family === 'ipv6' ? `[${address}]:${port}`", theme)
        self.assertIn("IPv6 Direct · OpenWrt 当前上报", theme)


if __name__ == "__main__":
    unittest.main()
