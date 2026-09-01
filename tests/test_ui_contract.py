import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "server/app/templates/dashboard.html"
LOGIN = ROOT / "server/app/templates/login.html"
APP = ROOT / "server/app/static/js/app.js"
GATE = ROOT / "server/app/static/js/gate-controls.js"
ENDPOINT_PICKER = ROOT / "server/app/static/js/endpoint-picker.js"
CLIENT_SOURCES = ROOT / "server/app/static/js/client-sources.js"
FEEDBACK = ROOT / "server/app/static/js/ui-feedback.js"
FEEDBACK_CSS = ROOT / "server/app/static/css/feedback.css"
BOOTSTRAP = ROOT / "server/app/static/js/theme-bootstrap.js"
DASHBOARD_CSS = ROOT / "server/app/static/css/dashboard.css"
COMPONENTS_CSS = ROOT / "server/app/static/css/components.css"
INSTALL = ROOT / "server/install.sh"
UPDATE = ROOT / "server/update.sh"
SERVER = ROOT / "server/remote-gate.py"
OPENWRT_UPDATE = ROOT / "openwrt/update.sh"
OPENWRT_AGENT = ROOT / "openwrt/remote-gate-agent.sh"
OPENWRT_EGRESS = ROOT / "openwrt/remote-gate-wireguard-egress.sh"


