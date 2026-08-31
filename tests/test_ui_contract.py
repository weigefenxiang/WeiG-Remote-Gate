import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "server/app/templates/dashboard.html"
APP = ROOT / "server/app/static/js/app.js"
GATE = ROOT / "server/app/static/js/gate-controls.js"
BOOTSTRAP = ROOT / "server/app/static/js/theme-bootstrap.js"
CLIENT_SOURCES = ROOT / "server/app/static/js/client-sources.js"
ENDPOINT_PICKER = ROOT / "server/app/static/js/endpoint-picker.js"
DURATION = ROOT / "server/app/static/js/duration-control.js"
FEEDBACK = ROOT / "server/app/static/js/motion-feedback.js"
FAVICON = ROOT / "server/app/static/Wei.G.ico"
LAYOUT = ROOT / "server/app/static/css/layout.css"
SPATIAL = ROOT / "server/app/static/css/spatial.css"
INTERACTION = ROOT / "server/app/static/css/interaction.css"
I18N = ROOT / "server/app/static/js/i18n.js"
INSTALL = ROOT / "server/install.sh"
UPDATE = ROOT / "server/update.sh"
REMOTE_GATE = ROOT / "server/remote-gate.py"
CLIENT_SOURCE_MODEL = ROOT / "server/app/client_sources.py"


