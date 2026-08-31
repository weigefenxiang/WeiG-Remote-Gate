import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOTPLUG = ROOT / "openwrt/remote-gate-hotplug.sh"
INIT = ROOT / "openwrt/remote-gate-agent.init"


class ReturnRoutingTests(unittest.TestCase):
    def test_ipv4_and_ipv6_have_independent_auth_and_route_state(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        for token in (
            "authorization-ipv4", "authorization-ipv6",
            "return-route-ipv4", "return-route-ipv6",
            "return-route-verify-ipv4", "return-route-verify-ipv6",
        ):
            self.assertIn(token, source)
        self.assertIn("return_route_sync_family ipv4", source)
        self.assertIn("return_route_sync_family ipv6", source)

    def test_return_route_is_router_local_and_per_destination(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        self.assertIn('iif lo to "$rg_target" lookup "$rg_table"', source)
        self.assertIn('rg_target="$rg_source/32"', source)
        self.assertIn('rg_target="$rg_source/128"', source)
        self.assertNotIn("FORWARD", source)
        self.assertNotIn("DNAT", source)

    def test_policy_table_and_wireguard_port_are_dynamic(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        self.assertIn("candidate_tables", source)
        self.assertIn("existing_table_for_device", source)
        self.assertIn("choose_owned_table", source)
        self.assertIn('rg_port="$(sed -n', source)
        self.assertNotIn("pppoe-WAN2", source)
        self.assertNotIn("51820", source)

    def test_verification_route_overrides_only_requested_family_then_restores(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        self.assertIn("verify_route_set", source)
        self.assertIn("verify_route_clear", source)
        self.assertIn("family_verify_route_file", source)
        self.assertIn("return_route_sync_family \"$rg_family\"", source)

    def test_lifecycle_starts_and_clears_return_route_loop(self):
        source = INIT.read_text(encoding="utf-8")
        self.assertIn("return-route-loop", source)
        self.assertIn("return-route-clear", source)


if __name__ == "__main__":
    unittest.main()
