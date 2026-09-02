from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENT = (ROOT / "openwrt" / "remote-gate-agent.sh").read_text(encoding="utf-8")
FIREWALL = (ROOT / "openwrt" / "remote-gate-firewall.sh").read_text(encoding="utf-8")
BACKENDS = (ROOT / "openwrt" / "remote-gate-firewall-backends.sh").read_text(encoding="utf-8")
MAPPING = (ROOT / "openwrt" / "remote-gate-mapping.sh").read_text(encoding="utf-8")
REGISTRY = (ROOT / "openwrt" / "remote-gate-service-registry.sh").read_text(encoding="utf-8")
APP = (ROOT / "server" / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
GATE_CONTROLS = (ROOT / "server" / "app" / "static" / "js" / "gate-controls.js").read_text(encoding="utf-8")
ENDPOINT_PICKER = (ROOT / "server" / "app" / "static" / "js" / "endpoint-picker.js").read_text(encoding="utf-8")
FIT_TEXT = (ROOT / "server" / "app" / "static" / "js" / "fit-text.js").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "server" / "app" / "static" / "js" / "theme-bootstrap.js").read_text(encoding="utf-8")
DASHBOARD_CSS = (ROOT / "server" / "app" / "static" / "css" / "dashboard.css").read_text(encoding="utf-8")
DESIGN = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
MAPPER = (ROOT / "native" / "remote-gate-mapper.c").read_text(encoding="utf-8")