class UIContractTests(unittest.TestCase):
    def test_browser_candidate_uses_cors_fetch_not_third_party_script(self):
        source = CLIENT_SOURCES.read_text(encoding="utf-8")
        self.assertIn("https://api.ipify.org?format=json", source)
        self.assertIn("https://api6.ipify.org?format=json", source)
        self.assertIn("https://api-ipv4.ip.sb/ip", source)
        self.assertIn("https://api-ipv6.ip.sb/ip", source)
        self.assertIn("mode: 'cors'", source)
        self.assertIn("credentials: 'omit'", source)
        self.assertIn("/api/v1/client-source/candidate", source)
        self.assertIn("X-CSRF-Token", source)
        self.assertIn("remote-gate-client-source-diagnostics", source)
        self.assertIn("Candidate rejected:", source)
        self.assertIn("timed out after", source)
        self.assertNotIn("createElement('script')", source)
        self.assertNotIn("/api/v1/client-source/challenge", source)

    def test_candidate_api_is_production_routed_and_router_egress_fails_closed(self):
        server = SERVER.read_text(encoding="utf-8")
        self.assertIn('path == "/api/v1/client-source/candidate"', server)
        self.assertIn("record = observe_candidate(STORE, session.token, address, family)", server)
        self.assertIn('record.get("confidence") == "suppressed"', server)
        self.assertIn('self._json(409, {"error": "router_egress_source"})', server)
        self.assertIn('path == "/api/v1/client-source/probe"', server)
        self.assertIn('self._json(410, {"error": "legacy_source_probe_disabled"})', server)

    def test_observed_family_skips_carrier_probe_and_candidate_update_never_reloads_page(self):
        source = CLIENT_SOURCES.read_text(encoding="utf-8")
        self.assertIn("source.confidence === 'observed'", source)
        self.assertIn("carrier probe skipped", source)
        self.assertIn("remote-gate-client-source-updated", source)
        self.assertNotIn("window.location.reload", source)
        self.assertNotIn("location.reload", source)

    def test_probe_fallback_hosts_are_allowed_by_production_csp(self):
        server = SERVER.read_text(encoding="utf-8")
        self.assertIn("https://api-ipv4.ip.sb", server)
        self.assertIn("https://api-ipv6.ip.sb", server)
        self.assertIn("https://api.ipify.org", server)
        self.assertIn("https://api6.ipify.org", server)

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

    def test_standard_feedback_assets_are_versioned_and_loaded_before_gate_controls(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        feedback = FEEDBACK.read_text(encoding="utf-8")
        css = FEEDBACK_CSS.read_text(encoding="utf-8")
        self.assertIn('/static/css/feedback.css?v={{ASSET_VERSION}}', template)
        marker = '<script src="/static/js/ui-feedback.js?v={{ASSET_VERSION}}"></script>'
        self.assertIn(marker, template)
        self.assertLess(template.index(marker), template.index('<script src="/static/js/gate-controls.js?v={{ASSET_VERSION}}"></script>'))
        self.assertIn("RemoteGateFeedback", feedback)
        self.assertIn("feedback-card", css)
        self.assertIn("feedback-error", css)
        self.assertIn("feedback-progress", css)
        self.assertIn("prefers-reduced-motion", css)

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
            "feedback.css", "ui-feedback.js", "client-sources.js", "gate-controls.js", "app.js",
        ):
            self.assertIn(asset, dashboard)
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
            self.assertIn("server/app/static/css/feedback.css", source)
            self.assertIn("server/app/static/js/ui-feedback.js", source)
        self.assertIn('LOCAL_BUILD="$(cat "$LIB_DIR/BUILD"', update)
        self.assertIn('[ "$LOCAL_BUILD" = "$BUILD_SHA" ]', update)

    def test_browser_never_submits_authorized_source_ip(self):
        gate = GATE.read_text(encoding="utf-8")
        probe = CLIENT_SOURCES.read_text(encoding="utf-8")
        self.assertNotIn("source_ip:", gate)
        self.assertNotIn('"source_ip"', probe)
        self.assertIn("body: JSON.stringify({family, address})", probe)

    def test_ipv4_ipv6_and_split_dual_activate_are_supported_in_one_compact_row(self):
        gate = GATE.read_text(encoding="utf-8")
        template = TEMPLATE.read_text(encoding="utf-8")
        css = COMPONENTS_CSS.read_text(encoding="utf-8")
        self.assertIn("families:['ipv4','ipv6']", gate)
        self.assertIn("endpoint_ids:{ipv4:pair.ipv4.id,ipv6:pair.ipv6.id}", gate)
        self.assertIn("egress_wans:{ipv4:egressPlan.ipv4,ipv6:egressPlan.ipv6}", gate)
        self.assertIn("dualEndpointPairs", gate)
        self.assertIn("Dual · Split WAN", gate)
        self.assertIn("Split Exit", gate)
        self.assertIn("same WireGuard service", gate)
        self.assertIn("双栈就绪 · IPv4 + IPv6 已识别", gate)
        self.assertIn("Dual stack ready · IPv4 + IPv6 detected", gate)
        self.assertIn("option.dataset.ipv4EndpointId", gate)
        self.assertIn("option.dataset.ipv6EndpointId", gate)
        self.assertIn("option.dataset.ipv4Wan", gate)
        self.assertIn("option.dataset.ipv6Wan", gate)
        self.assertIn("queueMicrotask(syncDualEndpointSelect)", gate)
        self.assertIn("family === 'dual'", gate)
        self.assertIn("{ipv4: 'IPv4', ipv6: 'IPv6', dual: 'Dual'}", gate)
        self.assertIn('data-family="ipv4"', template)
        self.assertIn('data-family="ipv6"', template)
        self.assertIn('data-family="dual"', template)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr)) !important", css)
        self.assertIn("white-space: nowrap", css)
        self.assertIn(".family-segment button", css)

    def test_mobile_endpoint_picker_fits_long_addresses_without_chevron(self):
        source = ENDPOINT_PICKER.read_text(encoding="utf-8")
        self.assertIn('endpoint-trigger-address fit-single-line', source)
        self.assertIn('data-fit-min="7.5"', source)
        self.assertIn("RemoteGateFit?.fit?.(address)", source)
        self.assertIn("trigger.style.gridTemplateColumns = 'minmax(0, 1fr)'", source)
        self.assertIn("trigger.addEventListener('click', () => open(selectId))", source)
        self.assertIn("bindSelect('endpoint-select')", source)
        self.assertNotIn("endpoint-trigger-chevron", source)

    def test_internet_exit_reuses_the_existing_endpoint_picker(self):
        picker = ENDPOINT_PICKER.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("const configs = new Map()", picker)
        self.assertIn("selectId === 'egress-select'", picker)
        self.assertIn("bindSelect", picker)
        self.assertIn("egress-select", gate)
        self.assertIn("INTERNET EXIT", gate)
        self.assertIn("Internet 出口", gate)

    def test_gate_hides_redundant_wireguard_selector_but_keeps_internal_state(self):
        picker = ENDPOINT_PICKER.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("hideWireGuardSelector", picker)
        self.assertIn("field.hidden = true", picker)
        self.assertIn("select.tabIndex = -1", picker)
        self.assertIn("$('wg-select')?.value", gate)

    def test_gate_transaction_lock_is_real_and_server_terminal_owned(self):
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("transactionLocked", gate)
        self.assertIn("transactionGuard", gate)
        self.assertIn("form.inert = Boolean(locked)", gate)
        self.assertIn("control.disabled = true;", gate)
        self.assertIn("orb.disabled = !orbEnabled", gate)
        self.assertIn("['done', 'failed', 'expired']", gate)
        self.assertNotIn("65000", gate)
        self.assertIn("setInterval(() => window.RemoteGateApp?.refresh?.(), 1000)", gate)
        self.assertIn("RemoteGateFeedback", gate)
        self.assertIn("正在激活远程访问", gate)
        self.assertIn("正在关闭远程访问", gate)
        self.assertNotIn("正在验证 WireGuard", gate)

    def test_gate_orb_toggles_activate_and_close(self):
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("function toggleAccess()", gate)
        self.assertIn("activeFamilyState(fw, context.state.family)", gate)
        self.assertIn("closeAccess();", gate)
        self.assertIn("else activate();", gate)
        self.assertIn("addEventListener('click',toggleAccess)", gate)
        self.assertIn("const orbLabel = active ? t('gate.close') : t('gate.activate')", gate)

    def test_gate_open_state_is_scoped_to_current_browser_source(self):
        gate = GATE.read_text(encoding="utf-8")
        server = SERVER.read_text(encoding="utf-8")
        self.assertIn("authorized_sources", gate)
        self.assertIn("authorizations", gate)
        self.assertIn("authorizationForSource", gate)
        self.assertIn("sourceExpiresIn", gate)
        self.assertIn('"authorized_sources"', server)
        self.assertIn('"authorizations"', server)
        self.assertIn('"source_count"', server)

    def test_candidate_and_http_observed_sources_remain_visibly_distinct(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn("Carrier candidate", app)
        self.assertIn("Cloudflare HTTP observed", app)
        self.assertIn("without requiring a pre-existing WireGuard handshake", app)
        self.assertNotIn("hints only", app)
        self.assertIn("remote-gate-client-source-diagnostics", app)
        self.assertIn("remote-gate-client-source-updated", app)

    def test_dashboard_render_does_not_overwrite_gate_endpoint_memory(self):
        app = APP.read_text(encoding="utf-8")
        marker = "window.RemoteGateGateControls?.render(data);"
        self.assertIn(marker, app)
        tail = app.split(marker, 1)[1].split("window.RemoteGateFit?.observe();", 1)[0]
        self.assertNotIn("syncEndpointSelect(data)", tail)
        self.assertNotIn("renderClient(data)", tail)

    def test_private_and_egress_paths_remain_available_for_manual_try(self):
        app = APP.read_text(encoding="utf-8")
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("['direct', 'mapped', 'private', 'egress_probe']", app)
        self.assertIn("['direct','mapped','private','egress_probe']", gate)
        self.assertIn("Private/CGNAT · Try", app)
        self.assertIn("NAT egress · Try", app)

    def test_runtime_wireguard_egress_reboots_off_and_supports_split_dual(self):
        egress = OPENWRT_EGRESS.read_text(encoding="utf-8")
        agent = OPENWRT_AGENT.read_text(encoding="utf-8")
        update = OPENWRT_UPDATE.read_text(encoding="utf-8")
        self.assertIn('RUNTIME_DIR="${REMOTE_GATE_RUNTIME_DIR:-/tmp/remote-gate}"', egress)
        self.assertIn('STATE_FILE="$RUNTIME_DIR/wireguard-egress.conf"', egress)
        self.assertNotIn("uci set", egress)
        self.assertIn("schedule_expiry", egress)
        self.assertIn("status-json", egress)
        self.assertIn("enable-split", egress)
        self.assertIn("WAN_INTERFACE4", egress)
        self.assertIn("WAN_INTERFACE6", egress)
        self.assertIn("AllowedIPs = 0.0.0.0/0, ::/0", egress)
        self.assertIn("cleanup-legacy", update)
        self.assertIn("runtime only, reboot returns it to OFF", update)
        self.assertIn('egress_wan_ipv4="$(jsonfilter', agent)
        self.assertIn('egress_wan_ipv6="$(jsonfilter', agent)
        self.assertIn('"$EGRESS" enable-split "$wireguard" "$egress_wan_ipv4" "$egress_wan_ipv6" "$ttl"', agent)
        self.assertIn("apply_egress=0", agent)
        self.assertIn("web-authorization-active-pending-egress", agent)

    def test_scope_defaults_to_wireguard_only(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("state.scope='wg'", source)
        self.assertIn("wg_ping", source)

    def test_vps_installers_already_deploy_changed_runtime_files(self):
        required = (
            "server/remote-gate.py",
            "server/app/client_sources.py",
            "server/app/gate.py",
            "server/app/static/css/feedback.css",
            "server/app/static/js/ui-feedback.js",
            "server/app/static/js/client-sources.js",
            "server/app/static/js/gate-controls.js",
        )
        for path in (INSTALL, UPDATE):
            source = path.read_text(encoding="utf-8")
            for item in required:
                self.assertIn(item, source, f"{path.name}: {item}")


if __name__ == "__main__":
    unittest.main()
