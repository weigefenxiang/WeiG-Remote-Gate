import tempfile
import unittest
from pathlib import Path

from server.app.gate import GateError, queue_activate
from server.app.store import JsonStore


class GateActiveRuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name))
        self.store.write("current.json", {
            "schema": 1,
            "interfaces": {
                "WAN2": {
                    "ip": "203.0.113.10",
                    "device": "pppoe-WAN2",
                    "address_type": "public",
                    "active": True,
                },
            },
        })

    def tearDown(self):
        self.tmp.cleanup()

    def write_status(self, firewall, egress=None):
        self.store.write("agent-status.json", {
            "schema": 3,
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820}],
            "firewall": firewall,
            "egress": egress or {"active": False, "state": "inactive"},
        })

    def activate(self):
        return queue_activate(
            self.store,
            source_ip="198.51.100.7",
            wan_name="WAN2",
            wg_name="WG_HOME",
            ttl=300,
        )

    def test_top_level_active_runtime_requires_close(self):
        self.write_status({
            "active": True,
            "family": "ipv4",
            "scope": "wg_ping",
            "source_ip": "198.51.100.7",
            "device": "pppoe-WAN2",
            "ingress_port": 51820,
        })
        with self.assertRaisesRegex(GateError, "gate_close_required"):
            self.activate()

    def test_family_runtime_requires_close_even_when_legacy_active_flag_is_false(self):
        self.write_status({
            "active": False,
            "families": {
                "ipv4": {"active": False},
                "ipv6": {
                    "active": True,
                    "scope": "wg",
                    "source_ip": "2001:4860:4860::8888",
                    "device": "pppoe-WAN",
                    "ingress_port": 51820,
                },
            },
        })
        with self.assertRaisesRegex(GateError, "gate_close_required"):
            self.activate()

    def test_inactive_gate_runtime_allows_activate(self):
        self.write_status({
            "active": False,
            "families": {
                "ipv4": {"active": False},
                "ipv6": {"active": False},
            },
        })
        command = self.activate()
        self.assertEqual(command["action"], "activate")
        self.assertEqual(command["family"], "ipv4")

    def test_internet_exit_runtime_does_not_become_gate_authority(self):
        self.write_status(
            {"active": False, "families": {"ipv4": {"active": False}, "ipv6": {"active": False}}},
            egress={"active": True, "state": "active", "mode": "ipv4", "wan": "WAN2"},
        )
        command = self.activate()
        self.assertEqual(command["action"], "activate")


if __name__ == "__main__":
    unittest.main()
