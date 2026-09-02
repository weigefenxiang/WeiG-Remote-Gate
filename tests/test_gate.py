import tempfile
import time
import unittest
from pathlib import Path

from server.app.endpoints import build_endpoints
from server.app.gate import GateError, ack_command, gate_view, pull_command, queue_activate, queue_close, valid_ttl
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

    def activate(self, ttl=300):
        return queue_activate(
            self.store,
            source_ip="198.51.100.7",
            wan_name="WAN2",
            wg_name="WG_HOME",
            ttl=ttl,
        )

    def test_browser_source_is_bound_into_command(self):
        command = self.activate()
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

    def test_private_endpoint_id_is_rejected_by_gate_authority(self):
        self.store.write("inventory-v2.json", {
            "schema": 2,
            "generated_at": int(time.time()),
            "wans": [{
                "name": "WAN",
                "device": "eth0",
                "logical_interfaces": ["WAN"],
                "up": True,
                "default_route_v4": True,
                "default_route_v6": False,
                "ipv4": [{"address": "10.0.0.2"}],
                "ipv6": [],
            }],
            "natmap": [],
            "capabilities": {"gate_ipv4": True, "gate_ipv6": False},
        })
        self.store.write("agent-status.json", {
            "schema": 2,
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820}],
        })
        private_endpoint = next(
            endpoint for endpoint in build_endpoints(self.store)
            if endpoint.get("reachability") == "private"
        )

        with self.assertRaisesRegex(GateError, "endpoint_not_reachable"):
            queue_activate(
                self.store,
                source_ip="198.51.100.7",
                endpoint_id=str(private_endpoint["id"]),
                family="ipv4",
                ttl=300,
            )

    def test_preset_ttls_remain_valid(self):
        for ttl in (60, 300, 900, 1800):
            self.assertTrue(valid_ttl(ttl), ttl)

    def test_custom_ttl_accepts_half_hour_steps_through_twelve_hours(self):
        for ttl in (1800, 3600, 5400, 21600, 41400, 43200):
            self.assertTrue(valid_ttl(ttl), ttl)

    def test_custom_ttl_rejects_out_of_range_or_wrong_step(self):
        for ttl in (0, 59, 360, 1799, 2700, 4500, 43201, 45000):
            self.assertFalse(valid_ttl(ttl), ttl)

    def test_twelve_hour_command_is_preserved(self):
        command = self.activate(ttl=43200)
        self.assertEqual(command["ttl"], 43200)

    def test_command_is_consumed_once(self):
        command = self.activate()
        pulled = pull_command(self.store)
        self.assertEqual(pulled["id"], command["id"])
        self.assertTrue(ack_command(self.store, command["id"], True, "ok"))
        self.assertIsNone(pull_command(self.store))
        self.assertFalse(ack_command(self.store, command["id"], True, "again"))

    def test_failed_batch_command_cancels_remaining_family(self):
        now = int(time.time())
        first = {"id": "first", "action": "activate", "family": "ipv4", "batch_id": "batch", "state": "pending", "created_at": now, "expires_at": now + 60}
        second = {"id": "second", "action": "activate", "family": "ipv6", "batch_id": "batch", "state": "pending", "created_at": now, "expires_at": now + 60}
        self.store.write("commands.json", {"pending": first, "next": [second], "last": None})
        self.assertTrue(ack_command(self.store, "first", False, "failed-v4"))
        queue = self.store.read("commands.json", {})
        self.assertIsNone(queue["pending"])
        self.assertEqual(queue["next"], [])
        self.assertEqual(queue["last"]["state"], "failed")
        self.assertEqual(queue["last"]["detail"], "failed-v4")

    def test_expired_followup_batch_command_queues_rollback_close(self):
        now = int(time.time())
        second = {
            "schema": 3,
            "id": "second",
            "action": "activate",
            "family": "ipv6",
            "source_ip": "2001:4860:4860::8888",
            "batch_id": "batch",
            "batch_index": 1,
            "batch_count": 2,
            "ttl": 300,
            "state": "pending",
            "created_at": now - 120,
            "expires_at": now - 1,
        }
        self.store.write("commands.json", {"pending": second, "next": [], "last": None})

        rollback = pull_command(self.store)
        self.assertIsNotNone(rollback)
        self.assertEqual(rollback["action"], "close")
        self.assertEqual(rollback["rollback_for_batch"], "batch")
        self.assertEqual(rollback["expires_at"] - rollback["created_at"], 300)
        queue = self.store.read("commands.json", {})
        self.assertEqual(queue["last"]["id"], "second")
        self.assertEqual(queue["last"]["state"], "expired")
        self.assertEqual(queue["pending"]["id"], rollback["id"])
        self.assertEqual(queue["next"], [])

        with self.assertRaisesRegex(GateError, "command_pending"):
            self.activate()
        self.assertEqual(self.store.read("commands.json", {})["pending"]["id"], rollback["id"])
        events = self.store.read("activity.json", [])
        self.assertTrue(any(item.get("type") == "batch_rollback_queued" and item.get("batch_id") == "batch" for item in events))

    def test_dashboard_view_archives_expired_pending_command(self):
        expired = {
            "schema": 2,
            "id": "dashboard-expired",
            "action": "activate",
            "created_at": int(time.time()) - 120,
            "expires_at": int(time.time()) - 1,
            "state": "pending",
        }
        self.store.write("commands.json", {"pending": expired, "next": [], "last": None})
        view = gate_view(self.store)
        self.assertIsNone(view["queue"]["pending"])
        self.assertEqual(view["queue"]["last"]["state"], "expired")

    def test_pending_command_cannot_be_silently_overwritten(self):
        first = self.activate()
        with self.assertRaisesRegex(GateError, "command_pending"):
            self.activate()
        with self.assertRaisesRegex(GateError, "command_pending"):
            queue_close(self.store, source_ip="198.51.100.7")
        pending = self.store.read("commands.json", {})["pending"]
        self.assertEqual(pending["id"], first["id"])

    def test_expired_pending_command_is_archived_before_replacement(self):
        expired = {
            "schema": 2,
            "id": "expired-command",
            "action": "activate",
            "created_at": int(time.time()) - 120,
            "expires_at": int(time.time()) - 60,
            "state": "pending",
        }
        self.store.write("commands.json", {"pending": expired, "last": None})
        replacement = self.activate()
        queue = self.store.read("commands.json", {})
        self.assertEqual(queue["pending"]["id"], replacement["id"])
        events = self.store.read("activity.json", [])
        self.assertTrue(any(item.get("type") == "command_expired" for item in events))


if __name__ == "__main__":
    unittest.main()
