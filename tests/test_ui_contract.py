import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "server/app/templates/dashboard.html"
LOGIN = ROOT / "server/app/templates/login.html"
APP = ROOT / "server/app/static/js/app.js"
GATE = ROOT / "server/app/static/js/gate-controls.js"
CLIENT_SOURCES = ROOT / "server/app/static/js/client-sources.js"
BOOTSTRAP = ROOT / "server/app/static/js/theme-bootstrap.js"
DASHBOARD_CSS = ROOT / "server/app/static/css/dashboard.css"
INSTALL = ROOT / "server/install.sh"
UPDATE = ROOT / "server/update.sh"


class UIContractTests(unittest.TestCase):
    def test_browser_candidate_uses_cors_fetch_not_third_party_script(self):
        source = CLIENT_SOURCES.read_text(encoding="utf-8")
        self.assertIn("https://api.ipify.org?format=json", source)
        self.assertIn("https://api6.ipify.org?format=json", source)
        self.assertIn("mode: 'cors'", source)
        self.assertIn("credentials: 'omit'", source)
        self.assertIn("/api/v1/client-source/candidate", source)
        self.assertIn("X-CSRF-Token", source)
        self.assertNotIn("createElement('script')", source)
        self.assertNotIn("/api/v1/client-source/challenge", source)

    def test_production_dashboard_loads_candidate_probe_exactly_once(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        marker = '<script src="/static/js/client-sources.js?v={{ASSET_VERSION}}"></script>'
        self.assertEqual(template.count(marker), 1)
        self.assertIn('/static/js/theme-bootstrap.js?v={{ASSET_VERSION}}', template)
        self.assertLess(template.index(marker), template.index('<script src="/static/js/gate-controls.js?v={{ASSET_VERSION}}"></script>'))
        self.assertLess(template.index(marker), template.index('<script src="/static/js/app.js?v={{ASSET_VERSION}}"></script>'))
        self.assertNotIn("'/static/js/client-sources.js'", bootstrap)
        self.assertNotIn('"/static/js/client-sources.js"', bootstrap)

    def test_all_production_assets_are_build_sha_versioned(self):
        dashboard = TEMPLATE.read_text(encoding="utf-8")
        login = LOGIN.read_text(encoding="utf-8")
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertNotIn("032-r2", dashboard)
        self.assertNotIn("032-r2", login)
        self.assertIn("?v={{ASSET_VERSION}}", dashboard)
        self.assertIn("?v={{ASSET_VERSION}}", login)
        for asset in (
            "theme-bootstrap.js", "i18n.js", "tokens.css", "base.css", "components.css",
            "client-sources.js", "gate-controls.js", "app.js",
        ):
            self.assertIn(asset, dashboard if asset not in {"tokens.css", "base.css", "components.css"} else dashboard)
        self.assertIn("document.currentScript", bootstrap)
        self.assertIn("searchParams.get('v')", bootstrap)
        self.assertIn("assetUrl(src)", bootstrap)
        self.assertIn("assetUrl('/static/css/interaction.css')", bootstrap)
        self.assertIn('id="system-version">{{VERSION}}</strong>', dashboard)
        self.assertIn('id="system-build" title="{{BUILD_SHA}}">{{BUILD_SHORT}}</strong>', dashboard)

    def test_vps_install_and_update_freeze_to_one_commit_build(self):
        install = INSTALL.read_text(encoding="utf-8")
        update = UPDATE.read_text(encoding="utf-8")
        for source in (install, update):
            self.assertIn("resolve_build_sha", source)
            self.assertIn("REMOTE_GATE_BUILD_SHA", source)
            self.assertIn('RAW_BASE="${RAW_PREFIX}${BUILD_SHA}"', source)
            self.assertIn('"{{ASSET_VERSION}}": build', source)
            self.assertIn('"{{BUILD_SHA}}": build', source)
            self.assertIn('"{{BUILD_SHORT}}": build[:12]', source)
            self.assertIn('install -o root -g root -m 0644 "$TMP_DIR/BUILD" "$LIB_DIR/BUILD"', source)
            self.assertIn("application/vnd.github.raw+json", source)
        self.assertIn('LOCAL_BUILD="$(cat "$LIB_DIR/BUILD"', update)
        self.assertIn('[ "$LOCAL_BUILD" = "$BUILD_SHA" ]', update)

    def test_browser_never_submits_authorized_source_ip(self):
        gate = GATE.read_text(encoding="utf-8")
        probe = CLIENT_SOURCES.read_text(encoding="utf-8")
        self.assertNotIn("source_ip:", gate)
        self.assertNotIn('"source_ip"', probe)
        self.assertIn("body: JSON.stringify({family, address})", probe)

    def test_ipv4_ipv6_and_dual_activate_are_supported(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("families:['ipv4','ipv6']", source)
        self.assertIn("endpoint_ids:{ipv4:v4.id,ipv6:v6.id}", source)
        self.assertIn("family === 'dual'", source)
        template = TEMPLATE.read_text(encoding="utf-8")
        css = DASHBOARD_CSS.read_text(encoding="utf-8")
        self.assertIn('data-family="ipv4"', template)
        self.assertIn('data-family="ipv6"', template)
        self.assertIn('data-family="dual"', template)
        self.assertIn('>Dual Stack</button>', template)
        self.assertNotIn('>IPv4 + IPv6</button>', template)
        self.assertIn('.family-segment { grid-template-columns: repeat(3, 1fr); }', css)

    def test_candidate_and_verified_sources_remain_visibly_distinct(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn("carrier_probe", app)
        self.assertIn("Carrier NAT probe", app)
        self.assertIn("Cloudflare-observed sources remain preferred", app)

    def test_private_and_egress_paths_remain_available_for_manual_try(self):
        app = APP.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("['direct', 'mapped', 'private', 'egress_probe']", app)
        self.assertIn("['direct','mapped','private','egress_probe']", gate)
        self.assertIn("Private/CGNAT · Try", app)
        self.assertIn("NAT egress · Try", app)

    def test_scope_defaults_to_wireguard_only(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("state.scope='wg'", source)
        self.assertIn("wg_ping", source)

    def test_vps_installers_already_deploy_changed_runtime_files(self):
        required = (
            "server/remote-gate.py",
            "server/app/client_sources.py",
            "server/app/gate.py",
            "server/app/static/js/client-sources.js",
            "server/app/static/js/gate-controls.js",
        )
        for path in (INSTALL, UPDATE):
            source = path.read_text(encoding="utf-8")
            for item in required:
                self.assertIn(item, source, f"{path.name}: {item}")


if __name__ == "__main__":
    unittest.main()
