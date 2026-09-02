import copy
import unittest

from server.app.endpoints import validate_inventory_v2, validate_inventory_v3


class InventoryBooleanAuthorityTests(unittest.TestCase):
    def v2(self):
        return {
            "schema": 2,
            "generated_at": 1,
            "capabilities": {
                "gate_ipv4": True,
                "gate_ipv6": False,
                "control_ipv4": True,
                "control_ipv6": False,
                "natmap": False,
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
            "natmap": [],
        }

    def v3(self):
        return {
            "schema": 3,
            "generated_at": 1,
            "capabilities": {
                "gate_ipv4": True,
                "gate_ipv6": False,
                "control_ipv4": True,
                "control_ipv6": False,
                "mapped_access": False,
                "mapper_available": False,
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
            "services": [],
            "mappings": [],
        }

    def test_schema2_rejects_string_booleans_in_wan_authority(self):
        for field in ("up", "default_route_v4", "default_route_v6"):
            inventory = copy.deepcopy(self.v2())
            inventory["wans"][0][field] = "false"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "invalid_boolean"):
                validate_inventory_v2(inventory)

    def test_schema3_rejects_string_booleans_in_wan_authority(self):
        for field in ("up", "default_route_v4", "default_route_v6"):
            inventory = copy.deepcopy(self.v3())
            inventory["wans"][0][field] = "false"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "invalid_boolean"):
                validate_inventory_v3(inventory)

    def test_schema2_rejects_string_capability_booleans(self):
        for field in ("gate_ipv4", "gate_ipv6", "control_ipv4", "control_ipv6", "natmap"):
            inventory = copy.deepcopy(self.v2())
            inventory["capabilities"][field] = "false"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "invalid_boolean"):
                validate_inventory_v2(inventory)

    def test_schema3_rejects_string_capability_booleans(self):
        for field in ("gate_ipv4", "gate_ipv6", "control_ipv4", "control_ipv6", "mapped_access", "mapper_available"):
            inventory = copy.deepcopy(self.v3())
            inventory["capabilities"][field] = "false"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "invalid_boolean"):
                validate_inventory_v3(inventory)

    def test_missing_capabilities_keep_legacy_defaults(self):
        v2 = self.v2()
        v2["capabilities"] = {}
        clean2 = validate_inventory_v2(v2)
        self.assertTrue(clean2["capabilities"]["gate_ipv4"])
        self.assertFalse(clean2["capabilities"]["gate_ipv6"])
        self.assertTrue(clean2["capabilities"]["control_ipv4"])

        v3 = self.v3()
        v3["capabilities"] = {}
        clean3 = validate_inventory_v3(v3)
        self.assertTrue(clean3["capabilities"]["gate_ipv4"])
        self.assertFalse(clean3["capabilities"]["gate_ipv6"])
        self.assertTrue(clean3["capabilities"]["control_ipv4"])


if __name__ == "__main__":
    unittest.main()
