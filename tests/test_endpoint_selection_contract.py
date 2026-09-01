import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"
PICKER = ROOT / "server/app/static/js/endpoint-picker.js"
THEME = ROOT / "server/app/static/js/theme-bootstrap.js"
ENDPOINTS = ROOT / "server/app/endpoints.py"


class EndpointSelectionContractTests(unittest.TestCase):
    def test_public_endpoint_is_automatically_preferred_and_confirmed(self):
        gate = GATE.read_text(encoding="utf-8")
        theme = THEME.read_text(encoding="utf-8")
        self.assertIn("preferredIpv4Endpoint", gate)
        self.assertIn("preferredIpv6Endpoint", gate)
        self.assertIn("preferredSelection", gate)
        self.assertIn("endpointScore", gate)
        self.assertIn("const confirmed = Boolean(value);", gate)
        self.assertIn("select.dataset.selectionSource = confirmed ? source : '';", gate)
        self.assertIn("const source = endpointSelectionIsManual(family) ? 'manual' : 'auto';", gate)
        self.assertNotIn("endpointSelectionIsManual(state.family) &&", gate)
        self.assertIn("select.dataset.selectionConfirmed !== '1'", theme)
        self.assertIn("selectedEndpointRecord", theme)
        self.assertIn("remote-gate-endpoint-selection", theme)

    def test_ipv4_prefers_direct_before_mapped_or_private(self):
        gate = GATE.read_text(encoding="utf-8")
        score = gate.split("function endpointScore(item) {", 1)[1].split("function endpointCompare", 1)[0]
        direct = score.index("item.family === 'ipv4' && item.reachability === 'direct'")
        mapped = score.index("item.family === 'ipv4' && item.reachability === 'mapped'")
        probe = score.index("item.family === 'ipv4' && item.reachability === 'egress_probe'")
        private = score.index("item.reachability === 'private'")
        self.assertLess(direct, mapped)
        self.assertLess(mapped, probe)
        self.assertLess(probe, private)

    def test_ipv6_prefers_the_selected_ipv4_wan_when_available(self):
        gate = GATE.read_text(encoding="utf-8")
        preferred = gate.split("function preferredIpv6Endpoint() {", 1)[1].split("function dualEndpointPairs", 1)[0]
        self.assertIn("preferredIpv4Endpoint()?.wan", preferred)
        self.assertIn("a?.wan === preferredV4Wan", preferred)
        self.assertIn("b?.wan === preferredV4Wan", preferred)

    def test_manual_endpoint_override_is_preserved_until_it_disappears(self):
        gate = GATE.read_text(encoding="utf-8")
        restore = gate.split("function restoreEndpointSelection", 1)[1].split("function syncDualEndpointSelect", 1)[0]
        self.assertIn("endpointSelectionIsManual(family) && saved", restore)
        self.assertIn("option.value === saved.value", restore)
        self.assertIn("endpointWanForSelection(family, option.value) === saved.wan", restore)
        self.assertIn("context.state.endpointManualSelections[family] = false", restore)
        self.assertIn("const preferred = preferredSelection(family);", restore)

    def test_picker_still_allows_manual_endpoint_override(self):
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

    def test_automatic_family_keeps_ipv4_first_when_both_are_available(self):
        gate = GATE.read_text(encoding="utf-8")
        choose = gate.split("function chooseFamily() {", 1)[1].split("function familyReason", 1)[0]
        ipv4_available = choose.index("if (singleAvailable('ipv4')) return 'ipv4';")
        request_ipv6 = choose.index("if (state.requestFamily === 'ipv6' && singleReady('ipv6')) return 'ipv6';")
        self.assertLess(ipv4_available, request_ipv6)
        self.assertIn("if (singleAvailable('ipv6')) return 'ipv6';", choose)

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