class UIContractTests(unittest.TestCase):
    def test_mobile_layout_never_uses_display_contents(self):
        source = LAYOUT.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"display\s*:\s*contents")
        self.assertIn(".workspace-flow", source)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", source)

    def test_template_has_gate_family_scope_and_presets(self):
        source = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('id="endpoint-select"', source)
        self.assertIn('id="scope-segment"', source)
        self.assertIn('data-scope="wg"', source)
        self.assertIn('data-scope="wg_ping"', source)
        self.assertIn('data-family="ipv4"', source)
        self.assertIn('data-family="ipv6"', source)
        self.assertNotIn('data-family="dual"', source)
        for ttl, label in ((60, "1m"), (300, "5m"), (900, "15m"), (1800, "30m")):
            self.assertIn(f'data-ttl="{ttl}"', source)
            self.assertIn(f'>{label}</button>', source)
        self.assertNotIn('data-ttl="3600"', source)
        self.assertIn('/static/css/spatial.css', source)

    def test_browser_never_supplies_authorization_ip_directly(self):
        app = APP.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        source_probe = CLIENT_SOURCES.read_text(encoding="utf-8")
        self.assertNotIn("CLIENT_MEMORY_KEY", app)
        self.assertNotRegex(gate, r"source_ip\s*:")
        self.assertIn("client_sources", app)
        self.assertIn("endpoint_id", gate)
        self.assertIn("scope", gate)
        self.assertNotIn("body: JSON.stringify({family, address})", source_probe)
        self.assertNotIn("api.ipify.org", source_probe)

    def test_dual_stack_source_observer_is_automatic_and_independent(self):
        source = CLIENT_SOURCES.read_text(encoding="utf-8")
        runtime = REMOTE_GATE.read_text(encoding="utf-8")
        model = CLIENT_SOURCE_MODEL.read_text(encoding="utf-8")
        self.assertIn("/api/v1/client-source/challenge", source)
        self.assertIn("observerProbe", source)
        self.assertIn("PROBE_INTERVAL", source)
        self.assertIn("PROBE_TIMEOUT", source)
        self.assertIn("['ipv4', 'ipv6']", source)
        self.assertIn("data?.client_sources?.[family]?.address", source)
        self.assertIn("/api/v1/client-source/observe", runtime)
        self.assertIn("CF-Connecting-IP", (ROOT / "server/app/security.py").read_text(encoding="utf-8"))
        self.assertIn("untrusted_source_probe_disabled", runtime)
        self.assertIn("untrusted_source_probe_disabled", model)
        self.assertNotIn("https://api.ipify.org", runtime)
        self.assertNotIn("https://api6.ipify.org", runtime)

    def test_private_and_egress_wan_paths_are_manual_try_options(self):
        app = APP.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        expected = "['direct', 'mapped', 'private', 'egress_probe']"
        self.assertIn(expected, app)
        self.assertIn(expected, gate)
        self.assertIn("Private/CGNAT · Try", app)
        self.assertIn("NAT egress · Try", app)
        self.assertIn("NAT IPv4", app)
        self.assertIn("Egress · Try", app)

    def test_ipv4_is_preferred_without_overriding_manual_ipv6(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("state.familyManual && familyAvailable(state.family)", source)
        self.assertIn("familyAvailable('ipv4')", source)
        self.assertIn("state.familyManual = true", source)
        self.assertIn("familyAvailable('ipv6')", source)
        self.assertNotIn("state.requestFamily !== 'ipv4'", source)
        self.assertNotIn("state.requestFamily !== 'ipv6'", source)

    def test_cgnat_safe_scope_defaults_to_wireguard_only(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("state.scope = 'wg'", source)
        self.assertIn("wg_ping", source)
        app = APP.read_text(encoding="utf-8")
        self.assertIn("fw.scope === 'wg_ping'", app)

    def test_endpoint_picker_replaces_native_select_visual(self):
        picker = ENDPOINT_PICKER.read_text(encoding="utf-8")
        css = INTERACTION.read_text(encoding="utf-8")
        self.assertIn("endpoint-picker-trigger", picker)
        self.assertIn("endpoint-picker-layer", picker)
        self.assertIn("endpoint-option-card", picker)
        self.assertIn('role="listbox"', picker)
        self.assertIn("endpoint-native-select", picker)
        self.assertIn(".endpoint-native-select", css)
        self.assertIn("pointer-events: none", css)
        self.assertIn(".endpoint-picker-sheet", css)
        self.assertIn(".endpoint-option-card.selected", css)

    def test_custom_duration_is_half_hour_to_twelve_hours(self):
        source = DURATION.read_text(encoding="utf-8")
        self.assertIn("const MIN = 1800", source)
        self.assertIn("const MAX = 43200", source)
        self.assertIn("const STEP = 1800", source)
        self.assertIn("ttl-custom-button", source)
        self.assertIn("duration-slider", source)
        self.assertIn("RemoteGateFeedback", source)
        self.assertNotIn('data-ttl="3600"', TEMPLATE.read_text(encoding="utf-8"))

    def test_feedback_module_has_sound_haptic_and_user_controls(self):
        source = FEEDBACK.read_text(encoding="utf-8")
        self.assertIn("AudioContext", source)
        self.assertIn("navigator.vibrate", source)
        self.assertIn("feedback-sound", source)
        self.assertIn("feedback-haptic", source)
        self.assertIn("localStorage", source)

    def test_brand_uses_canonical_wei_g_icon_with_chassis(self):
        self.assertTrue(FAVICON.is_file())
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        css = INTERACTION.read_text(encoding="utf-8")
        self.assertIn("/static/Wei.G.ico", bootstrap)
        self.assertIn("brand-icon-image", bootstrap)
        self.assertIn("brand-icon-chassis", bootstrap)
        self.assertIn("/static/css/interaction.css", bootstrap)
        self.assertIn(".brand-icon-chassis", css)
        self.assertIn(".brand-icon-image", css)

    def test_spatial_layer_has_touch_and_depth_tokens(self):
        source = SPATIAL.read_text(encoding="utf-8")
        self.assertIn("var(--touch-min)", source)
        self.assertIn("var(--depth-z3)", source)
        self.assertIn(".activity-row", source)
        self.assertIn(".system-row span", source)

    def test_interaction_layer_respects_reduced_motion(self):
        source = INTERACTION.read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion: reduce", source)
        self.assertIn(".endpoint-option-card", source)
        self.assertIn(".duration-custom-panel", source)

    def test_old_ipv4_only_copy_is_gone(self):
        source = I18N.read_text(encoding="utf-8")
        self.assertNotIn("IPv6 is displayed but data-plane authorization is not enabled", source)
        self.assertNotIn("Open this control page over IPv4 before activating", source)
        self.assertIn("Observed by VPS", source)
        self.assertIn("仅 WireGuard", source)

    def test_deploy_scripts_include_interaction_modules(self):
        required = (
            "server/app/static/css/spatial.css",
            "server/app/static/css/interaction.css",
            "server/app/static/js/motion-feedback.js",
            "server/app/static/js/client-sources.js",
            "server/app/static/js/endpoint-picker.js",
            "server/app/static/js/duration-control.js",
        )
        for path in (INSTALL, UPDATE):
            source = path.read_text(encoding="utf-8")
            for item in required:
                self.assertIn(item, source, f"{path.name}: {item}")

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
