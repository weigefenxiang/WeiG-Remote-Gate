import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "openwrt/remote-gate-wireguard-egress.sh"
AGENT = ROOT / "openwrt/remote-gate-agent.sh"
UPDATER = ROOT / "openwrt/update.sh"
SERVER = ROOT / "server/remote-gate.py"
GATE = ROOT / "server/app/static/js/gate-controls.js"


class DualEgressRuntimeContractTests(unittest.TestCase):
    def test_wireguard_ula_is_detected_from_interface_address(self):
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn('ip -6 addr show dev "$device"', source)
        self.assertIn('addr ~ /^(fc|fd)/', source)
        self.assertNotIn('ip -6 route show dev "$device" scope link', source)
        self.assertIn('ip -6 route show dev "$device"', source)

    def test_ipv6_policy_table_drops_isp_source_specific_from_clause(self):
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn('gateway="$(printf', source)
        self.assertIn('if ($i=="via")', source)
        self.assertIn('ip -6 route replace table "$table" default via "$gateway" dev "$wan_dev"', source)
        self.assertIn('ip -6 route replace table "$table" default dev "$wan_dev"', source)

    def test_dual_egress_remains_runtime_only_and_transactional(self):
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn('RUNTIME_DIR="${REMOTE_GATE_RUNTIME_DIR:-/tmp/remote-gate}"', source)
        self.assertIn('enable-split <wireguard-interface> <ipv4-wan> <ipv6-wan>', source)
        self.assertIn('enable_egress_plan "$1" "$2" "$3" "${4:-300}" dual', source)
        self.assertIn('rollback "Cannot build IPv4 default route through $wan4"', source)
        self.assertIn('rollback "Cannot build IPv6 default route through $wan6"', source)
        self.assertIn('rollback "IPv6 nft NAT66 installation failed"', source)
        self.assertIn('WAN_INTERFACE4=\'$WAN_INTERFACE4\'', source)
        self.assertIn('WAN_INTERFACE6=\'$WAN_INTERFACE6\'', source)
        self.assertIn('runtime_cleanup "${FIREWALL_BACKEND:-}"', source)
        self.assertIn('Persistent UCI egress rules: no', source)
        self.assertIn('AllowedIPs = 0.0.0.0/0, ::/0', source)

    def test_selected_wan_policy_route_change_clears_egress(self):
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn('egress_policy_route_current()', source)
        self.assertIn('interface_up "$wan" || return 1', source)
        self.assertIn('[ "$current_dev" = "$saved_dev" ] || return 1', source)
        self.assertIn('route show default dev "$current_dev"', source)
        self.assertIn('route show table "$table" default dev "$current_dev"', source)
        self.assertIn('egress_policy_route_current -4 "$wan4" "$saved_dev4" "${ROUTE_TABLE4:-}"', source)
        self.assertIn('egress_policy_route_current -6 "$wan6" "$saved_dev6" "${ROUTE_TABLE6:-}"', source)
        self.assertIn('WireGuard egress WAN or policy route changed and was cleared', source)

    def test_failed_egress_state_survives_refresh_but_not_close(self):
        helper = HELPER.read_text(encoding="utf-8")
        agent = AGENT.read_text(encoding="utf-8")
        self.assertIn('ERROR_FILE="$RUNTIME_DIR/wireguard-egress-error.conf"', helper)
        self.assertIn("STATE='failed'", helper)
        self.assertIn('\"state\":\"failed\"', helper)
        self.assertIn('clear_error_state', helper)
        self.assertIn('egress="$(egress_json)"', agent)
        self.assertIn('\\"egress\\":${egress}', agent)
        self.assertIn('detail="wireguard-egress-activation-failed"', agent)
        self.assertIn('ack "$id" false "$detail"', agent)

    def test_agent_applies_one_split_dual_transaction(self):
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn("egress_wan_ipv4", source)
        self.assertIn("egress_wan_ipv6", source)
        self.assertIn('"$EGRESS" enable-split "$wireguard" "$egress_wan_ipv4" "$egress_wan_ipv6" "$ttl"', source)
        self.assertIn('rollback_batch_access "$batch_count"', source)
        self.assertIn('incomplete-dual-egress-plan', source)

    def test_vps_sanitizes_and_persists_agent_egress(self):
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn('def _clean_egress(value: object) -> dict:', source)
        self.assertIn('{"inactive", "active", "failed"}', source)
        self.assertIn('egress = _clean_egress(data.get("egress"))', source)
        self.assertIn('"egress": egress', source)
        self.assertIn('"wan_v4"', source)
        self.assertIn('"wan_v6"', source)

    def test_ui_does_not_mask_exit_failure_with_gate_open(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn('function reportedEgress', source)
        self.assertIn('function egressMatchesSelection', source)
        self.assertIn("egress.state === 'failed'", source)
        self.assertIn('OPEN · EXIT FAILED', source)
        self.assertIn('EXIT FAILED', source)
        self.assertIn('EXIT ACTIVE', source)
        self.assertIn('OPEN · EXIT OFF', source)

    def test_upgrade_keeps_legacy_cleanup(self):
        source = UPDATER.read_text(encoding="utf-8")
        self.assertIn('remote-gate-wireguard-egress.sh" cleanup-legacy', source)


if __name__ == "__main__":
    unittest.main()
