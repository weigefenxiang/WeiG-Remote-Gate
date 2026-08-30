import tempfile
import unittest
from pathlib import Path

from server.app.endpoints import build_endpoints, observe_wan_egress, validate_inventory_v2
from server.app.gate import queue_activate
from server.app.store import JsonStore


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name))
        self.store.write("agent-status.json", {
            "schema": 2,
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820}],
        })
        self.inventory = {
            "schema": 2,
            "generated_at": 1,
            "capabilities": {
                "gate_ipv4": True,
                "gate_ipv6": True,
                "control_ipv4": True,
                "control_ipv6": True,
                "natmap": False,
            },
            "wans": [
                {
                    "name": "WAN",
                    "device": "pppoe-WAN",
                    "logical_interfaces": ["WAN", "WAN_6"],
                    "up": True,
                    "default_route_v4": True,
                    "default_route_v6": True,
                    "ipv4": ["172.20.111.32"],
                    "ipv6": ["2606:4700:4700::1111"],
                },
                {
                    "name": "WAN2",
                    "device": "pppoe-WAN2",
                    "logical_interfaces": ["WAN2", "WAN2_6"],
                    "up": True,
                    "default_route_v4": True,
                    "default_route_v6": True,
                    "ipv4": ["8.8.8.8"],
                    "ipv6": ["2606:4700:4700::1001"],
                },
            ],
            "natmap": [],
        }
        self.store.write("inventory-v2.json", validate_inventory_v2(self.inventory))

    def tearDown(self):
        self.tmp.cleanup()

    def test_public_ipv4_is_first_and_private_ipv4_is_last(self):
        endpoints = build_endpoints(self.store)
        self.assertEqual(endpoints[0]["wan"], "WAN2")
        self.assertEqual(endpoints[0]["family"], "ipv4")
        self.assertEqual(endpoints[0]["reachability"], "direct")
        self.assertEqual(endpoints[-1]["wan"], "WAN")
        self.assertEqual(endpoints[-1]["family"], "ipv4")
        self.assertEqual(endpoints[-1]["reachability"], "private")

    def test_global_ipv6_on_private_ipv4_wan_is_reachable(self):
        endpoints = build_endpoints(self.store)
        wan_v6 = [x for x in endpoints if x["wan"] == "WAN" and x["family"] == "ipv6"][0]
        self.assertEqual(wan_v6["reachability"], "direct")

    def test_private_wan_egress_probe_creates_public_try_endpoint(self):
        observe_wan_egress(self.store, "pppoe-WAN", "1.1.1.1", now=100)
        endpoints = build_endpoints(self.store)
        egress = [x for x in endpoints if x.get("provider") == "egress_probe"][0]
        self.assertEqual(egress["wan"], "WAN")
        self.assertEqual(egress["device"], "pppoe-WAN")
        self.assertEqual(egress["external_address"], "1.1.1.1")
        self.assertEqual(egress["external_port"], 51820)
        self.assertEqual(egress["reachability"], "egress_probe")
        self.assertLess(egress["priority"], 90)

    def test_egress_probe_endpoint_can_be_attempted(self):
        observe_wan_egress(self.store, "pppoe-WAN", "1.1.1.1")
        endpoint = [x for x in build_endpoints(self.store) if x.get("provider") == "egress_probe"][0]
        command = queue_activate(
            self.store,
            source_ip="8.8.4.4",
            endpoint_id=endpoint["id"],
            family="ipv4",
            scope="wg",
            ttl=300,
        )
        self.assertEqual(command["provider"], "egress_probe")
        self.assertEqual(command["reachability"], "egress_probe")
        self.assertEqual(command["external_address"], "1.1.1.1")
        self.assertEqual(command["device"], "pppoe-WAN")

    def test_expired_egress_probe_is_not_an_endpoint(self):
        observe_wan_egress(self.store, "pppoe-WAN", "1.1.1.1", now=100)
        # Store timestamps are deliberately old compared with wall clock.
        endpoints = build_endpoints(self.store)
        self.assertFalse(any(x.get("provider") == "egress_probe" for x in endpoints))

    def test_ipv6_activation_uses_exact_source_and_wg_only_scope(self):
        endpoint = [x for x in build_endpoints(self.store) if x["wan"] == "WAN" and x["family"] == "ipv6"][0]
        command = queue_activate(
            self.store,
            source_ip="2001:4860:4860::8888",
            endpoint_id=endpoint["id"],
            family="ipv6",
            scope="wg",
            ttl=300,
        )
        self.assertEqual(command["family"], "ipv6")
        self.assertEqual(command["source_ip"], "2001:4860:4860::8888")
        self.assertEqual(command["scope"], "wg")
        self.assertEqual(command["device"], "pppoe-WAN")
        self.assertEqual(command["wg_port"], 51820)

    def test_private_ipv4_endpoint_can_be_attempted_manually(self):
        endpoint = [x for x in build_endpoints(self.store) if x["wan"] == "WAN" and x["family"] == "ipv4"][0]
        command = queue_activate(
            self.store,
            source_ip="1.1.1.1",
            endpoint_id=endpoint["id"],
            family="ipv4",
            scope="wg",
            ttl=300,
        )
        self.assertEqual(command["reachability"], "private")
        self.assertEqual(command["device"], "pppoe-WAN")
        self.assertEqual(command["external_address"], "172.20.111.32")

    def test_advanced_gate_waits_for_schema2_agent(self):
        self.store.write("agent-status.json", {
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820}],
        })
        endpoint = [x for x in build_endpoints(self.store) if x["wan"] == "WAN" and x["family"] == "ipv6"][0]
        with self.assertRaisesRegex(ValueError, "agent_upgrade_required"):
            queue_activate(
                self.store,
                source_ip="2001:4860:4860::8888",
                endpoint_id=endpoint["id"],
                family="ipv6",
                scope="wg",
                ttl=300,
            )


if __name__ == "__main__":
    unittest.main()
