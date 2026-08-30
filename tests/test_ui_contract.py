import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "server/app/templates/dashboard.html"
APP = ROOT / "server/app/static/js/app.js"
GATE = ROOT / "server/app/static/js/gate-controls.js"
BOOTSTRAP = ROOT / "server/app/static/js/theme-bootstrap.js"
FAVICON = ROOT / "server/app/static/Wei.G.ico"
LAYOUT = ROOT / "server/app/static/css/layout.css"
SPATIAL = ROOT / "server/app/static/css/spatial.css"
I18N = ROOT / "server/app/static/js/i18n.js"
INSTALL = ROOT / "server/install.sh"
UPDATE = ROOT / "server/update.sh"


class UIContractTests(unittest.TestCase):
    def test_mobile_layout_never_uses_display_contents(self):
        source = LAYOUT.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"display\s*:\s*contents")
        self.assertIn(".workspace-flow", source)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", source)

    def test_template_has_v03_gate_controls(self):
        source = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('id="endpoint-select"', source)
        self.assertIn('id="scope-segment"', source)
        self.assertIn('data-scope="wg"', source)
        self.assertIn('data-scope="wg_ping"', source)
        self.assertIn('data-family="ipv4"', source)
        self.assertIn('data-family="ipv6"', source)
        self.assertNotIn('data-family="dual"', source)
        self.assertIn('/static/css/spatial.css', source)

    def test_browser_never_supplies_authorization_ip(self):
        app = APP.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        self.assertNotIn("CLIENT_MEMORY_KEY", app)
        self.assertNotRegex(gate, r"source_ip\s*:")
        self.assertIn("client_sources", app)
        self.assertIn("endpoint_id", gate)
        self.assertIn("scope", gate)

    def test_manual_family_is_not_locked_to_current_request(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertNotIn("state.requestFamily !== 'ipv4'", source)
        self.assertNotIn("state.requestFamily !== 'ipv6'", source)
        self.assertIn("button.disabled = !familyAvailable(family)", source)
        self.assertIn("familyAvailable('ipv4')", source)
        self.assertIn("familyAvailable('ipv6')", source)

    def test_cgnat_safe_scope_defaults_to_wireguard_only(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("state.scope = 'wg'", source)
        self.assertIn("wg_ping", source)
        app = APP.read_text(encoding="utf-8")
        self.assertIn("fw.scope === 'wg_ping'", app)

    def test_spatial_layer_has_touch_and_depth_tokens(self):
        source = SPATIAL.read_text(encoding="utf-8")
        self.assertIn("var(--touch-min)", source)
        self.assertIn("var(--depth-z3)", source)
        self.assertIn(".activity-row", source)
        self.assertIn(".system-row span", source)

    def test_old_ipv4_only_copy_is_gone(self):
        source = I18N.read_text(encoding="utf-8")
        self.assertNotIn("IPv6 is displayed but data-plane authorization is not enabled", source)
        self.assertNotIn("Open this control page over IPv4 before activating", source)
        self.assertIn("Observed by VPS", source)
        self.assertIn("仅 WireGuard", source)

    def test_deploy_scripts_include_spatial_module(self):
        for path in (INSTALL, UPDATE):
            source = path.read_text(encoding="utf-8")
            self.assertIn("server/app/static/css/spatial.css", source, path.name)

    def test_canonical_favicon_is_bootstrapped_and_deployed(self):
        self.assertTrue(FAVICON.is_file())
        self.assertEqual(FAVICON.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("/static/Wei.G.ico", bootstrap)
        self.assertIn("favicon.type = 'image/png'", bootstrap)
        for path in (INSTALL, UPDATE):
            source = path.read_text(encoding="utf-8")
            self.assertIn("server/app/static/Wei.G.ico", source, path.name)

    def test_vps_updater_is_installed_and_preserved(self):
        install = INSTALL.read_text(encoding="utf-8")
        update = UPDATE.read_text(encoding="utf-8")
        for source in (install, update):
            self.assertIn('"server/update.sh"', source)
            self.assertIn('bash -n "$TMP_DIR/server/update.sh"', source)
            self.assertIn('"$LIB_DIR/update.sh"', source)
        self.assertIn('install -o root -g root -m 0755 "$TMP_DIR/server/update.sh" "$LIB_DIR/update.sh"', install)
        self.assertIn('install -o root -g root -m 0755 "$TMP_DIR/server/update.sh" "$LIB_DIR/update.sh"', update)


if __name__ == "__main__":
    unittest.main()
