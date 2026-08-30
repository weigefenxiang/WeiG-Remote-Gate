import tempfile
import unittest
from pathlib import Path

from server.app.gate import GateError, ack_command, pull_command, queue_activate
from server.app.store import JsonStore


class GateTests(unittest.TestCase):
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
                "WAN": {
                    "ip": "192.168.1.2",
                    "device": "eth0",
                    "address_type": "private",
                    "active": True,
                },
            },
        })
        self.store.write("agent-status.json", {
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820}]
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_browser_source_is_bound_into_command(self):
        command = queue_activate(
            self.store,
            source_ip="198.51.100.7",
            wan_name="WAN2",
            wg_name="WG_HOME",
            ttl=300,
        )
        self.assertEqual(command["source_ip"], "198.51.100.7")
        self.assertEqual(command["device"], "pppoe-WAN2")
        self.assertEqual(command["wg_port"], 51820)

    def test_private_wan_is_rejected(self):
        with self.assertRaises(GateError):
            queue_activate(
                self.store,
                source_ip="198.51.100.7",
                wan_name="WAN",
                wg_name="WG_HOME",
                ttl=300,
            )

    def test_command_is_consumed_once(self):
        command = queue_activate(
            self.store,
            source_ip="198.51.100.7",
            wan_name="WAN2",
            wg_name="WG_HOME",
            ttl=300,
        )
        pulled = pull_command(self.store)
        self.assertEqual(pulled["id"], command["id"])
        self.assertTrue(ack_command(self.store, command["id"], True, "ok"))
        self.assertIsNone(pull_command(self.store))
        self.assertFalse(ack_command(self.store, command["id"], True, "again"))


if __name__ == "__main__":
    unittest.main()
