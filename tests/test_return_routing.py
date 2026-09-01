import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOTPLUG = ROOT / "openwrt/remote-gate-hotplug.sh"
INIT = ROOT / "openwrt/remote-gate-agent.init"


class ReturnRoutingTests(unittest.TestCase):
    def test_ipv4_and_ipv6_have_independent_multi_source_auth_and_route_state(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        for token in (
            "authorization-ipv4.d", "authorization-ipv6.d",
            "return-route-ipv4.d", "return-route-ipv6.d",
            "return-route-verify-ipv4", "return-route-verify-ipv6",
        ):
            self.assertIn(token, source)
        self.assertIn("read_route_sources", source)
        self.assertIn("sync_return_route_record", source)
        self.assertIn("return_route_sync_family ipv4", source)
        self.assertIn("return_route_sync_family ipv6", source)

    def test_return_route_is_router_local_and_per_destination(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        self.assertIn('iif lo to "$rg_target" lookup "$rg_table"', source)
        self.assertIn('rg_target="$rg_source/32"', source)
        self.assertIn('rg_target="$rg_source/128"', source)
        self.assertNotIn("FORWARD", source)
        self.assertNotIn("DNAT", source)

    def test_each_authorized_source_gets_independent_route_state(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        self.assertIn("return_state_file_for_source", source)
        self.assertIn("route_state_key", source)
        self.assertIn('for rg_file in "$rg_auth_dir"/*', source)
        self.assertIn("awk '!seen[$1]++'", source)
        self.assertIn('grep -Fqx "$rg_key" "$rg_active"', source)

    def test_policy_table_and_wireguard_port_are_dynamic(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        self.assertIn("candidate_tables", source)
        self.assertIn("existing_table_for_device", source)
        self.assertIn("choose_owned_table", source)
        self.assertIn('rg_port="$(sed -n', source)
        self.assertNotIn("pppoe-WAN2", source)
        self.assertNotIn("51820", source)

    def test_ipv6_reuses_device_policy_table_without_unsupported_route_get_table(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        self.assertIn("table_default_device", source)
        self.assertIn('ip "$rg_flag" route show table "$rg_table"', source)
        self.assertNotIn('route get "$rg_source" table "$rg_table"', source)

    def test_ipv6_owned_fallback_uses_explicit_wan_source_address(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        self.assertIn("device_global_ipv6_sources", source)
        self.assertIn('ip -6 addr show dev "$rg_wanted" scope global', source)
        self.assertIn('ip -6 route get "$rg_source" from "$rg_local_src" oif "$rg_wanted"', source)
        self.assertIn('src "$rg_local_src"', source)

    def test_verification_route_is_diagnostic_and_family_scoped(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        self.assertIn("verify_route_set", source)
        self.assertIn("verify_route_clear", source)
        self.assertIn("family_verify_route_file", source)
        self.assertIn("return_route_sync_family \"$rg_family\"", source)

    def test_interface_down_immediately_resyncs_gate_and_return_routes(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        event_block = source.split('case "${ACTION:-}" in', 1)[1]
        self.assertIn("ifdown)", event_block)
        self.assertIn("resync_gate_once", event_block)
        self.assertIn("remote-gate-agent.sh sync-firewall", source)
        self.assertIn('"$0" return-route-sync', source)
        self.assertNotIn("FORWARD", event_block)
        self.assertNotIn("DNAT", event_block)
        self.assertNotIn("wg set", event_block)

    def test_interface_up_retries_resync_while_netifd_settles(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        event_block = source.split('case "${ACTION:-}" in', 1)[1]
        settle = source.split("resync_gate_after_settle() {", 1)[1].split('case "${1:-}" in', 1)[0]
        self.assertIn("ifup|ifupdate|update)", event_block)
        self.assertIn("interface-resync-settle", event_block)
        self.assertEqual(settle.count("resync_gate_once"), 4)
        self.assertIn("sleep 2", settle)
        self.assertIn("sleep 5", settle)
        self.assertIn("sleep 10", settle)

    def test_lifecycle_starts_and_clears_return_route_loop(self):
        source = INIT.read_text(encoding="utf-8")
        self.assertIn("return-route-loop", source)
        self.assertIn("return-route-clear", source)


if __name__ == "__main__":
    unittest.main()
