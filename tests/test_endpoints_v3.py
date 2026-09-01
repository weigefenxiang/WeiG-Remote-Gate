import tempfile
import unittest
from pathlib import Path

from server.app.endpoints import build_endpoints, validate_inventory_v3
from server.app.gate import queue_activate
from server.app.store import JsonStore


class EndpointV3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name))
        self.store.write("agent-status.json", {
            "schema": 3,
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820}],
        })
        self.inventory = {
            "schema": 3,
            "generated_at": 1,
            "capabilities": {
                "gate_ipv4": True,
                "gate_ipv6": False,
                "control_ipv4": True,
                "control_ipv6": False,
                "mapped_access": True,
                "mapper_available": True,
            },
            "wans": [{
                "name": "WAN",
                "device": "pppoe-WAN",
                "logical_interfaces": ["WAN"],
                "up": True,
                "default_route_v4": True,
                "default_route_v6": False,
                "ipv4": ["100.64.1.2"],
                "ipv6": [],
            }],
            "services": [{
                "id": "wg.WG_HOME",
                "type": "wireguard",
                "transport": "udp",
                "name": "WG_HOME",
                "service_port": 51820,
            }],
            "mappings": [{
                "wan": "WAN",
                "device": "pppoe-WAN",
                "family": "ipv4",
                "transport": "udp",
                "external_address": "1.1.1.1",
                "external_port": 43001,
                "ingress_port": 30001,
                "service_id": "wg.WG_HOME",
                "observed_at": 123,
            }],
        }
        self.store.write("inventory-v3.json", validate_inventory_v3(self.inventory))

    def tearDown(self):
        self.tmp.cleanup()

    def test_mapped_endpoint_keeps_three_port_model(self):
        mapped = [item for item in build_endpoints(self.store) if item["access_method"] == "mapped"]
        self.assertEqual(len(mapped), 1)
        endpoint = mapped[0]
        self.assertEqual(endpoint["reachability"], "mapped")
        self.assertEqual(endpoint["external_port"], 43001)
        self.assertEqual(endpoint["ingress_port"], 30001)
        self.assertEqual(endpoint["service_port"], 51820)
        self.assertEqual(endpoint["service_id"], "wg.WG_HOME")
        self.assertEqual(endpoint["wireguard"], "WG_HOME")

    def test_mapped_activation_queues_only_server_resolved_registration(self):
        endpoint = [item for item in build_endpoints(self.store) if item["access_method"] == "mapped"][0]
        command = queue_activate(
            self.store,
            source_ip="8.8.8.8",
            endpoint_id=endpoint["id"],
            family="ipv4",
            scope="wg",
            ttl=300,
        )
        self.assertEqual(command["schema"], 3)
        self.assertEqual(command["access_method"], "mapped")
        self.assertEqual(command["service_id"], "wg.WG_HOME")
        self.assertEqual(command["service_port"], 51820)
        self.assertEqual(command["ingress_port"], 30001)
        self.assertEqual(command["external_port"], 43001)
        self.assertEqual(command["external_address"], "1.1.1.1")

    def test_unknown_service_mapping_is_dropped(self):
        inventory = dict(self.inventory)
        inventory["mappings"] = [dict(self.inventory["mappings"][0], service_id="wg.DOES_NOT_EXIST")]
        normalized = validate_inventory_v3(inventory)
        self.assertEqual(normalized["mappings"], [])

    def test_mapping_for_unknown_wan_pair_is_dropped(self):
        inventory = dict(self.inventory)
        inventory["mappings"] = [dict(self.inventory["mappings"][0], device="pppoe-WAN2")]
        normalized = validate_inventory_v3(inventory)
        self.assertEqual(normalized["mappings"], [])

    def test_direct_and_mapped_share_service_registration_not_ingress_port(self):
        endpoints = build_endpoints(self.store)
        direct = [item for item in endpoints if item["access_method"] == "direct" and item["family"] == "ipv4"][0]
        mapped = [item for item in endpoints if item["access_method"] == "mapped"][0]
        self.assertEqual(direct["service_id"], mapped["service_id"])
        self.assertEqual(direct["service_port"], mapped["service_port"])
        self.assertNotEqual(direct["ingress_port"], mapped["ingress_port"])


if __name__ == "__main__":
    unittest.main()
