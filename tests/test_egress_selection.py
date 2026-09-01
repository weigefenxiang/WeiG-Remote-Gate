import tempfile
import unittest
from pathlib import Path

from server.app.gate import GateError, _egress_plan, egress_wan, queue_activate
from server.app.store import JsonStore


class EgressSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name))
        self.store.write("current.json", {
            "schema": 1,
            "interfaces": {
                "WAN2": {"ip": "203.0.113.10", "device": "pppoe-WAN2", "address_type": "public", "active": True},
            },
        })
        self.store.write("inventory-v2.json", {
            "schema": 2,
            "generated_at": 1,
            "capabilities": {"gate_ipv4": True, "gate_ipv6": True},
            "natmap": [],
            "wans": [
                {
                    "name": "WAN2",
                    "device": "pppoe-WAN2",
                    "logical_interfaces": ["WAN2"],
                    "up": True,
                    "default_route_v4": True,
                    "default_route_v6": True,
                    "ipv4": [{"address": "203.0.113.10", "kind": "public"}],
                    "ipv6": [{"address": "2001:4860:4860::8888", "kind": "global"}],
                },
                {
                    "name": "WAN",
                    "device": "pppoe-WAN",
                    "logical_interfaces": ["WAN"],
                    "up": True,
                    "default_route_v4": True,
                    "default_route_v6": False,
                    "ipv4": [{"address": "172.20.182.224", "kind": "private"}],
                    "ipv6": [],
                },
                {
                    "name": "V6ONLY",
                    "device": "eth8",
                    "logical_interfaces": ["V6ONLY"],
                    "up": True,
                    "default_route_v4": False,
                    "default_route_v6": True,
                    "ipv4": [],
                    "ipv6": [{"address": "2001:4860:4860::8844", "kind": "global"}],
                },
                {
                    "name": "AUX",
                    "device": "eth9",
                    "logical_interfaces": ["AUX"],
                    "up": True,
                    "default_route_v4": False,
                    "default_route_v6": False,
                    "ipv4": [{"address": "192.168.50.2", "kind": "private"}],
                    "ipv6": [],
                },
            ],
        })
        self.store.write("agent-status.json", {
            "schema": 3,
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820}],
        })

    def tearDown(self):
        self.tmp.cleanup()

    def reset_queue(self):
        self.store.write("commands.json", {"pending": None, "next": [], "last": None})

    def activate(self, egress_name=""):
        return queue_activate(
            self.store,
            source_ip="198.51.100.7",
            wan_name="WAN2",
            wg_name="WG_HOME",
            egress_name=egress_name,
            ttl=300,
        )

    def test_lan_only_keeps_egress_empty(self):
        self.assertEqual(self.activate()["egress_wan"], "")

    def test_public_or_cgnat_default_wan_can_be_selected_as_ipv4_exit(self):
        self.assertEqual(self.activate("WAN2")["egress_wan"], "WAN2")
        self.reset_queue()
        command = self.activate("WAN")
        self.assertEqual(command["egress_wan"], "WAN")
        self.assertEqual(command["egress_mode"], "ipv4")

    def test_dual_exit_requires_both_default_routes_and_global_ipv6(self):
        self.assertEqual(egress_wan(self.store, "WAN2", "dual"), "WAN2")
        with self.assertRaisesRegex(GateError, "egress_ipv6_unavailable"):
            egress_wan(self.store, "WAN", "dual")
        with self.assertRaisesRegex(GateError, "egress_ipv4_unavailable"):
            egress_wan(self.store, "V6ONLY", "dual")

    def test_split_dual_plan_keeps_family_wans_and_clears_legacy_shared_wan(self):
        legacy, wan4, wan6, mode = _egress_plan(
            self.store,
            egress_name="",
            egress_names={"ipv4": "WAN", "ipv6": "V6ONLY"},
            mode="dual",
        )
        self.assertEqual((legacy, wan4, wan6, mode), ("", "WAN", "V6ONLY", "dual"))

    def test_same_wan_dual_plan_preserves_legacy_compatibility(self):
        split = _egress_plan(
            self.store,
            egress_name="",
            egress_names={"ipv4": "WAN2", "ipv6": "WAN2"},
            mode="dual",
        )
        legacy = _egress_plan(
            self.store,
            egress_name="WAN2",
            egress_names=None,
            mode="dual",
        )
        self.assertEqual(split, ("WAN2", "WAN2", "WAN2", "dual"))
        self.assertEqual(legacy, split)

    def test_incomplete_split_dual_plan_fails_closed(self):
        with self.assertRaisesRegex(GateError, "dual_egress_incomplete"):
            _egress_plan(
                self.store,
                egress_name="",
                egress_names={"ipv4": "WAN"},
                mode="dual",
            )

    def test_ipv6_exit_requires_default_route_and_global_ipv6(self):
        self.assertEqual(egress_wan(self.store, "WAN2", "ipv6"), "WAN2")
        self.assertEqual(egress_wan(self.store, "V6ONLY", "ipv6"), "V6ONLY")
        with self.assertRaisesRegex(GateError, "egress_ipv6_unavailable"):
            egress_wan(self.store, "WAN", "ipv6")

    def test_ipv4_exit_rejects_ipv6_only_or_non_default_wan(self):
        with self.assertRaisesRegex(GateError, "egress_ipv4_unavailable"):
            egress_wan(self.store, "V6ONLY", "ipv4")
        with self.assertRaisesRegex(GateError, "egress_ipv4_unavailable"):
            self.activate("AUX")

    def test_invalid_or_unknown_exit_is_rejected(self):
        with self.assertRaisesRegex(GateError, "invalid_egress_mode"):
            egress_wan(self.store, "WAN2", "invalid")
        with self.assertRaisesRegex(GateError, "egress_wan_unavailable"):
            self.activate("MISSING")


if __name__ == "__main__":
    unittest.main()
