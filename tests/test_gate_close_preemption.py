import tempfile
import time
import unittest
from pathlib import Path

from server.app.gate import ack_command, queue_close
from server.app.store import JsonStore


class GateClosePreemptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_close_carries_exact_preempted_command_and_batch_identity(self):
        now = int(time.time())
        pending = {
            "id": "activate-first",
            "action": "activate",
            "family": "ipv4",
            "batch_id": "dual-batch",
            "state": "pending",
            "created_at": now,
            "expires_at": now + 60,
        }
        queued = {
            "id": "activate-second",
            "action": "activate",
            "family": "ipv6",
            "batch_id": "dual-batch",
            "state": "pending",
            "created_at": now,
            "expires_at": now + 60,
        }
        self.store.write("commands.json", {"pending": pending, "next": [queued], "last": None})

        close = queue_close(self.store, source_ip="198.51.100.7")
        self.assertEqual(close["preempted_command_id"], "activate-first")
        self.assertEqual(close["preempted_batch_id"], "dual-batch")
        self.assertEqual(self.store.read("commands.json", {})["next"], [])

        self.assertTrue(ack_command(self.store, close["id"], True, "cleared"))
        terminal = self.store.read("commands.json", {})["last"]
        self.assertEqual(terminal["preempted_command_id"], "activate-first")
        self.assertEqual(terminal["preempted_batch_id"], "dual-batch")


if __name__ == "__main__":
    unittest.main()
