import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "server/app/templates/dashboard.html").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "server/app/static/js/theme-bootstrap.js").read_text(encoding="utf-8")
APP = (ROOT / "server/app/static/js/app.js").read_text(encoding="utf-8")
GATE = (ROOT / "server/app/static/js/gate-controls.js").read_text(encoding="utf-8")
CSS = (ROOT / "server/app/static/css/dashboard.css").read_text(encoding="utf-8")


class GatePresentationOwnerContractTests(unittest.TestCase):
    def test_theme_bootstrap_is_not_a_gate_runtime_owner(self):
        self.assertNotIn("MutationObserver", BOOTSTRAP)
        self.assertNotIn("window.fetch =", BOOTSTRAP)
        self.assertNotIn("ensureGateStatusStructure", BOOTSTRAP)
        self.assertNotIn("ensureVerifiedEndpoint", BOOTSTRAP)
        self.assertNotIn("renderSelectedEndpoint", BOOTSTRAP)
        self.assertNotIn("selectedPublicEndpoint", BOOTSTRAP)
        self.assertNotIn("polishGateActions", BOOTSTRAP)
        self.assertNotIn("brandIcon", BOOTSTRAP)

    def test_gate_status_and_public_endpoint_dom_are_canonical_template_markup(self):
        self.assertIn('class="gate-orb-wrap gate-status-hero"', TEMPLATE)
        self.assertIn('id="gate-status-stage"', TEMPLATE)
        self.assertIn('id="gate-orb-state"', TEMPLATE)
        self.assertIn('id="gate-status-copy"', TEMPLATE)
        self.assertIn('id="current-public-endpoint"', TEMPLATE)
        self.assertIn('data-public-endpoint-label="1"', TEMPLATE)
        self.assertIn('data-public-endpoint-value="1"', TEMPLATE)
        self.assertNotIn("mapped-public-endpoint", TEMPLATE)
        self.assertNotIn("verified-endpoint-note", TEMPLATE)
        self.assertNotIn("verified-endpoint-note", CSS)
        self.assertIn("justify-content: center;", CSS)

    def test_current_public_endpoint_display_consumes_gate_structured_rows_only(self):
        self.assertIn("function selectedPublicPathRow()", APP)
        self.assertIn("option.dataset.pathRows", APP)
        self.assertIn("['Public Direct', 'Global Direct', 'Mapped']", APP)
        self.assertIn("function renderCurrentPublicEndpoint()", APP)
        self.assertIn("window.addEventListener('remote-gate-endpoint-selection'", APP)
        self.assertNotIn("function endpointScore", APP)
        self.assertNotIn("function endpointsFor", APP)
        self.assertNotIn("function mappedEndpoint", APP)
        self.assertNotIn("OpenWrt 当前上报", APP)
        self.assertNotIn("currently reported by OpenWrt", APP)

    def test_internet_exit_rows_are_single_family_wan_addresses_not_access_ports(self):
        block = GATE.split("function populateEgressWanSelect", 1)[1].split("function ensureEgressControl", 1)[0]
        self.assertIn("setPathRows(option, [pathRow(family, item.wan.name, '', item.address)]", block)
        self.assertIn("option.dataset.egressFamily = family", block)
        self.assertNotIn("endpointAddress(item)", block)
        self.assertNotIn("external_port", block)
        self.assertNotIn("service_port", block)


if __name__ == "__main__":
    unittest.main()