class MappedAccessContractTests(unittest.TestCase):
    def test_agent_keeps_wireguard_ports_mapped_pairs_and_control_separate(self):
        self.assertIn('wg_ports="$(wireguard_ports', AGENT)
        self.assertIn('mapped_pairs="$(mapped_ingress_pairs', AGENT)
        self.assertIn('mapped_control="$(mapped_control_pairs', AGENT)
        self.assertIn('sync "$v4" "$v6" "$wg_ports" "$mapped_pairs" "$mapped_control"', AGENT)
        self.assertNotIn('registered_ingress_ports()', AGENT)

    def test_firewall_authorizes_only_current_registered_ingress(self):
        self.assertIn('MAPPED_INGRESS_V4_FILE=', FIREWALL)
        self.assertIn('MAPPED_CONTROL_V4_FILE=', FIREWALL)
        self.assertIn('protected_ingress_current()', FIREWALL)
        self.assertIn('"${rg_dev}|${rg_port}"', FIREWALL)

    def test_fw4_uses_device_port_tuple_for_mapped_ingress(self):
        self.assertIn('type ifname . inet_service', BACKENDS)
        self.assertIn('iifname . udp dport @weig_remote_gate_mapped_ingress_v4', BACKENDS)
        self.assertIn('"$rg_dev" . $rg_port', BACKENDS)

    def test_fw3_uses_exact_device_and_port_drop(self):
        self.assertIn('fw3_load_mapped_drops_v4()', BACKENDS)
        self.assertIn('-i "$rg_dev" -p udp --dport "$rg_port" -j DROP', BACKENDS)

    def test_stun_control_is_exact_and_precedes_mapped_drop(self):
        self.assertIn('control-pairs', MAPPING)
        self.assertIn("'@.stun_address'", MAPPING)
        self.assertIn("'@.stun_port'", MAPPING)
        self.assertIn('type ifname . inet_service . ipv4_addr . inet_service', BACKENDS)
        self.assertIn('iifname . udp dport . ip saddr . udp sport @weig_remote_gate_mapped_control_v4', BACKENDS)
        self.assertIn('-s "$rg_stun_ip" --sport "$rg_stun_port" --dport "$rg_ingress" -j ACCEPT', BACKENDS)
        self.assertLess(
            BACKENDS.index('!WeiG Remote Gate: mapped STUN control'),
            BACKENDS.index('!WeiG Remote Gate: protected IPv4 mapped ingress'),
        )
        self.assertLess(
            BACKENDS.index('fw3_load_mapped_control_v4\n'),
            BACKENDS.index('fw3_load_mapped_drops_v4\n'),
        )

    def test_mapper_waits_for_firewall_go_signal_and_publishes_stun_peer(self):
        self.assertIn('--go-file', MAPPING)
        self.assertIn('activate-prepared', MAPPING)
        self.assertIn('status_control_tuple', MAPPING)
        self.assertIn('go_file', MAPPER)
        self.assertIn('wait_for_go', MAPPER)
        self.assertIn('stun_address', MAPPER)
        self.assertIn('stun_port', MAPPER)

    def test_stun_allow_cannot_become_service_data_bypass(self):
        self.assertIn('if (!sockaddr_equal(&source, stun_server)) continue;', MAPPER)
        self.assertIn('if (sockaddr_equal(&source, stun_server)) {', MAPPER)
        stun_block = MAPPER.split('if (sockaddr_equal(&source, stun_server)) {', 1)[1].split('int index = find_session', 1)[0]
        self.assertIn('parse_stun_mapping', stun_block)
        self.assertIn('continue;', stun_block)

    def test_service_registry_is_the_only_service_authority(self):
        self.assertIn('validate)', REGISTRY)
        self.assertIn('"$SERVICES" validate', MAPPING)
        self.assertIn('service-not-registered', AGENT)
        self.assertIn('service-wireguard-mismatch', AGENT)

    def test_ui_uses_access_method_not_natmap_branding(self):
        self.assertNotIn("function endpointLabel", APP)
        self.assertNotIn("provider === 'natmap'", APP)
        self.assertIn("item?.access_method === 'mapped' || item?.reachability === 'mapped'", GATE_CONTROLS)
        self.assertIn("return 'Mapped'", GATE_CONTROLS)
        self.assertNotIn("provider === 'natmap'", GATE_CONTROLS)
        self.assertNotIn("return 'NATMap'", GATE_CONTROLS)
        self.assertIn("option?.dataset?.pathPrimary === '1'", ENDPOINT_PICKER)
        self.assertNotIn('/Direct|NATMap/', ENDPOINT_PICKER)
        self.assertIn('Direct', DESIGN)
        self.assertIn('Mapped', DESIGN)
        self.assertIn('NAT egress', DESIGN)
        self.assertIn("show Private/CGNAT as a selectable public Access Endpoint", DESIGN)
        self.assertNotIn('Direct / Mapped / NAT egress / Private-CGNAT', DESIGN)

    def test_network_identity_text_uses_one_shared_fit_engine(self):
        self.assertIn("hero: {max: 22, min: 7.5, floor: 6}", FIT_TEXT)
        self.assertIn("value: {max: 20, min: 7.5, floor: 6}", FIT_TEXT)
        self.assertIn("identity: {max: 17, min: 8.5, floor: 7}", FIT_TEXT)
        self.assertIn("compact: {max: 13, min: 7.5, floor: 6}", FIT_TEXT)
        for selector in (
            '.verified-endpoint-value',
            '.address-value',
            '.wan-address-copy',
            '.endpoint-trigger-copy strong',
            '.endpoint-option-topline strong',
            '.wan-row h3',
            '.endpoint-trigger-address',
            '.endpoint-option-address',
        ):
            self.assertIn(selector, FIT_TEXT)
        self.assertIn("element.classList.add('fit-single-line')", FIT_TEXT)
        self.assertIn("setProperty('font-size', `${Math.max(1, size).toFixed(1)}px`, 'important')", FIT_TEXT)
        self.assertIn("{subtree: true, childList: true, characterData: true}", FIT_TEXT)
        self.assertIn('NetworkIdentityText', DESIGN)
        self.assertIn('Do not create IPv6-, Endpoint-, WAN- or Dual-specific fitting utilities.', DESIGN)
        self.assertIn('whole-page horizontal overflow is a contract failure', DESIGN)

    def test_activate_resolves_latest_mapping_on_openwrt(self):
        self.assertIn('resolve-current <wan> <device> <service-id>', MAPPING)
        self.assertIn('wan="$(jsonfilter -i "$BODY" -e \'@.wan\'', AGENT)
        self.assertIn('"$MAPPING" resolve-current "$wan" "$device" "$service_id"', AGENT)
        self.assertIn('mapped-endpoint:${external_address}:${external_port}', AGENT)
        activate = AGENT.split('case "$action" in', 1)[1].split('close)', 1)[0]
        self.assertLess(activate.index('sync_firewall_policy || true'), activate.index('"$MAPPING" resolve-current'))
        self.assertLess(activate.index('"$MAPPING" resolve-current'), activate.index('"$FIREWALL" activate'))

    def test_mapped_endpoint_display_uses_confirmed_selection_without_option_rewriting(self):
        self.assertNotIn('function rewriteMappedOptions()', BOOTSTRAP)
        self.assertNotIn("const mappedIndex = parts.indexOf('Mapped')", BOOTSTRAP)
        self.assertNotIn('function observeMappedPicker()', BOOTSTRAP)
        self.assertIn('function selectedEndpointRecord(data)', BOOTSTRAP)
        self.assertIn("select.dataset.selectionConfirmed !== '1'", BOOTSTRAP)
        self.assertIn('function selectedPublicEndpoint(data)', BOOTSTRAP)

    def test_current_mapped_endpoint_matches_selected_mapping_and_is_copyable(self):
        self.assertIn('function selectedEndpointRecord(data)', BOOTSTRAP)
        self.assertIn('function mappedEndpoint(data, selected)', BOOTSTRAP)
        self.assertIn('inventory?.mappings', BOOTSTRAP)
        self.assertIn("String(item.wan || '') === String(selected.wan || '')", BOOTSTRAP)
        self.assertIn("String(item.device || '') === String(selected.device || '')", BOOTSTRAP)
        self.assertIn("String(item.service_id || '') === String(selected.service_id || '')", BOOTSTRAP)
        self.assertIn('Number(b.observed_at || 0) - Number(a.observed_at || 0)', BOOTSTRAP)
        self.assertIn('当前 WireGuard 公网 Endpoint', BOOTSTRAP)
        self.assertIn('Current WireGuard Public Endpoint', BOOTSTRAP)
        self.assertIn('OpenWrt 持续观测，Activate 时实时确认', BOOTSTRAP)
        self.assertIn('navigator.clipboard.writeText(text)', BOOTSTRAP)
        self.assertIn('copyFallback(text)', BOOTSTRAP)
        self.assertIn('RemoteGateFeedback?.notify', BOOTSTRAP)
        self.assertNotIn('data-mapped-copy-hint', BOOTSTRAP)
        self.assertNotIn("textContent = zh() ? '点击复制'", BOOTSTRAP)

    def test_gate_status_component_separates_orb_side_meta_and_endpoint(self):
        self.assertIn('function ensureGateStatusStructure()', BOOTSTRAP)
        self.assertIn("shortState.id = 'gate-orb-state'", BOOTSTRAP)
        self.assertIn("stage.className = 'gate-status-stage'", BOOTSTRAP)
        self.assertIn("left.dataset.gateStatusSide = 'left'", BOOTSTRAP)
        self.assertIn("right.dataset.gateStatusSide = 'right'", BOOTSTRAP)
        self.assertIn("return zh() ? ['WAN 入口', '保持隐藏']", BOOTSTRAP)
        self.assertIn("copy.id = 'gate-status-copy'", BOOTSTRAP)
        self.assertIn('copy.append(state)', BOOTSTRAP)
        self.assertIn('copy.append(substate)', BOOTSTRAP)
        self.assertIn("if (state === 'open') return 'OPEN'", BOOTSTRAP)
        self.assertIn("if (state === 'authorizing') return 'WAIT'", BOOTSTRAP)
        self.assertIn("row.className = 'verified-endpoint'", BOOTSTRAP)
        self.assertNotIn('ensureGatePolishStyles', BOOTSTRAP)
        self.assertNotIn('gate-orb-polish-styles', BOOTSTRAP)
        self.assertNotIn("document.createElement('style')", BOOTSTRAP)

    def test_verified_endpoint_uses_shared_tokens_and_respects_reduced_motion(self):
        self.assertIn('.gate-status-stage', DASHBOARD_CSS)
        self.assertIn('grid-template-areas: "left orb right"', DASHBOARD_CSS)
        self.assertIn('.verified-endpoint-value', DASHBOARD_CSS)
        self.assertIn('color: var(--success)', DASHBOARD_CSS)
        self.assertIn('remote-gate-endpoint-verified', DASHBOARD_CSS)
        self.assertIn('@media (prefers-reduced-motion: reduce)', DASHBOARD_CSS)
        self.assertIn('@media (max-width: 767px)', DASHBOARD_CSS)
        self.assertIn('grid-template-columns: 1fr;', DASHBOARD_CSS)


if __name__ == "__main__":
    unittest.main()
